from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import ListView

from accounts.permissions import PERMISSIONS, has_perm, require_perm
from core.emailing import EmailFailed, send_document
from core.forms import EmailDocumentForm
from core.models import AuditLog, FirmSettings
from core.utils import safe_next
from core.pdf import pdf_response, render_pdf
from core.templatetags.lawtags import money
from matters.models import Matter

from .forms import DisbursementForm, InvoiceCreateForm, InvoiceEditForm, PaymentForm, TimeEntryForm
from .models import Disbursement, Invoice, InvoiceItem, Payment, TimeEntry


def _back(request, default):
    return safe_next(request, default)


# ---------------------------------------------------------------- time recording

class TimeEntryList(ListView):
    template_name = "billing/timeentry_list.html"
    paginate_by = 100

    def get_queryset(self):
        qs = TimeEntry.objects.select_related("matter", "user", "invoice")
        if self.request.GET.get("all") != "1":
            qs = qs.filter(user=self.request.user)
        if self.request.GET.get("unbilled"):
            qs = qs.filter(invoice__isnull=True)
        return qs


def time_entry_form(request, pk=None):
    entry = get_object_or_404(TimeEntry, pk=pk) if pk else None
    if entry and entry.is_locked:
        messages.error(request, f"Already billed on {entry.invoice} – void the fee note to change it.")
        return redirect(entry.matter.get_absolute_url() + "?tab=time")
    initial = {"user": request.user, "date": timezone.localdate(), "matter": request.GET.get("matter")}
    form = TimeEntryForm(request.POST or None, instance=entry, initial=initial)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        AuditLog.record(request.user, "update" if entry else "create", obj)
        messages.success(request, "Time recorded.")
        if "add_another" in request.POST:
            return redirect(f"{request.path}?matter={obj.matter_id}")
        return redirect(_back(request, obj.matter.get_absolute_url() + "?tab=time"))
    return render(request, "form.html", {"form": form, "title": "Time entry", "show_add_another": entry is None})


def time_entry_delete(request, pk):
    entry = get_object_or_404(TimeEntry, pk=pk)
    url = entry.matter.get_absolute_url() + "?tab=time"
    if request.method == "POST":
        if entry.is_locked:
            messages.error(request, "Billed time cannot be deleted.")
        else:
            AuditLog.record(request.user, "delete", entry)
            entry.delete()
            messages.success(request, "Time entry deleted.")
    return redirect(url)


# ---------------------------------------------------------------- disbursements

def disbursement_form(request, pk=None):
    disb = get_object_or_404(Disbursement, pk=pk) if pk else None
    if disb and disb.is_locked:
        messages.error(request, f"Already billed on {disb.invoice}.")
        return redirect(disb.matter.get_absolute_url() + "?tab=disbursements")
    form = DisbursementForm(request.POST or None, instance=disb,
                            initial={"date": timezone.localdate(), "matter": request.GET.get("matter")})
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        if not disb:
            obj.created_by = request.user
        obj.save()
        AuditLog.record(request.user, "update" if disb else "create", obj)
        messages.success(request, "Disbursement saved.")
        return redirect(obj.matter.get_absolute_url() + "?tab=disbursements")
    return render(request, "form.html", {"form": form, "title": "Disbursement"})


def disbursement_delete(request, pk):
    disb = get_object_or_404(Disbursement, pk=pk)
    url = disb.matter.get_absolute_url() + "?tab=disbursements"
    if request.method == "POST":
        if disb.is_locked:
            messages.error(request, "Billed disbursements cannot be deleted.")
        else:
            AuditLog.record(request.user, "delete", disb)
            disb.delete()
            messages.success(request, "Disbursement deleted.")
    return redirect(url)


# ---------------------------------------------------------------- fee notes

class InvoiceList(ListView):
    template_name = "billing/invoice_list.html"
    paginate_by = 50

    def get_queryset(self):
        qs = Invoice.objects.select_related("matter__client")
        status = self.request.GET.get("status")
        q = self.request.GET.get("q", "").strip()
        if status:
            qs = qs.filter(status=status)
        if q:
            qs = qs.filter(Q(number__icontains=q) | Q(matter__file_number__icontains=q)
                           | Q(matter__client__name__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        return super().get_context_data(statuses=Invoice.STATUS_CHOICES, **kwargs)


@require_perm("invoice_issue")
def invoice_create(request, matter_pk):
    matter = get_object_or_404(Matter, pk=matter_pk)
    unbilled_time = matter.time_entries.filter(invoice__isnull=True, billable=True)
    unbilled_disb = matter.disbursements.filter(invoice__isnull=True)
    initial = {
        "date": timezone.localdate(),
        "time_entries": unbilled_time,
        "disbursements": unbilled_disb,
    }
    if matter.billing_type == "fixed" and matter.fixed_fee and not matter.invoices.exclude(status="void").exists():
        initial.update(fixed_fee_description=f"Fixed fee: {matter.description}", fixed_fee_amount=matter.fixed_fee)
    form = InvoiceCreateForm(matter, request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        with transaction.atomic():
            invoice = Invoice.objects.create(matter=matter, date=data["date"], notes=data["notes"],
                                             created_by=request.user)
            data["time_entries"].update(invoice=invoice)
            data["disbursements"].update(invoice=invoice)
            if data.get("fixed_fee_amount"):
                InvoiceItem.objects.create(invoice=invoice, description=data["fixed_fee_description"],
                                           amount=data["fixed_fee_amount"])
        AuditLog.record(request.user, "create", invoice, f"Draft fee note {invoice.number}")
        messages.success(request, f"Draft fee note {invoice.number} created. Review it, then issue it.")
        return redirect(invoice)
    return render(request, "billing/invoice_create.html", {"form": form, "matter": matter})


def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related("matter__client"), pk=pk)
    return render(request, "billing/invoice_detail.html", {
        "invoice": invoice,
        "payment_form": PaymentForm(invoice, initial={"date": timezone.localdate(), "amount": invoice.balance}),
        "edit_form": InvoiceEditForm(instance=invoice),
        "trust_balance": invoice.matter.trust_balance,
    })


def invoice_print(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related("matter__client"), pk=pk)
    return render(request, "billing/invoice_print.html", {"invoice": invoice})


@require_perm("invoice_issue")
def invoice_edit(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, status="draft")
    form = InvoiceEditForm(request.POST or None, instance=invoice)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Fee note updated.")
    return redirect(invoice)


def invoice_action(request, pk, action):
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method != "POST":
        return redirect(invoice)
    needed = "invoice_void" if action == "void" else "invoice_issue"
    if not has_perm(request.user, needed):
        raise PermissionDenied(PERMISSIONS[needed][0])
    if action == "issue" and invoice.status == "draft":
        if invoice.total <= 0:
            messages.error(request, "A fee note must have a total greater than zero.")
            return redirect(invoice)
        invoice.status = "issued"
        invoice.save(update_fields=["status"])
        AuditLog.record(request.user, "issue", invoice, f"Issued fee note {invoice.number} for {invoice.total}")
        messages.success(request, f"{invoice.number} issued.")
    elif action == "void" and invoice.status in ("draft", "issued"):
        if invoice.payments.exists():
            messages.error(request, "Fee notes with payments cannot be voided. Reverse the payments first.")
            return redirect(invoice)
        invoice.void()
        AuditLog.record(request.user, "void", invoice, f"Voided fee note {invoice.number}")
        messages.success(request, f"{invoice.number} voided; its time and disbursements are unbilled again.")
    elif action == "remove_item" and invoice.status == "draft":
        kind, item_id = request.POST.get("kind"), request.POST.get("item")
        if kind == "time":
            invoice.time_entries.filter(pk=item_id).update(invoice=None)
        elif kind == "disbursement":
            invoice.disbursements.filter(pk=item_id).update(invoice=None)
        elif kind == "item":
            invoice.items.filter(pk=item_id).delete()
    else:
        messages.error(request, "That action is not allowed for this fee note.")
    return redirect(invoice)


@require_perm("invoice_void")
def payment_reverse(request, pk):
    from trust import services as trust_services

    payment = get_object_or_404(Payment, pk=pk)
    invoice = payment.invoice
    if request.method == "POST":
        reason = request.POST.get("reason", "").strip() or "Payment reversed"
        if payment.trust_transaction_id:
            trust_services.reverse(payment.trust_transaction, request.user,
                                   date=timezone.localdate(), reason=reason)
        else:
            AuditLog.record(request.user, "reverse", payment,
                            f"Reversed payment {payment.amount} on {invoice.number}: {reason}")
            payment.delete()
            invoice.refresh_status()
        messages.success(request, "Payment reversed.")
    return redirect(invoice)


@require_perm("payment_record")
def payment_add(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, status="issued")
    form = PaymentForm(invoice, request.POST or None)
    if request.method == "POST" and form.is_valid():
        payment = form.save(commit=False)
        payment.invoice, payment.created_by = invoice, request.user
        payment.save()
        invoice.refresh_status()
        AuditLog.record(request.user, "payment", payment, f"Payment {payment.amount} on {invoice.number}")
        messages.success(request, "Payment recorded.")
    else:
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
    return redirect(invoice)


def invoice_pdf(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related("matter__client"), pk=pk)
    return pdf_response("pdf/invoice.html", {"invoice": invoice, "firm": FirmSettings.load()}, f"{invoice.number}.pdf",
                        inline=request.GET.get("download") != "1")


@require_perm("invoice_issue")
def invoice_email(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related("matter__client"), pk=pk)
    if invoice.status not in ("issued", "paid"):
        messages.error(request, "Issue the fee note before emailing it.")
        return redirect(invoice)
    firm = FirmSettings.load()
    client = invoice.matter.client
    initial = {
        "to": client.email,
        "subject": f"Fee note {invoice.number} – {invoice.matter.description}",
        "message": (
            f"Dear {client.contact_person or client.name}\n\n"
            f"Please find attached our fee note {invoice.number} for {money(invoice.total)} "
            f"in respect of {invoice.matter.description} (our ref {invoice.matter.file_number}).\n\n"
            f"Payment is due by {invoice.due_date:%d %B %Y}. Please use {invoice.number} as your payment reference.\n\n"
            f"Kind regards\n{request.user.get_full_name()}\n{firm.name}"
        ),
    }
    form = EmailDocumentForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        pdf = render_pdf("pdf/invoice.html", {"invoice": invoice, "firm": firm})
        try:
            send_document(user=request.user, to=data["to"], subject=data["subject"], body=data["message"],
                          filename=f"{invoice.number}.pdf", pdf_bytes=pdf, obj=invoice)
        except EmailFailed as exc:
            form.add_error(None, f"The email could not be sent: {exc}. Check the email settings.")
        else:
            messages.success(request, f"{invoice.number} emailed to {data['to']}.")
            return redirect(invoice)
    return render(request, "form.html", {"form": form, "title": f"Email {invoice.number}",
                                         "intro": f"The fee note is attached as {invoice.number}.pdf."})
