from django.contrib import admin

from .models import Document, DocumentTemplate, FileNote, Matter


@admin.register(Matter)
class MatterAdmin(admin.ModelAdmin):
    list_display = ("file_number", "description", "client", "matter_type", "status", "responsible")
    list_filter = ("status", "matter_type")
    search_fields = ("file_number", "description", "client__name")


admin.site.register([FileNote, Document, DocumentTemplate])
