from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.permissions import require_perm
from billing.models import Invoice, Payment
from clients.models import Client
from core.emailing import EmailFailed, send_document
from core.forms import EmailDocumentForm
from core.models import AuditLog, FirmSettings
from core.pdf import pdf_response, render_pdf
from core.templatetags.lawtags import money
from core.views import _csv, _parse_date
from matters.models import Matter
from trust.models import TrustTransaction

from .forms import BusinessTransactionForm, CategoryForm
from .models import BusinessTransaction, Category

ZERO = Decimal("0")


def _period(request):
    today = timezone.localdate()
    start = _parse_date(request.GET.get("start"), today.replace(day=1))
    end = _parse_date(request.GET.get("end"), today)
    return start, end


@require_perm("accounting")
def cashbook(request):
    start, end = _period(request)
    if "start" not in request.GET:
        start = date(end.year, 1, 1)
    qs = BusinessTransaction.objects.filter(date__range=(start, end)).select_related("category", "payment__invoice")
    category = request.GET.get("category")
    if category:
        qs = qs.filter(category_id=category)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(description__icontains=q) | Q(party__icontains=q) | Q(reference__icontains=q))
    opening = BusinessTransaction.balance(start - timezone.timedelta(days=1)) if not (category or q) else None
    rows, running = [], opening or ZERO
    for tx in qs:
        running += tx.signed_amount
        rows.append((tx, running if opening is not None else None))
    if request.GET.get("format") == "csv":
        return _csv("business_cashbook.csv", ["Date", "Type", "Category", "Party", "Description", "Reference",
                                              "Amount", "VAT"], [
            [t.date, t.get_type_display(), t.category.name, t.party, t.description, t.reference, t.signed_amount,
             t.vat_amount] for t, _ in rows])
    return render(request, "accounting/cashbook.html", {
        "rows": rows, "start": start, "end": end, "opening": opening, "closing": running,
        "balance": BusinessTransaction.balance(), "categories": Category.objects.all(),
    })


@require_perm("accounting")
def entry_form(request, kind, pk=None):
    tx = get_object_or_404(BusinessTransaction, pk=pk) if pk else None
    if tx and tx.is_automatic:
        messages.error(request, "This entry was created from a fee payment. Reverse the payment on the fee note instead.")
        return redirect("business_cashbook")
    if tx:
        kind = Category.INCOME if tx.type == BusinessTransaction.RECEIPT else Category.EXPENSE
    form = BusinessTransactionForm(request.POST or None, instance=tx, kind=kind,
                                   initial={"date": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.type = BusinessTransaction.RECEIPT if kind == Category.INCOME else BusinessTransaction.PAYMENT
        if not tx:
            obj.created_by = request.user
        obj.save()
        AuditLog.record(request.user, "update" if tx else "create", obj,
                        f"Business {obj.get_type_display().lower()} {obj.amount}: {obj.description}")
        messages.success(request, "Saved.")
        if "add_another" in request.POST:
            return redirect(request.path)
        return redirect("business_cashbook")
    title = ("Edit " if tx else "New ") + ("income / money in" if kind == Category.INCOME else "expense / money out")
    return render(request, "form.html", {
        "form": form, "title": title, "show_add_another": tx is None,
        "delete_url": f"/accounting/entries/{tx.pk}/delete/" if tx else None,
    })


@require_perm("accounting")
def entry_delete(request, pk):
    tx = get_object_or_404(BusinessTransaction, pk=pk, payment__isnull=True)
    if request.method == "POST":
        AuditLog.record(request.user, "delete", tx, f"Deleted business entry {tx.amount}: {tx.description}")
        tx.delete()
        messages.success(request, "Entry deleted.")
    return redirect("business_cashbook")


@require_perm("accounting")
def categories(request):
    form = CategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Category added.")
        return redirect("accounting_categories")
    return render(request, "accounting/categories.html", {"form": form, "categories": Category.objects.all()})


def _output_vat(start, end, basis):
    """VAT charged to clients in the period, on the invoice or the payments basis."""
    if basis == "payments":
        total = ZERO
        payments = Payment.objects.filter(date__range=(start, end)).select_related("invoice")
        for p in payments:
            inv = p.invoice
            if inv.total:
                total += (p.amount * inv.vat / inv.total).quantize(Decimal("0.01"))
        return total, payments.count()
    invoices = Invoice.objects.filter(date__range=(start, end), status__in=["issued", "paid"])
    return sum((i.vat for i in invoices), ZERO), invoices.count()


@require_perm("accounting")
def vat_report(request):
    start, end = _period(request)
    basis = request.GET.get("basis", "invoice")
    output_vat, output_count = _output_vat(start, end, basis)
    expenses = BusinessTransaction.objects.filter(date__range=(start, end), type=BusinessTransaction.PAYMENT,
                                                  vat_amount__gt=0).select_related("category")
    input_vat = expenses.aggregate(t=Sum("vat_amount"))["t"] or ZERO
    invoices = Invoice.objects.filter(date__range=(start, end), status__in=["issued", "paid"]).select_related(
        "matter__client")
    return render(request, "accounting/vat_report.html", {
        "start": start, "end": end, "basis": basis, "output_vat": output_vat, "output_count": output_count,
        "input_vat": input_vat, "net": output_vat - input_vat, "expenses": expenses,
        "invoices": invoices if basis == "invoice" else None,
    })


@require_perm("accounting")
def income_statement(request):
    start, end = _period(request)
    if "start" not in request.GET:
        start = date(end.year, 1, 1)
    invoices = Invoice.objects.filter(date__range=(start, end), status__in=["issued", "paid"])
    fees = sum((i.fees for i in invoices), ZERO)
    disbursements_recovered = sum((i.disbursement_total for i in invoices), ZERO)
    other_income = []
    for cat in Category.objects.filter(kind=Category.INCOME, system=False):
        amount = BusinessTransaction.objects.filter(category=cat, date__range=(start, end)).aggregate(
            t=Sum("amount"))["t"] or ZERO
        if amount:
            other_income.append((cat, amount))
    expenses = []
    for cat in Category.objects.filter(kind=Category.EXPENSE):
        agg = BusinessTransaction.objects.filter(category=cat, date__range=(start, end)).aggregate(
            gross=Sum("amount"), vat=Sum("vat_amount"))
        net = (agg["gross"] or ZERO) - (agg["vat"] or ZERO)
        if net:
            expenses.append((cat, net))
    total_income = fees + disbursements_recovered + sum((a for _, a in other_income), ZERO)
    total_expenses = sum((a for _, a in expenses), ZERO)
    return render(request, "accounting/income_statement.html", {
        "start": start, "end": end, "fees": fees, "disbursements_recovered": disbursements_recovered,
        "other_income": other_income, "expenses": expenses, "total_income": total_income,
        "total_expenses": total_expenses, "profit": total_income - total_expenses,
        "invoice_count": invoices.count(),
    })


def statement_data(client, matter=None, start=None):
    """Statement of account: fee notes as debits, payments as credits, with a running balance."""
    matters = [matter] if matter else list(client.matters.all())
    lines = []
    for inv in Invoice.objects.filter(matter__in=matters, status__in=["issued", "paid"]).select_related("matter"):
        lines.append({"date": inv.date, "ref": inv.number, "matter": inv.matter,
                      "description": f"Fee note – {inv.matter.description}", "debit": inv.total, "credit": None})
        for p in inv.payments.all():
            lines.append({"date": p.date, "ref": p.reference or inv.number, "matter": inv.matter,
                          "description": f"Payment received ({p.get_method_display()}) – {inv.number}",
                          "debit": None, "credit": p.amount})
    lines.sort(key=lambda line: (line["date"], line["credit"] is not None))
    opening = ZERO
    if start:
        for line in [ln for ln in lines if ln["date"] < start]:
            opening += (line["debit"] or ZERO) - (line["credit"] or ZERO)
        lines = [ln for ln in lines if ln["date"] >= start]
    balance = opening
    for line in lines:
        balance += (line["debit"] or ZERO) - (line["credit"] or ZERO)
        line["balance"] = balance
    trust = [(m, TrustTransaction.balance_for(m)) for m in matters]
    return {
        "client": client, "matter": matter, "lines": lines, "opening": opening, "closing": balance,
        "start": start, "trust": [(m, b) for m, b in trust if b], "today": timezone.localdate(),
    }


def _statement_args(request, client_pk):
    client = get_object_or_404(Client, pk=client_pk)
    matter = get_object_or_404(Matter, pk=request.GET["matter"], client=client) if request.GET.get("matter") else None
    return statement_data(client, matter, _parse_date(request.GET.get("start"), None))


def statement(request, client_pk):
    data = _statement_args(request, client_pk)
    if request.GET.get("format") == "pdf":
        return pdf_response("pdf/statement.html", {**data, "firm": FirmSettings.load()},
                            f"Statement-{data['client'].code}.pdf")
    return render(request, "accounting/statement.html", data)


def email_statement(request, client_pk):
    data = _statement_args(request, client_pk)
    client, firm = data["client"], FirmSettings.load()
    form = EmailDocumentForm(request.POST if "to" in request.POST else None, initial={
        "to": client.email,
        "subject": f"Statement of account – {firm.name}",
        "message": (f"Dear {client.contact_person or client.name}\n\nPlease find attached your statement of account. "
                    f"The amount due is {money(data['closing'])}.\n\nKind regards\n"
                    f"{request.user.get_full_name()}\n{firm.name}"),
    })
    if form.is_bound and form.is_valid():
        pdf = render_pdf("pdf/statement.html", {**data, "firm": firm})
        try:
            send_document(user=request.user, to=form.cleaned_data["to"], subject=form.cleaned_data["subject"],
                          body=form.cleaned_data["message"], filename=f"Statement-{client.code}.pdf",
                          pdf_bytes=pdf, obj=client)
        except EmailFailed as exc:
            form.add_error(None, f"The email could not be sent: {exc}. Check the email settings.")
        else:
            messages.success(request, f"Statement emailed to {form.cleaned_data['to']}.")
            return redirect(client)
    return render(request, "form.html", {"form": form, "title": f"Email statement to {client.name}",
                                         "intro": "The statement is attached as a PDF."})
