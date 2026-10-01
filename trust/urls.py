from django.urls import path

from . import views

urlpatterns = [
    path("", views.cashbook, name="trust_cashbook"),
    path("receipt/", views.receipt, name="trust_receipt"),
    path("receipt/<int:pk>/print/", views.receipt_print, name="trust_receipt_print"),
    path("payment/", views.payment, name="trust_payment"),
    path("transfer/", views.matter_transfer, name="trust_transfer"),
    path("fees/<int:invoice_pk>/", views.fee_transfer, name="trust_fee_transfer"),
    path("<int:pk>/reverse/", views.reverse, name="trust_reverse"),
    path("reconciliations/", views.reconciliation_list, name="trust_reconciliation_list"),
    path("reconciliations/new/", views.reconciliation_new, name="trust_reconciliation_new"),
    path("reconciliations/<int:pk>/", views.reconciliation_detail, name="trust_reconciliation_detail"),
]
