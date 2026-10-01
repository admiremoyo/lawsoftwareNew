from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.urls import reverse

from clients.models import Client
from core.models import FirmSettings, Sequence


class Matter(models.Model):
    TYPE_CHOICES = [
        ("litigation", "Litigation"),
        ("conveyancing", "Conveyancing / Property"),
        ("estates", "Deceased estates / Wills"),
        ("commercial", "Commercial / Corporate"),
        ("family", "Family / Divorce"),
        ("labour", "Labour"),
        ("criminal", "Criminal"),
        ("collections", "Collections / Debt recovery"),
        ("other", "Other"),
    ]
    STATUS_CHOICES = [("open", "Open"), ("on_hold", "On hold"), ("closed", "Closed")]
    BILLING_CHOICES = [("hourly", "Hourly / time based"), ("fixed", "Fixed fee"), ("contingency", "Contingency")]

    file_number = models.CharField(max_length=30, unique=True, editable=False)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="matters")
    description = models.CharField(max_length=300)
    matter_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="other")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="matters", verbose_name="responsible attorney"
    )
    date_opened = models.DateField()
    date_closed = models.DateField(null=True, blank=True)
    billing_type = models.CharField(max_length=20, choices=BILLING_CHOICES, default="hourly")
    hourly_rate = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Overrides the fee earner's rate."
    )
    fixed_fee = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    opposing_party = models.CharField(max_length=200, blank=True)
    opposing_attorney = models.CharField(max_length=200, blank=True)
    court = models.CharField(max_length=200, blank=True)
    case_number = models.CharField(max_length=100, blank=True)
    prescription_date = models.DateField(null=True, blank=True, help_text="Date the claim prescribes.")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_opened", "-id"]

    def __str__(self):
        return f"{self.file_number} – {self.description}"

    def save(self, *args, **kwargs):
        if not self.file_number:
            prefix = FirmSettings.load().matter_prefix
            self.file_number = f"{prefix}{Sequence.next('matter'):05d}"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("matter_detail", args=[self.pk])

    def rate_for(self, user):
        if self.hourly_rate is not None:
            return self.hourly_rate
        profile = getattr(user, "profile", None)
        if profile and profile.hourly_rate is not None:
            return profile.hourly_rate
        return FirmSettings.load().default_hourly_rate

    @property
    def trust_balance(self):
        from trust.models import TrustTransaction

        return TrustTransaction.balance_for(self)

    @property
    def unbilled_fees(self):
        return self.time_entries.filter(billable=True, invoice__isnull=True).aggregate(t=Sum("amount"))["t"] or Decimal(
            "0"
        )

    @property
    def unbilled_disbursements(self):
        return self.disbursements.filter(invoice__isnull=True).aggregate(t=Sum("amount"))["t"] or Decimal("0")

    @property
    def outstanding(self):
        return sum((inv.balance for inv in self.invoices.exclude(status__in=["draft", "void"])), Decimal("0"))


class FileNote(models.Model):
    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, related_name="file_notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    date = models.DateField()
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.date} {self.note[:50]}"


def document_path(instance, filename):
    return f"matters/{instance.matter.file_number}/{filename}"


class Document(models.Model):
    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to=document_path)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.title


class DocumentTemplate(models.Model):
    """Precedent with merge fields, e.g. {{ client.name }} or {{ matter.file_number }}."""

    name = models.CharField(max_length=200)
    matter_type = models.CharField(max_length=20, choices=[("", "Any")] + Matter.TYPE_CHOICES, blank=True)
    body = models.TextField(
        help_text="Merge fields: {{ firm.name }}, {{ client.name }}, {{ client.physical_address }}, "
        "{{ matter.file_number }}, {{ matter.description }}, {{ matter.opposing_party }}, "
        "{{ matter.case_number }}, {{ author }}, {{ today }}"
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
