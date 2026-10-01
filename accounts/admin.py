from django.contrib import admin

from .models import LoginFailure, TwoFactorDevice


@admin.register(LoginFailure)
class LoginFailureAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "username", "ip_address")


@admin.register(TwoFactorDevice)
class TwoFactorDeviceAdmin(admin.ModelAdmin):
    list_display = ("user", "confirmed", "created_at")
    exclude = ("secret",)
