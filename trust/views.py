from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.permissions import require_perm
from billing.models import Invoice
from core.models import AuditLog
from matters.models import Matter

from . import services
from .forms import FeeTransferForm, MatterTransferForm, ReconciliationForm, ReversalForm, TrustEntryForm
from .models import TrustReconciliation, TrustTransaction


@require_perm("trust_view")
def cashbook(request):
    qs = TrustTransaction.objects.select_related("matter__client", "created_by").order_by("-date", "-id")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(matter__file_number__icontains=q) | Q(party__icontains=q)
                       | Q(description__icontains=q) | Q(reference__icontains=q))
    if request.GET.get("type"):
        qs = qs.filter(type=request.GET["type"])
    return render(request, "trust/cashbook.html", {
        "transactions": qs[:500],
        "total": TrustTransaction.total_balance(),
        "types": TrustTransaction.TYPE_CHOICES,
    })


def _entry(request, kind):
    is_receipt = kind == "receipt"
    form = TrustEntryForm(
        request.POST or None,
        initial={"date": timezone.localdate(), "matter": request.GET.get("matter")},
        party_label="Received from" if is_receipt else "Paid to",
    )
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        action = services.receive if is_receipt else services.pay
        try:
            tx = action(data["matter"], data["amount"], request.user, date=data["date"], party=data["party"],
                        description=data["description"], reference=data["reference"])
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f"Trust {'receipt' if is_receipt else 'payment'} recorded.")
            if is_receipt:
                return redirect("trust_receipt_print", pk=tx.pk)
            return redirect(tx.matter.get_absolute_url() + "?tab=trust")
    return render(request, "form.html", {
        "form": form, "title": "Trust receipt" if is_receipt else "Trust payment",
        "intro": None if is_receipt else "Payments are refused if they would overdraw the matter's trust ledger.",
    })


@require_perm("trust_post")
def receipt(request):
    return _entry(request, "receipt")


@require_perm("trust_post")
def payment(request):
    return _entry(request, "payment")


@require_perm("trust_view")
def receipt_print(request, pk):
    tx = get_object_or_404(TrustTransaction.objects.select_related("matter__client"), pk=pk,
                           type=TrustTransaction.RECEIPT)
    return render(request, "trust/receipt_print.html", {"tx": tx})


@require_perm("trust_post")
def fee_transfer(request, invoice_pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    available = invoice.matter.trust_balance
    form = FeeTransferForm(request.POST or None, initial={
        "date": timezone.localdate(), "amount": min(available, invoice.balance),
    })
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            services.transfer_fees(invoice, data["amount"], request.user, date=data["date"],
                                   reference=data["reference"])
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Fees transferred from trust to business.")
            return redirect(invoice)
    return render(request, "form.html", {
        "form": form, "title": f"Pay {invoice.number} from trust",
        "intro": f"Trust balance on {invoice.matter.file_number}: {available}. Fee note balance: {invoice.balance}.",
    })


@require_perm("trust_post")
def matter_transfer(request):
    form = MatterTransferForm(request.POST or None, initial={
        "date": timezone.localdate(), "source": request.GET.get("matter"),
    })
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            services.transfer_between(data["source"], data["target"], data["amount"], request.user,
                                      date=data["date"], description=data["description"])
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Trust transfer recorded.")
            return redirect(data["source"].get_absolute_url() + "?tab=trust")
    return render(request, "form.html", {"form": form, "title": "Transfer trust funds between matters"})


@require_perm("trust_reverse")
def reverse(request, pk):
    tx = get_object_or_404(TrustTransaction, pk=pk)
    form = ReversalForm(request.POST or None, initial={"date": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        try:
            services.reverse(tx, request.user, date=form.cleaned_data["date"], reason=form.cleaned_data["reason"])
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Transaction reversed.")
            return redirect(tx.matter.get_absolute_url() + "?tab=trust")
    return render(request, "form.html", {
        "form": form, "title": "Reverse trust transaction",
        "intro": f"{tx} on {tx.matter.file_number}: {tx.description}. "
                 "Trust entries are never deleted; an equal and opposite entry will be posted.",
    })


@require_perm("trust_view")
def reconciliation_list(request):
    return render(request, "trust/reconciliation_list.html", {
        "reconciliations": TrustReconciliation.objects.select_related("prepared_by"),
    })


@require_perm("trust_reconcile")
def reconciliation_new(request):
    """Tick the cash book entries that appear on the bank statement, then save the reconciliation."""
    try:
        as_at = date.fromisoformat(request.GET.get("date") or request.POST.get("date") or "")
    except ValueError:
        as_at = timezone.localdate()
    form = ReconciliationForm(request.POST or None, initial={"date": as_at})
    if request.method == "POST":
        cleared_ids = request.POST.getlist("cleared")
        items, _, _ = services.unreconciled(as_at)
        TrustTransaction.objects.filter(pk__in=[t.pk for t in items if str(t.pk) in cleared_ids]).update(
            reconciled=True
        )
        if "save" in request.POST and form.is_valid():
            _, deposits, payments = services.unreconciled(as_at)
            cashbook_balance = TrustTransaction.total_balance(as_at)
            matters = Matter.objects.filter(trust_transactions__isnull=False).distinct()
            ledger_total = sum((TrustTransaction.balance_for(m, as_at) for m in matters), Decimal("0"))
            rec = TrustReconciliation.objects.create(
                date=as_at, bank_statement_balance=form.cleaned_data["bank_statement_balance"],
                cashbook_balance=cashbook_balance, ledger_total=ledger_total,
                outstanding_deposits=deposits, outstanding_payments=payments,
                notes=form.cleaned_data["notes"], prepared_by=request.user,
            )
            AuditLog.record(request.user, "reconcile", rec, f"Trust reconciliation {as_at}")
            if rec.is_balanced:
                messages.success(request, "Reconciliation balances.")
            else:
                messages.warning(request, f"Reconciliation saved with a difference of {rec.difference}.")
            return redirect("trust_reconciliation_detail", pk=rec.pk)
        if "save" not in request.POST:
            return redirect(f"{request.path}?date={as_at.isoformat()}")
    items, deposits, payments = services.unreconciled(as_at)
    return render(request, "trust/reconciliation_new.html", {
        "form": form, "items": items, "as_at": as_at, "deposits": deposits, "payments": payments,
        "cashbook": TrustTransaction.total_balance(as_at),
    })


@require_perm("trust_view")
def reconciliation_detail(request, pk):
    return render(request, "trust/reconciliation_detail.html", {"rec": get_object_or_404(TrustReconciliation, pk=pk)})
