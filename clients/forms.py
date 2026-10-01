from django import forms

from core.forms import StyledFormMixin

from .models import Client


class ClientForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Client
        exclude = ["code", "created_at"]
