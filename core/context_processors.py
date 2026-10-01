from .models import FirmSettings


def firm(request):
    return {"firm": FirmSettings.load()}
