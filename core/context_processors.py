from django.db import DatabaseError

from .models import FirmSettings


def firm(request):
    try:
        return {"firm": FirmSettings.load()}
    except DatabaseError:  # e.g. while rendering the 500 page during a database outage
        return {"firm": FirmSettings(name="LawPractice")}
