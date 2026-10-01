from decimal import Decimal

from django.conf import settings
from django.db import models, transaction


class FirmSettings(models.Model):
    """Single-row table holding firm-wide configuration."""

    name = models.CharField(max_length=200, default="My Law Firm")
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    vat_number = models.CharField("VAT / tax number", max_length=50, blank=True)
    currency_symbol = models.CharField(max_length=5, default="$")
    vat_rate = models.DecimalField("VAT rate (%)", max_digits=5, decimal_places=2, default=Decimal("15.00"))
    default_hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("150.00"))
    matter_prefix = models.CharField(max_length=10, default="MAT")
    client_prefix = models.CharField(max_length=10, default="CL")
    invoice_prefix = models.CharField(max_length=10, default="INV")
    invoice_due_days = models.PositiveIntegerField(default=30)
    business_bank_details = models.TextField(blank=True, help_text="Printed on fee notes.")
    trust_bank_name = models.CharField(max_length=100, blank=True)
    trust_account_number = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name_plural = "firm settings"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ("partner", "Partner / Director"),
        ("associate", "Associate"),
        ("candidate", "Candidate attorney / Clerk"),
        ("secretary", "Secretary"),
        ("bookkeeper", "Bookkeeper"),
    ]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="associate")
    initials = models.CharField(max_length=5, blank=True)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Sequence(models.Model):
    """Gap-free counters used for file, client and invoice numbers."""

    name = models.CharField(max_length=50, unique=True)
    value = models.PositiveIntegerField(default=0)

    @classmethod
    def next(cls, name):
        with transaction.atomic():
            seq, _ = cls.objects.select_for_update().get_or_create(name=name)
            seq.value += 1
            seq.save(update_fields=["value"])
            return seq.value


class AuditLog(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=20)
    object_type = models.CharField(max_length=100)
    object_id = models.CharField(max_length=50, blank=True)
    description = models.CharField(max_length=500)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.action} {self.description}"

    @classmethod
    def record(cls, user, action, obj, description=None):
        cls.objects.create(
            user=user if user and user.is_authenticated else None,
            action=action,
            object_type=obj._meta.verbose_name,
            object_id=str(obj.pk),
            description=(description or str(obj))[:500],
        )
