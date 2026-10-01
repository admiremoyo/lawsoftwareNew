from django.contrib import admin

from .models import Disbursement, Invoice, InvoiceItem, Payment, TimeEntry

admin.site.register([Invoice, InvoiceItem, TimeEntry, Disbursement, Payment])
