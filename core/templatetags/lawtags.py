from decimal import Decimal

from django import template
from django.contrib.humanize.templatetags.humanize import intcomma

from core.models import FirmSettings

register = template.Library()


@register.filter
def money(value):
    """Format a number as currency using the firm's currency symbol."""
    if value in (None, ""):
        value = Decimal("0")
    value = Decimal(value).quantize(Decimal("0.01"))
    symbol = FirmSettings.load().currency_symbol
    sign = "-" if value < 0 else ""
    whole, cents = f"{abs(value):.2f}".split(".")
    return f"{sign}{symbol}{intcomma(int(whole))}.{cents}"


@register.filter
def hours(minutes):
    minutes = int(minutes or 0)
    return f"{minutes // 60}:{minutes % 60:02d}"
