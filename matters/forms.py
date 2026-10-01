from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q

from clients.models import Client
from core.forms import DateInput, StyledFormMixin

from .models import Document, DocumentTemplate, FileNote, Matter, MatterTask, WorkflowStep, WorkflowTemplate


class MatterForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Matter
        exclude = ["file_number", "created_at"]
        widgets = {
            "date_opened": DateInput(),
            "date_closed": DateInput(),
            "prescription_date": DateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsible"].queryset = get_user_model().objects.filter(is_active=True)
        self.fields["client"].queryset = Client.objects.filter(Q(is_active=True) | Q(pk=self.instance.client_id))


class FileNoteForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = FileNote
        fields = ["date", "note"]
        widgets = {"date": DateInput()}


ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "dot", "dotx", "rtf", "odt", "txt", "xls", "xlsx", "csv", "ods", "ppt", "pptx",
    "jpg", "jpeg", "png", "gif", "tif", "tiff", "bmp", "msg", "eml", "zip", "7z",
}


class DocumentForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Document
        fields = ["title", "file"]

    def clean_file(self):
        upload = self.cleaned_data["file"]
        ext = upload.name.rsplit(".", 1)[-1].lower() if "." in upload.name else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise forms.ValidationError(f"Files of type .{ext or '?'} can't be uploaded.")
        if upload.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise forms.ValidationError(f"Files must be smaller than {settings.MAX_UPLOAD_MB} MB.")
        return upload


class DocumentTemplateForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = DocumentTemplate
        fields = "__all__"
        widgets = {"body": forms.Textarea(attrs={"rows": 18})}

    def clean_body(self):
        from django.template import TemplateSyntaxError

        from .merge import BLOCKED_TAGS, ENGINE

        body = self.cleaned_data["body"]
        if any(tag in body.lower() for tag in BLOCKED_TAGS):
            raise forms.ValidationError("Precedents can't use include, extends, load or debug tags.")
        try:
            ENGINE.from_string(body)
        except TemplateSyntaxError as exc:
            raise forms.ValidationError(f"Template error: {exc}")
        return body


class GenerateDocumentForm(StyledFormMixin, forms.Form):
    template = forms.ModelChoiceField(queryset=DocumentTemplate.objects.all())
    save_to_matter = forms.BooleanField(required=False, initial=True, label="Also save a copy on the matter")


class WorkflowTemplateForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = WorkflowTemplate
        fields = ["name", "matter_type", "auto_apply"]


class WorkflowStepForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = WorkflowStep
        fields = ["order", "title", "due_after_days"]


WorkflowStepFormSet = forms.inlineformset_factory(
    WorkflowTemplate, WorkflowStep, form=WorkflowStepForm, extra=3, can_delete=True)


class MatterTaskForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = MatterTask
        fields = ["title", "due_date"]
        widgets = {"due_date": DateInput(), "title": forms.TextInput(attrs={"placeholder": "New step…"})}
