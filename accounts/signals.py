from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from core.models import AuditLog

from .models import LoginFailure


def client_ip(request):
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR")) or None


@receiver(user_login_failed)
def record_failure(sender, credentials, request=None, **kwargs):
    LoginFailure.objects.create(username=(credentials.get("username") or "")[:150], ip_address=client_ip(request))


@receiver(user_logged_in)
def record_login(sender, request, user, **kwargs):
    LoginFailure.objects.filter(username=user.get_username()).delete()
    AuditLog.record(user, "login", user, f"Signed in from {client_ip(request)}")


@receiver(user_logged_out)
def record_logout(sender, request, user, **kwargs):
    if user:
        AuditLog.record(user, "logout", user, "Signed out")
