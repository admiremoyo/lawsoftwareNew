from django.contrib import admin

from .models import AuditLog, FirmSettings, UserProfile

admin.site.register(FirmSettings)
admin.site.register(UserProfile)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user", "action", "object_type", "description")
    list_filter = ("action", "object_type")
    readonly_fields = [f.name for f in AuditLog._meta.fields]
