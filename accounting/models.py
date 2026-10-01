from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone

CENT = Decimal("0.01")


class Category(models.Model):
    INCOME, EXPENSE = "income", "expense"
    KIND_CHOICES = [(INCOME, "Income"), (EXPENSE, "Expense")]

    name = models.CharField(max_length=100, unique=True)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    system = models.BooleanField(default=False, help_text="Used automatically by the system; can't be removed.")

    class Meta:
        ordering = ["kind", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


FEE_INCOME = "Fee income"


class BusinessTransaction(models.Model):
    """The firm's own (business / office) bank account cash book."""

    RECEIPT, PAYMENT = "receipt", "payment"
    TYPE_CHOICES = [(RECEIPT, "Money in"), (PAYMENT, "Money out")]

    date = models.DateField(default=timezone.localdate)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    party = models.CharField("received from / paid to", max_length=200, blank=True)
    description = models.CharField(max_length=300)
    reference = models.CharField(max_length=100, blank=True)
    amount = models.DecimalField("amount (incl. VAT)", max_digits=14, decimal_places=2)
    vat_amount = models.DecimalField("VAT included", max_digits=14, decimal_places=2, default=Decimal("0"),
                                     help_text="Input VAT you can claim back on this expense.")
    signed_amount = models.DecimalField(max_digits=14, decimal_places=2, editable=False)
    payment = models.OneToOneField("billing.Payment", null=True, blank=True, on_delete=models.CASCADE,
                                   related_name="business_transaction")
    reconciled = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "id"]

    def __str__(self):
        return f"{self.date} {self.description} {self.amount}"

    def save(self, *args, **kwargs):
        self.signed_amount = self.amount if self.type == self.RECEIPT else -self.amount
        super().save(*args, **kwargs)

    @property
    def net_amount(self):
        return self.amount - self.vat_amount

    @property
    def is_automatic(self):
        return self.payment_id is not None

    @classmethod
    def balance(cls, as_at=None):
        qs = cls.objects.all()
        if as_at:
            qs = qs.filter(date__lte=as_at)
        return qs.aggregate(t=Sum("signed_amount"))["t"] or Decimal("0")


def vat_from_gross(gross, rate):
    """VAT contained in a VAT-inclusive amount."""
    if not rate:
        return Decimal("0")
    return (Decimal(gross) * rate / (Decimal("100") + rate)).quantize(CENT, rounding=ROUND_HALF_UP)
