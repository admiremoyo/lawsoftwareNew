from django import forms

from core.forms import DateInput, StyledFormMixin
from matters.models import Matter


class TrustEntryForm(StyledFormMixin, forms.Form):
    matter = forms.ModelChoiceField(queryset=Matter.objects.exclude(status="closed").select_related("client"))
    date = forms.DateField(widget=DateInput())
    amount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0.01)
    party = forms.CharField(max_length=200)
    description = forms.CharField(max_length=300)
    reference = forms.CharField(max_length=100, required=False)

    def __init__(self, *args, party_label="Received from", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["party"].label = party_label


class FeeTransferForm(StyledFormMixin, forms.Form):
    date = forms.DateField(widget=DateInput())
    amount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0.01)
    reference = forms.CharField(max_length=100, required=False)


class MatterTransferForm(StyledFormMixin, forms.Form):
    source = forms.ModelChoiceField(queryset=Matter.objects.exclude(status="closed"), label="From matter")
    target = forms.ModelChoiceField(queryset=Matter.objects.exclude(status="closed"), label="To matter")
    date = forms.DateField(widget=DateInput())
    amount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0.01)
    description = forms.CharField(max_length=300)


class ReversalForm(StyledFormMixin, forms.Form):
    date = forms.DateField(widget=DateInput())
    reason = forms.CharField(max_length=250)


class ReconciliationForm(StyledFormMixin, forms.Form):
    date = forms.DateField(widget=DateInput(), help_text="Bank statement date.")
    bank_statement_balance = forms.DecimalField(max_digits=14, decimal_places=2)
    notes = forms.CharField(required=False, widget=forms.Textarea)
