from django.contrib import admin

from .models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "client_type", "email", "phone", "is_active")
    search_fields = ("code", "name", "email", "id_number")
