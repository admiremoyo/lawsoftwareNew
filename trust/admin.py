from django.contrib import admin

from .models import TrustReconciliation, TrustTransaction


@admin.register(TrustTransaction)
class TrustTransactionAdmin(admin.ModelAdmin):
    """Read-only: trust entries must be created through the app so the rules apply."""

    list_display = ("date", "matter", "type", "amount", "description", "reconciled")
    list_filter = ("type", "reconciled")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


from billing.admin import ReadOnlyAdmin  # noqa: E402

admin.site.register(TrustReconciliation, ReadOnlyAdmin)
