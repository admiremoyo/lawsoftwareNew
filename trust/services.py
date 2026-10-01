"""All trust money movements go through these functions so the no-overdraft rule
is enforced in one place."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from billing.models import Payment
from core.models import AuditLog

from .models import TrustTransaction


def _check_positive(amount):
    if amount is None or amount <= 0:
        raise ValidationError("Amount must be greater than zero.")


def _check_funds(matter, amount):
    balance = TrustTransaction.balance_for(matter)
    if amount > balance:
        raise ValidationError(
            f"Insufficient trust funds on {matter.file_number}: balance is {balance}, "
            f"requested {amount}. A matter's trust ledger may never be overdrawn."
        )


def _lock(matter):
    # Serialise trust activity per matter so two clerks can't overdraw it concurrently.
    type(matter).objects.select_for_update().get(pk=matter.pk)


@transaction.atomic
def receive(matter, amount, user, *, date, party, description, reference=""):
    _check_positive(amount)
    tx = TrustTransaction.objects.create(
        matter=matter, type=TrustTransaction.RECEIPT, amount=amount, date=date,
        party=party, description=description, reference=reference, created_by=user,
    )
    AuditLog.record(user, "trust", tx, f"Trust receipt {amount} on {matter.file_number}")
    return tx


@transaction.atomic
def pay(matter, amount, user, *, date, party, description, reference=""):
    _check_positive(amount)
    _lock(matter)
    _check_funds(matter, amount)
    tx = TrustTransaction.objects.create(
        matter=matter, type=TrustTransaction.PAYMENT, amount=amount, date=date,
        party=party, description=description, reference=reference, created_by=user,
    )
    AuditLog.record(user, "trust", tx, f"Trust payment {amount} on {matter.file_number}")
    return tx


@transaction.atomic
def transfer_fees(invoice, amount, user, *, date, reference=""):
    """Move money from the matter's trust ledger to business to settle a fee note."""
    _check_positive(amount)
    matter = invoice.matter
    if invoice.status not in ("issued",):
        raise ValidationError("Only issued, unpaid fee notes can be settled from trust.")
    if amount > invoice.balance:
        raise ValidationError(f"Amount exceeds the fee note balance of {invoice.balance}.")
    _lock(matter)
    _check_funds(matter, amount)
    tx = TrustTransaction.objects.create(
        matter=matter, type=TrustTransaction.FEE_TRANSFER, amount=amount, date=date,
        party="Business account", description=f"Fees – {invoice.number}", reference=reference,
        invoice=invoice, created_by=user,
    )
    Payment.objects.create(
        invoice=invoice, date=date, amount=amount, method="trust",
        reference=reference or f"Trust tx {tx.pk}", trust_transaction=tx, created_by=user,
    )
    invoice.refresh_status()
    AuditLog.record(user, "trust", tx, f"Trust-to-business {amount} for {invoice.number}")
    return tx


@transaction.atomic
def transfer_between(source, target, amount, user, *, date, description):
    _check_positive(amount)
    if source.pk == target.pk:
        raise ValidationError("Source and target matter must differ.")
    _lock(source)
    _check_funds(source, amount)
    out = TrustTransaction.objects.create(
        matter=source, type=TrustTransaction.TRANSFER_OUT, amount=amount, date=date,
        party=target.file_number, description=description, created_by=user,
    )
    inn = TrustTransaction.objects.create(
        matter=target, type=TrustTransaction.TRANSFER_IN, amount=amount, date=date,
        party=source.file_number, description=description, created_by=user, linked=out,
    )
    AuditLog.record(user, "trust", out, f"Trust transfer {amount} {source.file_number} -> {target.file_number}")
    return out, inn


@transaction.atomic
def reverse(tx, user, *, date, reason):
    """Undo an entry with an equal and opposite one. Paired transfers reverse together."""
    if tx.type == TrustTransaction.REVERSAL:
        raise ValidationError("A reversal cannot itself be reversed.")
    if hasattr(tx, "reversed_by"):
        raise ValidationError("This transaction has already been reversed.")
    pair = tx.linked or getattr(tx, "linked_from", None)
    entries = [tx] + ([pair] if pair else [])
    for entry in entries:
        if entry.signed_amount > 0:  # reversing money in takes money out
            _lock(entry.matter)
            _check_funds(entry.matter, entry.signed_amount)
    created = []
    for entry in entries:
        created.append(
            TrustTransaction.objects.create(
                matter=entry.matter, type=TrustTransaction.REVERSAL, amount=entry.amount, date=date,
                party=entry.party, description=f"Reversal: {reason}", reverses=entry, created_by=user,
            )
        )
    if tx.type == TrustTransaction.FEE_TRANSFER:
        # Money goes back to trust, so the fee note is unpaid again.
        payment = Payment.objects.filter(trust_transaction=tx).first()
        if payment:
            invoice = payment.invoice
            payment.delete()
            invoice.refresh_status()
    AuditLog.record(user, "trust", tx, f"Reversed trust tx {tx.pk}: {reason}")
    return created[0]


def unreconciled(as_at):
    """Bank-affecting cash book entries up to a date that are not yet on a statement."""
    qs = TrustTransaction.objects.filter(date__lte=as_at, reconciled=False).select_related("reverses")
    deposits = Decimal("0")
    payments = Decimal("0")
    items = []
    for tx in qs:
        if not tx.is_bank_movement:
            continue
        items.append(tx)
        if tx.signed_amount > 0:
            deposits += tx.signed_amount
        else:
            payments += -tx.signed_amount
    return items, deposits, payments
