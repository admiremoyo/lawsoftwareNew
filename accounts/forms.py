from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Q
from django.utils import timezone

from core.forms import StyledFormMixin
from core.models import FirmSettings, UserProfile

from .models import LoginFailure
from .signals import client_ip

User = get_user_model()


def is_locked_out(username, ip):
    since = timezone.now() - timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
    recent = LoginFailure.objects.filter(timestamp__gte=since)
    by_user = recent.filter(username=username).count() if username else 0
    by_ip = recent.filter(ip_address=ip).count() if ip else 0
    # An IP gets more leeway than a single account (several staff share an office IP).
    return by_user >= settings.LOGIN_MAX_FAILURES or by_ip >= settings.LOGIN_MAX_FAILURES * 4


LOCKED_MESSAGE = "Too many failed sign-in attempts. Wait {m} minutes and try again, or ask a partner to reset your password."


class LockoutAuthenticationForm(StyledFormMixin, AuthenticationForm):
    def clean(self):
        username = self.cleaned_data.get("username", "")
        if is_locked_out(username, client_ip(self.request)):
            raise forms.ValidationError(LOCKED_MESSAGE.format(m=settings.LOGIN_LOCKOUT_MINUTES), code="locked")
        return super().clean()


class TwoFactorCodeForm(StyledFormMixin, forms.Form):
    code = forms.CharField(max_length=10, label="6-digit code from your authenticator app",
                           widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric",
                                                         "autofocus": True}))


class UserForm(StyledFormMixin, forms.ModelForm):
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES)
    initials = forms.CharField(max_length=5, required=False)
    hourly_rate = forms.DecimalField(max_digits=10, decimal_places=2, required=False,
                                     help_text="Leave blank to use the firm's default rate.")
    password = forms.CharField(widget=forms.PasswordInput, required=False,
                               help_text="Required for new users. At least 10 characters.")

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["email"].required = True
        if self.instance.pk:
            profile = self.instance.profile
            self.initial.update(role=profile.role, initials=profile.initials, hourly_rate=profile.hourly_rate)
            self.fields["password"].help_text = "Leave blank to keep the current password."
        else:
            self.fields["password"].required = True
            del self.fields["is_active"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Another user already has this email address.")
        return email

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            password_validation.validate_password(password, self.instance)
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("password"):
            user.set_password(self.cleaned_data["password"])
        user.save()
        profile = user.profile
        profile.role = self.cleaned_data["role"]
        profile.initials = self.cleaned_data["initials"]
        profile.hourly_rate = self.cleaned_data["hourly_rate"]
        profile.save()
        return user


class SetupForm(StyledFormMixin, forms.Form):
    firm_name = forms.CharField(max_length=200, label="Firm name")
    currency_symbol = forms.CharField(max_length=5, initial="$")
    vat_rate = forms.DecimalField(max_digits=5, decimal_places=2, initial=15, label="VAT rate (%)")
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput, help_text="At least 10 characters.")
    password_confirm = forms.CharField(widget=forms.PasswordInput, label="Confirm password")

    def clean(self):
        data = super().clean()
        if data.get("password") and data.get("password") != data.get("password_confirm"):
            self.add_error("password_confirm", "Passwords do not match.")
        elif data.get("password"):
            try:
                password_validation.validate_password(data["password"], User(username=data.get("username", "")))
            except forms.ValidationError as exc:
                self.add_error("password", exc)
        return data

    def save(self):
        data = self.cleaned_data
        firm = FirmSettings.load()
        firm.name, firm.currency_symbol, firm.vat_rate = data["firm_name"], data["currency_symbol"], data["vat_rate"]
        firm.email = data["email"]
        firm.save()
        user = User.objects.create_superuser(data["username"], data["email"], data["password"],
                                             first_name=data["first_name"], last_name=data["last_name"])
        user.profile.role = "partner"
        user.profile.initials = (data["first_name"][:1] + data["last_name"][:1]).upper()
        user.profile.save()
        return user


def find_active_user(identifier):
    return User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier), is_active=True).first()
