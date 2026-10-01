from django.db import models
from django.urls import reverse

from core.models import FirmSettings, Sequence


class Client(models.Model):
    TYPE_CHOICES = [("individual", "Individual"), ("company", "Company / Organisation")]

    code = models.CharField(max_length=20, unique=True, editable=False)
    client_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="individual")
    name = models.CharField(max_length=200)
    id_number = models.CharField("ID / registration number", max_length=50, blank=True)
    vat_number = models.CharField(max_length=50, blank=True)
    contact_person = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    physical_address = models.TextField(blank=True)
    postal_address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def save(self, *args, **kwargs):
        if not self.code:
            prefix = FirmSettings.load().client_prefix
            self.code = f"{prefix}{Sequence.next('client'):05d}"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("client_detail", args=[self.pk])
