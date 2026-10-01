from django.conf import settings
from django.db import models
from django.urls import reverse

from matters.models import Matter


class DiaryEntry(models.Model):
    TYPE_CHOICES = [
        ("appointment", "Appointment / Consultation"),
        ("court", "Court date"),
        ("deadline", "Deadline / Dies"),
        ("task", "Task"),
        ("reminder", "Reminder"),
    ]
    title = models.CharField(max_length=200)
    entry_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="appointment")
    matter = models.ForeignKey(Matter, null=True, blank=True, on_delete=models.CASCADE, related_name="diary_entries")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="diary_entries")
    start = models.DateTimeField()
    end = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    completed = models.BooleanField(default=False)

    class Meta:
        ordering = ["start"]
        verbose_name_plural = "diary entries"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("diary_edit", args=[self.pk])
