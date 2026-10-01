import os

from django.contrib import messages
from django.core.files.base import ContentFile
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template import Context, Template, TemplateSyntaxError
from django.utils import timezone
from django.utils.html import linebreaks
from django.utils.text import slugify
from django.views.generic import CreateView, ListView, UpdateView

from accounts.permissions import PermissionMixin
from core.models import AuditLog, FirmSettings
from trust.models import TrustTransaction

from .forms import DocumentForm, DocumentTemplateForm, FileNoteForm, GenerateDocumentForm, MatterForm
from .models import Document, DocumentTemplate, Matter


class MatterList(ListView):
    model = Matter
    paginate_by = 50

    def get_queryset(self):
        qs = Matter.objects.select_related("client", "responsible")
        q = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "open")
        mine = self.request.GET.get("mine")
        if q:
            qs = qs.filter(
                Q(file_number__icontains=q) | Q(description__icontains=q) | Q(client__name__icontains=q)
                | Q(case_number__icontains=q) | Q(opposing_party__icontains=q)
            )
        if status:
            qs = qs.filter(status=status)
        if mine:
            qs = qs.filter(responsible=self.request.user)
        return qs

    def get_context_data(self, **kwargs):
        return super().get_context_data(statuses=Matter.STATUS_CHOICES, **kwargs)


class MatterCreate(CreateView):
    model = Matter
    form_class = MatterForm
    template_name = "form.html"
    extra_context = {"title": "Open new matter"}

    def get_initial(self):
        initial = {"date_opened": timezone.localdate(), "responsible": self.request.user}
        if "client" in self.request.GET:
            initial["client"] = self.request.GET["client"]
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        AuditLog.record(self.request.user, "create", self.object)
        messages.success(self.request, f"Matter {self.object.file_number} opened.")
        return response


class MatterUpdate(UpdateView):
    model = Matter
    form_class = MatterForm
    template_name = "form.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(title=f"Edit {self.object.file_number}", **kwargs)

    def form_valid(self, form):
        if form.cleaned_data["status"] == "closed":
            if TrustTransaction.balance_for(self.object) != 0:
                form.add_error("status", "Cannot close a matter that still holds money in trust.")
                return self.form_invalid(form)
            if not form.cleaned_data["date_closed"]:
                form.instance.date_closed = timezone.localdate()
        response = super().form_valid(form)
        AuditLog.record(self.request.user, "update", self.object)
        messages.success(self.request, "Matter updated.")
        return response


def matter_detail(request, pk):
    matter = get_object_or_404(Matter.objects.select_related("client", "responsible"), pk=pk)
    tab = request.GET.get("tab", "overview")
    ledger, running = [], 0
    for tx in matter.trust_transactions.select_related("invoice"):
        running += tx.signed_amount
        ledger.append((tx, running))
    context = {
        "matter": matter,
        "tab": tab,
        "note_form": FileNoteForm(initial={"date": timezone.localdate()}),
        "doc_form": DocumentForm(),
        "generate_form": GenerateDocumentForm(),
        "time_entries": matter.time_entries.select_related("user", "invoice"),
        "disbursements": matter.disbursements.select_related("invoice"),
        "invoices": matter.invoices.all(),
        "ledger": ledger,
        "diary": matter.diary_entries.select_related("assigned_to"),
    }
    return render(request, "matters/matter_detail.html", context)


def add_file_note(request, pk):
    matter = get_object_or_404(Matter, pk=pk)
    form = FileNoteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        note = form.save(commit=False)
        note.matter, note.author = matter, request.user
        note.save()
        messages.success(request, "File note added.")
    return redirect(f"{matter.get_absolute_url()}?tab=notes")


def upload_document(request, pk):
    matter = get_object_or_404(Matter, pk=pk)
    form = DocumentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        doc = form.save(commit=False)
        doc.matter, doc.uploaded_by = matter, request.user
        doc.save()
        AuditLog.record(request.user, "upload", doc, f"Uploaded {doc.title} to {matter.file_number}")
        messages.success(request, "Document uploaded.")
    else:
        errors = [e for field_errors in form.errors.values() for e in field_errors]
        messages.error(request, "Upload failed: " + (" ".join(errors) or "choose a file and give it a title."))
    return redirect(f"{matter.get_absolute_url()}?tab=documents")


def download_document(request, pk):
    """Documents are private: always served through this login-checked view, never as public files."""
    doc = get_object_or_404(Document, pk=pk)
    try:
        handle = doc.file.open("rb")
    except FileNotFoundError:
        raise Http404("The file is missing from storage.")
    # Only formats a browser can't execute script from may be shown inline.
    inline = request.GET.get("inline") == "1" and doc.file.name.lower().endswith((".pdf", ".png", ".jpg", ".jpeg"))
    return FileResponse(handle, as_attachment=not inline, filename=os.path.basename(doc.file.name))


def delete_document(request, pk):
    doc = get_object_or_404(Document, pk=pk)
    matter = doc.matter
    if request.method == "POST":
        AuditLog.record(request.user, "delete", doc, f"Deleted {doc.title} from {matter.file_number}")
        doc.file.delete(save=False)
        doc.delete()
        messages.success(request, "Document deleted.")
    return redirect(f"{matter.get_absolute_url()}?tab=documents")


def render_template_for(template_obj, matter, user):
    context = Context({
        "firm": FirmSettings.load(),
        "client": matter.client,
        "matter": matter,
        "author": user.get_full_name() or user.username,
        "today": timezone.localdate().strftime("%d %B %Y"),
    })
    return Template(template_obj.body).render(context)


def generate_document(request, pk):
    matter = get_object_or_404(Matter, pk=pk)
    form = GenerateDocumentForm(request.POST or None)
    if request.method != "POST" or not form.is_valid():
        return redirect(f"{matter.get_absolute_url()}?tab=documents")
    tpl = form.cleaned_data["template"]
    try:
        body = render_template_for(tpl, matter, request.user)
    except TemplateSyntaxError as exc:
        messages.error(request, f"Template error: {exc}")
        return redirect(f"{matter.get_absolute_url()}?tab=documents")
    html = (
        "<html><head><meta charset='utf-8'><title>{t}</title></head>"
        "<body style=\"font-family: 'Times New Roman', serif; font-size: 12pt\">{b}</body></html>"
    ).format(t=tpl.name, b=linebreaks(body) if "<" not in tpl.body else body)
    filename = f"{matter.file_number}-{slugify(tpl.name)}.doc"
    if form.cleaned_data["save_to_matter"]:
        doc = Document(matter=matter, title=tpl.name, uploaded_by=request.user)
        doc.file.save(filename, ContentFile(html.encode("utf-8")), save=True)
    response = HttpResponse(html, content_type="application/msword")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class TemplateList(ListView):
    model = DocumentTemplate


class TemplateCreate(PermissionMixin, CreateView):
    required_perm = "manage_templates"
    model = DocumentTemplate
    form_class = DocumentTemplateForm
    template_name = "form.html"
    extra_context = {"title": "New document template"}

    def get_success_url(self):
        return "/matters/templates/"


class TemplateUpdate(PermissionMixin, UpdateView):
    required_perm = "manage_templates"
    model = DocumentTemplate
    form_class = DocumentTemplateForm
    template_name = "form.html"
    extra_context = {"title": "Edit document template"}

    def get_success_url(self):
        return "/matters/templates/"

