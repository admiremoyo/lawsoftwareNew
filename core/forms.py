from django import forms

from .models import FirmSettings


class StyledFormMixin:
    """Adds Bootstrap classes to every widget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")
            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("rows", 3)


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs):
        kwargs.setdefault("format", "%Y-%m-%d")
        super().__init__(**kwargs)


class DateTimeInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self, **kwargs):
        kwargs.setdefault("format", "%Y-%m-%dT%H:%M")
        super().__init__(**kwargs)


class FirmSettingsForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = FirmSettings
        fields = "__all__"
        widgets = {"logo": forms.ClearableFileInput(attrs={"accept": "image/png,image/jpeg"})}

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if logo and hasattr(logo, "content_type"):
            if logo.content_type not in ("image/png", "image/jpeg"):
                raise forms.ValidationError("Upload a PNG or JPG image.")
            if logo.size > 2 * 1024 * 1024:
                raise forms.ValidationError("The logo must be smaller than 2 MB.")
        return logo


class EmailDocumentForm(StyledFormMixin, forms.Form):
    to = forms.EmailField(label="To")
    subject = forms.CharField(max_length=200)
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 8}))
