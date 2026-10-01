from django.contrib import messages
from django.db.models import Count, Q
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from core.models import AuditLog

from .forms import ClientForm
from .models import Client


class ClientList(ListView):
    model = Client
    paginate_by = 50

    def get_queryset(self):
        qs = Client.objects.annotate(matter_count=Count("matters")).order_by("name")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(name__icontains=q) | Q(code__icontains=q) | Q(email__icontains=q)
                | Q(id_number__icontains=q) | Q(phone__icontains=q)
            )
        return qs


class ClientDetail(DetailView):
    model = Client


class ClientCreate(CreateView):
    model = Client
    form_class = ClientForm
    template_name = "form.html"
    extra_context = {"title": "New client"}

    def form_valid(self, form):
        response = super().form_valid(form)
        AuditLog.record(self.request.user, "create", self.object)
        messages.success(self.request, f"Client {self.object.code} created.")
        return response


class ClientUpdate(UpdateView):
    model = Client
    form_class = ClientForm
    template_name = "form.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(title=f"Edit {self.object}", **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        AuditLog.record(self.request.user, "update", self.object)
        messages.success(self.request, "Client updated.")
        return response
