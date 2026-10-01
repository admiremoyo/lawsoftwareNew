from django import forms
from django.contrib.auth import get_user_model

from core.forms import DateTimeInput, StyledFormMixin
from matters.models import Matter

from .models import DiaryEntry


class DiaryEntryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = DiaryEntry
        fields = ["title", "entry_type", "matter", "assigned_to", "start", "end", "location", "notes", "completed"]
        widgets = {"start": DateTimeInput(), "end": DateTimeInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["matter"].queryset = Matter.objects.exclude(status="closed").select_related("client")
        self.fields["assigned_to"].queryset = get_user_model().objects.filter(is_active=True)

    def clean(self):
        data = super().clean()
        if data.get("start") and data.get("end") and data["end"] < data["start"]:
            self.add_error("end", "End must be after start.")
        return data
