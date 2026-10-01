from django.conf import settings
from django.contrib.auth.views import redirect_to_login

PUBLIC_PREFIXES = ("/login/", "/admin/", "/static/")


class LoginRequiredMiddleware:
    """Every page requires a signed-in user except the login page and admin."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated and not request.path.startswith(PUBLIC_PREFIXES):
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        return self.get_response(request)
