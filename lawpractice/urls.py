from django.contrib import admin
from django.urls import include, path

from core.views import health

admin.site.site_header = "LawPractice administration"
admin.site.site_title = "LawPractice"

urlpatterns = [
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("core.urls")),
    path("clients/", include("clients.urls")),
    path("matters/", include("matters.urls")),
    path("billing/", include("billing.urls")),
    path("trust/", include("trust.urls")),
    path("diary/", include("diary.urls")),
]

handler403 = "core.views.permission_denied"
handler404 = "core.views.not_found"
handler500 = "core.views.server_error"
