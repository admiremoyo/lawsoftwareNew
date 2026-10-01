from django.contrib import admin

from billing.admin import ReadOnlyAdmin

from .models import BusinessTransaction, Category

admin.site.register(Category)


@admin.register(BusinessTransaction)
class BusinessTransactionAdmin(ReadOnlyAdmin):
    list_display = ("date", "type", "category", "description", "amount", "vat_amount")
    list_filter = ("type", "category")
