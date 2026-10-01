"""Role-based permissions.

Each user has a role on their profile. A permission is granted when the user's role is listed for it.
Superusers have every permission.
"""
from functools import wraps

from django.core.exceptions import PermissionDenied

PARTNER, ASSOCIATE, CANDIDATE, SECRETARY, BOOKKEEPER = "partner", "associate", "candidate", "secretary", "bookkeeper"

PERMISSIONS = {
    "manage_users": ("Add and edit users", {PARTNER}),
    "firm_settings": ("Change firm settings", {PARTNER}),
    "audit_log": ("View the audit log", {PARTNER, BOOKKEEPER}),
    "trust_post": ("Post trust receipts, payments and transfers", {PARTNER, BOOKKEEPER}),
    "trust_reverse": ("Reverse trust entries", {PARTNER, BOOKKEEPER}),
    "trust_reconcile": ("Reconcile the trust bank account", {PARTNER, BOOKKEEPER}),
    "trust_view": ("View the trust cash book and reports", {PARTNER, BOOKKEEPER, ASSOCIATE}),
    "invoice_issue": ("Draft and issue fee notes", {PARTNER, BOOKKEEPER, ASSOCIATE}),
    "invoice_void": ("Void fee notes and reverse payments", {PARTNER, BOOKKEEPER}),
    "payment_record": ("Record fee payments", {PARTNER, BOOKKEEPER, SECRETARY}),
    "accounting": ("Business accounting, VAT and income reports", {PARTNER, BOOKKEEPER}),
    "financial_reports": ("Debtors, WIP and fee earner reports", {PARTNER, BOOKKEEPER}),
    "manage_templates": ("Manage precedents and workflows", {PARTNER, ASSOCIATE, SECRETARY}),
    "import_data": ("Import clients from CSV", {PARTNER, BOOKKEEPER}),
}


def role_of(user):
    profile = getattr(user, "profile", None)
    return profile.role if profile else None


def has_perm(user, perm):
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return role_of(user) in PERMISSIONS[perm][1]


def require_perm(perm):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not has_perm(request.user, perm):
                raise PermissionDenied(PERMISSIONS[perm][0])
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


class PermissionMixin:
    required_perm = None

    def dispatch(self, request, *args, **kwargs):
        if self.required_perm and not has_perm(request.user, self.required_perm):
            raise PermissionDenied(PERMISSIONS[self.required_perm][0])
        return super().dispatch(request, *args, **kwargs)


class _Can:
    def __init__(self, user):
        self.user = user

    def __getitem__(self, perm):
        return has_perm(self.user, perm)

    def __contains__(self, perm):
        return perm in PERMISSIONS


def can(request):
    """Context processor: {% if can.trust_post %} in templates."""
    return {"can": _Can(request.user) if hasattr(request, "user") else {}}
