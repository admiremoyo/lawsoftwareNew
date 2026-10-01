from django.urls import path

from . import views

urlpatterns = [
    path("time/", views.TimeEntryList.as_view(), name="time_list"),
    path("time/new/", views.time_entry_form, name="time_create"),
    path("time/<int:pk>/edit/", views.time_entry_form, name="time_edit"),
    path("time/<int:pk>/delete/", views.time_entry_delete, name="time_delete"),
    path("disbursements/new/", views.disbursement_form, name="disbursement_create"),
    path("disbursements/<int:pk>/edit/", views.disbursement_form, name="disbursement_edit"),
    path("disbursements/<int:pk>/delete/", views.disbursement_delete, name="disbursement_delete"),
    path("invoices/", views.InvoiceList.as_view(), name="invoice_list"),
    path("invoices/new/<int:matter_pk>/", views.invoice_create, name="invoice_create"),
    path("invoices/<int:pk>/", views.invoice_detail, name="invoice_detail"),
    path("invoices/<int:pk>/print/", views.invoice_print, name="invoice_print"),
    path("invoices/<int:pk>/edit/", views.invoice_edit, name="invoice_edit"),
    path("invoices/<int:pk>/payment/", views.payment_add, name="payment_add"),
    path("payments/<int:pk>/reverse/", views.payment_reverse, name="payment_reverse"),
    path("invoices/<int:pk>/<str:action>/", views.invoice_action, name="invoice_action"),
]
