from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from core.models import FirmSettings, Sequence
from matters.models import Matter

CENT = Decimal("0.01")


def _sum(qs, field="amount"):
    return qs.aggregate(t=Sum(field))["t"] or Decimal("0")


class Invoice(models.Model):
    """A fee note / tax invoice raised against a matter."""

    STATUS_CHOICES = [("draft", "Draft"), ("issued", "Issued"), ("paid", "Paid"), ("void", "Void")]

    number = models.CharField(max_length=30, unique=True, editable=False)
    matter = models.ForeignKey(Matter, on_delete=models.PROTECT, related_name="invoices")
    date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="draft")
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return self.number

    def save(self, *args, **kwargs):
        firm = FirmSettings.load()
        if not self.number:
            self.number = f"{firm.invoice_prefix}{Sequence.next('invoice'):05d}"
        if self.vat_rate is None:
            self.vat_rate = firm.vat_rate
        if self.due_date is None:
            self.due_date = self.date + timezone.timedelta(days=firm.invoice_due_days)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("invoice_detail", args=[self.pk])

    @property
    def time_fees(self):
        return _sum(self.time_entries.all())

    @property
    def item_fees(self):
        return _sum(self.items.all())

    @property
    def fees(self):
        return self.time_fees + self.item_fees

    @property
    def vatable_disbursements(self):
        return _sum(self.disbursements.filter(vat_applicable=True))

    @property
    def other_disbursements(self):
        return _sum(self.disbursements.filter(vat_applicable=False))

    @property
    def disbursement_total(self):
        return self.vatable_disbursements + self.other_disbursements

    @property
    def vat(self):
        base = self.fees + self.vatable_disbursements
        return (base * self.vat_rate / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)

    @property
    def total(self):
        return self.fees + self.disbursement_total + self.vat

    @property
    def paid(self):
        return _sum(self.payments.all())

    @property
    def balance(self):
        if self.status == "void":
            return Decimal("0")
        return self.total - self.paid

    def refresh_status(self):
        if self.status in ("issued", "paid"):
            self.status = "paid" if self.balance <= 0 else "issued"
            self.save(update_fields=["status"])

    def void(self):
        self.time_entries.update(invoice=None)
        self.disbursements.update(invoice=None)
        self.status = "void"
        self.save(update_fields=["status"])


class InvoiceItem(models.Model):
    """Manual fee line, e.g. a fixed fee or tariff item."""

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=300)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return self.description


class TimeEntry(models.Model):
    matter = models.ForeignKey(Matter, on_delete=models.PROTECT, related_name="time_entries")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="fee earner")
    date = models.DateField(default=timezone.localdate)
    description = models.CharField(max_length=500)
    minutes = models.PositiveIntegerField()
    rate = models.DecimalField("hourly rate", max_digits=10, decimal_places=2, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    billable = models.BooleanField(default=True)
    invoice = models.ForeignKey(
        Invoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="time_entries"
    )

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name_plural = "time entries"

    def __str__(self):
        return f"{self.date} {self.description[:40]}"

    def save(self, *args, **kwargs):
        if self.rate is None:
            self.rate = self.matter.rate_for(self.user)
        self.amount = (Decimal(self.minutes) / Decimal(60) * self.rate).quantize(CENT, rounding=ROUND_HALF_UP)
        super().save(*args, **kwargs)

    @property
    def is_locked(self):
        return self.invoice_id is not None


class Disbursement(models.Model):
    matter = models.ForeignKey(Matter, on_delete=models.PROTECT, related_name="disbursements")
    date = models.DateField(default=timezone.localdate)
    description = models.CharField(max_length=300)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    vat_applicable = models.BooleanField(default=False, help_text="Charge VAT on this disbursement.")
    invoice = models.ForeignKey(
        Invoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="disbursements"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return self.description

    @property
    def is_locked(self):
        return self.invoice_id is not None


class Payment(models.Model):
    METHOD_CHOICES = [
        ("eft", "EFT / bank transfer"),
        ("cash", "Cash"),
        ("card", "Card"),
        ("cheque", "Cheque"),
        ("mobile", "Mobile money"),
        ("trust", "Transfer from trust"),
    ]
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=10, choices=METHOD_CHOICES, default="eft")
    reference = models.CharField(max_length=100, blank=True)
    trust_transaction = models.OneToOneField(
        "trust.TrustTransaction", null=True, blank=True, on_delete=models.PROTECT, related_name="payment"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.invoice} {self.amount}"
