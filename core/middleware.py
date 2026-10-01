from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect

PUBLIC_PREFIXES = ("/login/", "/setup/", "/password-reset/", "/reset/", "/static/", "/health/")
TWO_FACTOR_EXEMPT = ("/account/2fa/", "/logout/", "/static/", "/health/")


class LoginRequiredMiddleware:
    """Every page requires a signed-in user, except sign-in, password reset and first-run setup.

    When the firm requires two-factor sign-in, users who haven't set it up are sent to do so first.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        user = request.user
        if not user.is_authenticated:
            if not path.startswith(PUBLIC_PREFIXES):
                return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        elif not path.startswith(TWO_FACTOR_EXEMPT):
            from core.models import FirmSettings

            if FirmSettings.load().require_two_factor:
                device = getattr(user, "two_factor", None)
                if not (device and device.confirmed):
                    return redirect(f"/account/2fa/?next={path}")
        return self.get_response(request)


class SecurityHeadersMiddleware:
    """Content-Security-Policy and related headers. All assets are served locally."""

    CSP = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; font-src 'self'; frame-ancestors 'none'; "
        "form-action 'self'; base-uri 'self'; object-src 'none'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", self.CSP)
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.user.is_authenticated and not request.path.startswith("/static/"):
            # Client data must not be kept in shared/browser caches.
            response.setdefault("Cache-Control", "no-store")
        return response
