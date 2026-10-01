from django.contrib import admin

from .models import BusinessTransaction, Category

admin.site.register(Category)


@admin.register(BusinessTransaction)
class BusinessTransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "type", "category", "description", "amount", "vat_amount")
    list_filter = ("type", "category")
