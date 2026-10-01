from django.urls import path

from . import views

urlpatterns = [
    path("", views.cashbook, name="business_cashbook"),
    path("income/new/", views.entry_form, {"kind": "income"}, name="business_income"),
    path("expense/new/", views.entry_form, {"kind": "expense"}, name="business_expense"),
    path("entries/<int:pk>/", views.entry_form, {"kind": None}, name="business_entry_edit"),
    path("entries/<int:pk>/delete/", views.entry_delete, name="business_entry_delete"),
    path("categories/", views.categories, name="accounting_categories"),
    path("vat/", views.vat_report, name="vat_report"),
    path("income-statement/", views.income_statement, name="income_statement"),
    path("statement/<int:client_pk>/", views.statement, name="client_statement"),
    path("statement/<int:client_pk>/email/", views.email_statement, name="email_statement"),
]
