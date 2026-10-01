from django.conf import settings
from django.db import models


class LoginFailure(models.Model):
    """Failed sign-in attempts, used to lock out password guessing."""

    username = models.CharField(max_length=150, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-timestamp"]


class TwoFactorDevice(models.Model):
    """Authenticator-app (TOTP) secret for a user."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="two_factor")
    secret = models.CharField(max_length=64)
    confirmed = models.BooleanField(default=False)
    last_used_step = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"2FA for {self.user}"
