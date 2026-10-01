from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from matters.models import Matter


class TrustTransaction(models.Model):
    """One line in the trust cash book, always tied to a matter ledger.

    Trust entries are never edited or deleted; mistakes are corrected with a reversal.
    """

    RECEIPT = "receipt"
    PAYMENT = "payment"
    FEE_TRANSFER = "fee_transfer"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    REVERSAL = "reversal"
    TYPE_CHOICES = [
        (RECEIPT, "Receipt (money in)"),
        (PAYMENT, "Payment (money out)"),
        (FEE_TRANSFER, "Transfer to business (fees)"),
        (TRANSFER_IN, "Transfer in from matter"),
        (TRANSFER_OUT, "Transfer out to matter"),
        (REVERSAL, "Reversal"),
    ]
    INFLOW = {RECEIPT, TRANSFER_IN}

    matter = models.ForeignKey(Matter, on_delete=models.PROTECT, related_name="trust_transactions")
    date = models.DateField(default=timezone.localdate)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=14, decimal_places=2, help_text="Always positive.")
    signed_amount = models.DecimalField(max_digits=14, decimal_places=2, editable=False)
    party = models.CharField("received from / paid to", max_length=200, blank=True)
    description = models.CharField(max_length=300)
    reference = models.CharField(max_length=100, blank=True)
    invoice = models.ForeignKey(
        "billing.Invoice", null=True, blank=True, on_delete=models.PROTECT, related_name="trust_transfers"
    )
    linked = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="linked_from",
        help_text="Other side of a matter-to-matter transfer.",
    )
    reverses = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversed_by"
    )
    reconciled = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "id"]

    def __str__(self):
        return f"{self.date} {self.get_type_display()} {self.amount}"

    def save(self, *args, **kwargs):
        if self.type == self.REVERSAL:
            self.signed_amount = -self.reverses.signed_amount
        elif self.type in self.INFLOW:
            self.signed_amount = self.amount
        else:
            self.signed_amount = -self.amount
        super().save(*args, **kwargs)

    @property
    def is_bank_movement(self):
        """Matter-to-matter transfers never touch the bank statement."""
        if self.type == self.REVERSAL:
            return self.reverses.is_bank_movement
        return self.type not in (self.TRANSFER_IN, self.TRANSFER_OUT)

    @classmethod
    def balance_for(cls, matter, as_at=None):
        qs = cls.objects.filter(matter=matter)
        if as_at:
            qs = qs.filter(date__lte=as_at)
        return qs.aggregate(t=Sum("signed_amount"))["t"] or Decimal("0")

    @classmethod
    def total_balance(cls, as_at=None):
        qs = cls.objects.all()
        if as_at:
            qs = qs.filter(date__lte=as_at)
        return qs.aggregate(t=Sum("signed_amount"))["t"] or Decimal("0")


class TrustReconciliation(models.Model):
    """Monthly three-way reconciliation: bank statement vs cash book vs matter ledgers."""

    date = models.DateField()
    bank_statement_balance = models.DecimalField(max_digits=14, decimal_places=2)
    cashbook_balance = models.DecimalField(max_digits=14, decimal_places=2)
    ledger_total = models.DecimalField(max_digits=14, decimal_places=2)
    outstanding_deposits = models.DecimalField(max_digits=14, decimal_places=2)
    outstanding_payments = models.DecimalField(max_digits=14, decimal_places=2)
    notes = models.TextField(blank=True)
    prepared_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    @property
    def adjusted_bank_balance(self):
        return self.bank_statement_balance + self.outstanding_deposits - self.outstanding_payments

    @property
    def difference(self):
        return self.adjusted_bank_balance - self.cashbook_balance

    @property
    def is_balanced(self):
        return self.difference == 0 and self.cashbook_balance == self.ledger_total
