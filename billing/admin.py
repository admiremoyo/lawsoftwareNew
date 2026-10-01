from django.contrib import admin

from .models import Disbursement, Invoice, InvoiceItem, Payment, TimeEntry


class ReadOnlyAdmin(admin.ModelAdmin):
    """Financial records are changed only through the app, where the rules and audit log apply."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Invoice)
class InvoiceAdmin(ReadOnlyAdmin):
    list_display = ("number", "matter", "date", "status")
    list_filter = ("status",)


@admin.register(Payment)
class PaymentAdmin(ReadOnlyAdmin):
    list_display = ("invoice", "date", "amount", "method")


admin.site.register([TimeEntry, Disbursement, InvoiceItem], ReadOnlyAdmin)
