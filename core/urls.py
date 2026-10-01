from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("search/", views.search, name="search"),
    path("settings/", views.firm_settings, name="firm_settings"),
    path("audit/", views.audit_log, name="audit_log"),
    path("reports/", views.reports, name="reports"),
    path("reports/wip/", views.report_wip, name="report_wip"),
    path("reports/debtors/", views.report_debtors, name="report_debtors"),
    path("reports/trust/", views.report_trust, name="report_trust"),
    path("reports/time/", views.report_time, name="report_time"),
    path("reports/matters/", views.report_matters, name="report_matters"),
]
