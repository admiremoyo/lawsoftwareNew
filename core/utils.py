from django.utils.http import url_has_allowed_host_and_scheme


def safe_next(request, default):
    """The ?next= / POST next URL if it points at this site, otherwise the default."""
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}, require_https=request.is_secure()):
        return nxt
    return default
