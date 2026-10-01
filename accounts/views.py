import base64
from io import BytesIO

import segno
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import PasswordChangeForm
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from core.forms import StyledFormMixin
from core.models import AuditLog, FirmSettings
from core.utils import safe_next

from . import totp
from .forms import LOCKED_MESSAGE, LockoutAuthenticationForm, SetupForm, TwoFactorCodeForm, UserForm, is_locked_out
from .models import LoginFailure, TwoFactorDevice
from .permissions import PERMISSIONS, require_perm
from .signals import client_ip

User = get_user_model()
PENDING_KEY = "2fa_pending"
PENDING_SECONDS = 300


# ---------------------------------------------------------------- sign in

class LoginView(auth_views.LoginView):
    form_class = LockoutAuthenticationForm
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        if not User.objects.exists():
            return redirect("setup")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.get_user()
        device = getattr(user, "two_factor", None)
        if device and device.confirmed:
            self.request.session[PENDING_KEY] = {
                "user": user.pk, "backend": user.backend, "at": timezone.now().timestamp(),
                "next": self.get_success_url(),
            }
            return redirect("login_2fa")
        return super().form_valid(form)


def login_2fa(request):
    pending = request.session.get(PENDING_KEY)
    if not pending or timezone.now().timestamp() - pending["at"] > PENDING_SECONDS:
        request.session.pop(PENDING_KEY, None)
        messages.error(request, "Your sign-in timed out. Please enter your password again.")
        return redirect("login")
    user = get_object_or_404(User, pk=pending["user"], is_active=True)
    form = TwoFactorCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ip = client_ip(request)
        if is_locked_out(user.get_username(), ip):
            form.add_error(None, LOCKED_MESSAGE.format(m=settings.LOGIN_LOCKOUT_MINUTES))
        else:
            device = user.two_factor
            step = totp.verify(device.secret, form.cleaned_data["code"], device.last_used_step)
            if step:
                device.last_used_step = step
                device.save(update_fields=["last_used_step"])
                del request.session[PENDING_KEY]
                login(request, user, backend=pending["backend"])
                return redirect(pending["next"] or settings.LOGIN_REDIRECT_URL)
            LoginFailure.objects.create(username=user.get_username(), ip_address=ip)
            form.add_error("code", "That code is not valid. Check your phone's clock and try again.")
    return render(request, "accounts/login_2fa.html", {"form": form})


def setup(request):
    """First-run wizard: create the firm and its first partner account."""
    if User.objects.exists():
        return redirect("login")
    form = SetupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        AuditLog.record(user, "setup", user, "Initial firm setup")
        messages.success(request, "Welcome! Complete your firm details, then add your colleagues under Users.")
        return redirect("firm_settings")
    return render(request, "accounts/setup.html", {"form": form})


# ---------------------------------------------------------------- my account

class StyledPasswordChangeForm(StyledFormMixin, PasswordChangeForm):
    pass


def my_account(request):
    form = StyledPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        update_session_auth_hash(request, form.user)
        AuditLog.record(request.user, "password", request.user, "Changed own password")
        messages.success(request, "Password changed.")
        return redirect("my_account")
    device = getattr(request.user, "two_factor", None)
    return render(request, "accounts/my_account.html", {
        "form": form, "two_factor_on": bool(device and device.confirmed),
    })


def _qr_data_uri(text):
    buf = BytesIO()
    segno.make(text, error="m").save(buf, kind="svg", scale=5, border=2)
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()


def two_factor_setup(request):
    device, _ = TwoFactorDevice.objects.get_or_create(user=request.user, defaults={"secret": totp.new_secret()})
    if device.confirmed:
        messages.info(request, "Two-factor sign-in is already on.")
        return redirect("my_account")
    form = TwoFactorCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        step = totp.verify(device.secret, form.cleaned_data["code"])
        if step:
            device.confirmed, device.last_used_step = True, step
            device.save()
            AuditLog.record(request.user, "2fa", request.user, "Turned on two-factor sign-in")
            messages.success(request, "Two-factor sign-in is now on. You'll need your phone each time you sign in.")
            return redirect(safe_next(request, reverse("my_account")))
        form.add_error("code", "That code is not valid. Scan the QR code again and enter the current code.")
    uri = totp.provisioning_uri(device.secret, request.user.get_username(), FirmSettings.load().name)
    return render(request, "accounts/two_factor_setup.html", {
        "form": form, "qr": _qr_data_uri(uri), "secret": device.secret,
        "required": FirmSettings.load().require_two_factor,
    })


def two_factor_disable(request):
    if request.method == "POST":
        if FirmSettings.load().require_two_factor:
            messages.error(request, "Your firm requires two-factor sign-in, so it can't be turned off.")
        elif not request.user.check_password(request.POST.get("password", "")):
            messages.error(request, "Incorrect password.")
        else:
            TwoFactorDevice.objects.filter(user=request.user).delete()
            AuditLog.record(request.user, "2fa", request.user, "Turned off two-factor sign-in")
            messages.success(request, "Two-factor sign-in turned off.")
    return redirect("my_account")


# ---------------------------------------------------------------- user management

@require_perm("manage_users")
def user_list(request):
    users = User.objects.select_related("profile").order_by("-is_active", "first_name", "username")
    devices = set(TwoFactorDevice.objects.filter(confirmed=True).values_list("user_id", flat=True))
    return render(request, "accounts/user_list.html", {
        "users": users, "devices": devices,
        "permissions": [(key, label, sorted(roles)) for key, (label, roles) in PERMISSIONS.items()],
    })


@require_perm("manage_users")
def user_form(request, pk=None):
    obj = get_object_or_404(User, pk=pk) if pk else None
    if obj and obj.is_superuser and not request.user.is_superuser:
        raise PermissionDenied("Only an administrator can edit an administrator.")
    form = UserForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        if obj and obj.pk == request.user.pk and not form.cleaned_data.get("is_active", True):
            form.add_error("is_active", "You can't deactivate your own account.")
        else:
            user = form.save()
            AuditLog.record(request.user, "update" if obj else "create", user,
                            f"{'Updated' if obj else 'Created'} user {user.username} ({user.profile.role})")
            messages.success(request, f"User {user.username} saved.")
            return redirect("user_list")
    return render(request, "form.html", {"form": form, "title": f"Edit {obj.username}" if obj else "New user"})


@require_perm("manage_users")
def user_reset_two_factor(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        TwoFactorDevice.objects.filter(user=user).delete()
        LoginFailure.objects.filter(username=user.username).delete()
        AuditLog.record(request.user, "2fa", user, f"Reset two-factor sign-in and lockout for {user.username}")
        messages.success(request, f"Two-factor sign-in reset for {user.username}. They will set it up again at next sign-in.")
    return redirect("user_list")


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/password_reset_email.txt"
    subject_template_name = "accounts/password_reset_subject.txt"
    extra_email_context = {"product_name": settings.PRODUCT_NAME}
    MAX_PER_HOUR = 5

    def form_valid(self, form):
        # Limit reset emails per address and per IP so the form can't be used to flood inboxes.
        keys = [f"pwreset:ip:{client_ip(self.request)}", f"pwreset:email:{form.cleaned_data['email'].lower()}"]
        if any(cache.get(k, 0) >= self.MAX_PER_HOUR for k in keys):
            return redirect(self.get_success_url())  # same response either way: reveals nothing
        for k in keys:
            cache.set(k, cache.get(k, 0) + 1, 3600)
        return super().form_valid(form)


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        for field in form.fields.values():
            field.widget.attrs["class"] = "form-control"
        return form
