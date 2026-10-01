"""Safe mail-merge for precedents.

Precedents are written by staff, so they must never reach live database objects: a template such as
{{ matter.invoices.first.void }} would otherwise call that method. Templates only ever see plain
dictionaries of values, rendered by an isolated engine that cannot include or load other templates.
"""
from django.template import Context, Engine
from django.utils import timezone

ENGINE = Engine(loaders=[], libraries={}, builtins=["django.template.defaulttags", "django.template.defaultfilters"],
                autoescape=True)
BLOCKED_TAGS = ("{% include", "{% extends", "{% load", "{% debug", "{% ssi")

FIRM_FIELDS = ["name", "address", "phone", "email", "vat_number", "business_bank_details", "trust_bank_name",
               "trust_account_number"]
CLIENT_FIELDS = ["code", "name", "id_number", "vat_number", "contact_person", "email", "phone", "physical_address",
                 "postal_address"]
MATTER_FIELDS = ["file_number", "description", "opposing_party", "opposing_attorney", "court", "case_number"]


class UnsafeTemplate(ValueError):
    pass


def _values(obj, fields):
    return {f: getattr(obj, f) or "" for f in fields}


def merge_context(firm, matter, user):
    client = matter.client
    fmt = "%d %B %Y"
    return {
        "firm": _values(firm, FIRM_FIELDS),
        "client": {**_values(client, CLIENT_FIELDS), "client_type": client.get_client_type_display()},
        "matter": {
            **_values(matter, MATTER_FIELDS),
            "matter_type": matter.get_matter_type_display(),
            "date_opened": matter.date_opened.strftime(fmt) if matter.date_opened else "",
            "prescription_date": matter.prescription_date.strftime(fmt) if matter.prescription_date else "",
            "responsible": matter.responsible.get_full_name() or matter.responsible.username,
            "trust_balance": f"{matter.trust_balance:,.2f}",
        },
        "author": user.get_full_name() or user.username,
        "today": timezone.localdate().strftime(fmt),
    }


def render_precedent(body, firm, matter, user):
    lowered = body.replace("{%-", "{%").lower()
    for tag in BLOCKED_TAGS:
        if tag in lowered.replace("{%  ", "{% "):
            raise UnsafeTemplate(f"Precedents can't use the '{tag[3:]}' tag.")
    return ENGINE.from_string(body).render(Context(merge_context(firm, matter, user)))
