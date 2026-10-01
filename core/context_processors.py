from django.conf import settings
from django.db import DatabaseError

from .models import FirmSettings


def firm(request):
    product = {"product_name": settings.PRODUCT_NAME}
    try:
        return {"firm": FirmSettings.load(), **product}
    except DatabaseError:  # e.g. while rendering the 500 page during a database outage
        return {"firm": FirmSettings(name=settings.PRODUCT_NAME), **product}
