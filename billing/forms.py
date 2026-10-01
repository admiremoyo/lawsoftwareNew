from django import forms
from django.contrib.auth import get_user_model

from core.forms import DateInput, StyledFormMixin
from matters.models import Matter

from .models import Disbursement, Invoice, Payment, TimeEntry


def open_matters(include=None):
    qs = Matter.objects.filter(status="open")
    if include:
        qs = qs | Matter.objects.filter(pk=include)
    return qs.select_related("client")


class TimeEntryForm(StyledFormMixin, forms.ModelForm):
    hours = forms.DecimalField(min_value=0, max_digits=6, decimal_places=2, required=False,
                               help_text="Either hours (e.g. 1.5) or minutes.")

    class Meta:
        model = TimeEntry
        fields = ["matter", "user", "date", "description", "hours", "minutes", "rate", "billable"]
        widgets = {"date": DateInput(), "description": forms.Textarea(attrs={"rows": 2})}
        help_texts = {"rate": "Leave blank to use the matter / fee earner rate."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["matter"].queryset = open_matters(self.instance.matter_id)
        self.fields["user"].queryset = get_user_model().objects.filter(is_active=True)
        self.fields["minutes"].required = False
        self.fields["rate"].required = False

    def clean(self):
        data = super().clean()
        hours, minutes = data.get("hours"), data.get("minutes")
        if hours:
            data["minutes"] = int(round(hours * 60))
        elif not minutes:
            raise forms.ValidationError("Enter the time spent in hours or minutes.")
        return data


class DisbursementForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Disbursement
        fields = ["matter", "date", "description", "amount", "vat_applicable"]
        widgets = {"date": DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["matter"].queryset = open_matters(self.instance.matter_id)
        self.fields["amount"].min_value = 0.01


class InvoiceCreateForm(StyledFormMixin, forms.Form):
    date = forms.DateField(widget=DateInput())
    time_entries = forms.ModelMultipleChoiceField(queryset=TimeEntry.objects.none(), required=False,
                                                  widget=forms.CheckboxSelectMultiple)
    disbursements = forms.ModelMultipleChoiceField(queryset=Disbursement.objects.none(), required=False,
                                                   widget=forms.CheckboxSelectMultiple)
    fixed_fee_description = forms.CharField(required=False, label="Fixed fee / additional item")
    fixed_fee_amount = forms.DecimalField(required=False, min_value=0, max_digits=12, decimal_places=2)
    notes = forms.CharField(required=False, widget=forms.Textarea)

    def __init__(self, matter, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["time_entries"].queryset = matter.time_entries.filter(invoice__isnull=True, billable=True)
        self.fields["disbursements"].queryset = matter.disbursements.filter(invoice__isnull=True)
        for name in ("time_entries", "disbursements"):
            self.fields[name].widget.attrs["class"] = "form-check-input"

    def clean(self):
        data = super().clean()
        if data.get("fixed_fee_amount") and not data.get("fixed_fee_description"):
            self.add_error("fixed_fee_description", "Describe the fixed fee item.")
        if not (data.get("time_entries") or data.get("disbursements") or data.get("fixed_fee_amount")):
            raise forms.ValidationError("Select at least one time entry, disbursement or fixed fee.")
        return data


class InvoiceEditForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ["date", "due_date", "notes"]
        widgets = {"date": DateInput(), "due_date": DateInput()}


class PaymentForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["date", "amount", "method", "reference"]
        widgets = {"date": DateInput()}

    def __init__(self, invoice, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.invoice = invoice
        self.fields["method"].choices = [c for c in Payment.METHOD_CHOICES if c[0] != "trust"]

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Amount must be greater than zero.")
        if amount > self.invoice.balance:
            raise forms.ValidationError(f"Amount exceeds the outstanding balance of {self.invoice.balance}.")
        return amount
