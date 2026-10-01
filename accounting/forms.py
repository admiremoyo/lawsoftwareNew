from django import forms

from core.forms import DateInput, StyledFormMixin
from core.models import FirmSettings

from .models import BusinessTransaction, Category, vat_from_gross


class BusinessTransactionForm(StyledFormMixin, forms.ModelForm):
    standard_vat = forms.BooleanField(required=False, label="Amount includes VAT at the standard rate",
                                      help_text="Ticks off the VAT for you. Only for expenses with a valid tax invoice.")

    class Meta:
        model = BusinessTransaction
        fields = ["date", "category", "party", "description", "reference", "amount", "standard_vat", "vat_amount"]
        widgets = {"date": DateInput()}

    def __init__(self, *args, kind, **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = kind
        self.fields["category"].queryset = Category.objects.filter(kind=kind).exclude(system=True)
        self.fields["vat_amount"].required = False
        if kind == Category.INCOME:
            del self.fields["standard_vat"]
            del self.fields["vat_amount"]

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Amount must be greater than zero.")
        return amount

    def clean(self):
        data = super().clean()
        amount = data.get("amount")
        if amount and self.kind == Category.EXPENSE:
            if data.get("standard_vat"):
                data["vat_amount"] = vat_from_gross(amount, FirmSettings.load().vat_rate)
            vat = data.get("vat_amount") or 0
            if vat < 0 or vat >= amount:
                self.add_error("vat_amount", "VAT must be less than the amount.")
            data["vat_amount"] = vat
        return data


class CategoryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "kind"]


class PeriodForm(forms.Form):
    start = forms.DateField()
    end = forms.DateField()
