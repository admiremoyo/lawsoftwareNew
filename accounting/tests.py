from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from billing.models import Invoice, Payment, TimeEntry
from clients.models import Client
from matters.models import Matter
from trust import services as trust

from .models import BusinessTransaction, Category, vat_from_gross

TODAY = date(2026, 10, 1)


class AccountingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("pat", "pat@firm.test", "pw-long-enough-123",
                                                         first_name="Pat", last_name="Partner")
        self.user.profile.role = "partner"
        self.user.profile.hourly_rate = Decimal("100")
        self.user.profile.save()
        self.client_obj = Client.objects.create(name="Acme Ltd", email="acme@example.com")
        self.matter = Matter.objects.create(client=self.client_obj, description="Acme v Beta",
                                            responsible=self.user, date_opened=TODAY)
        TimeEntry.objects.create(matter=self.matter, user=self.user, date=TODAY, description="Work", minutes=60)
        self.invoice = Invoice.objects.create(matter=self.matter, date=TODAY, created_by=self.user)
        self.matter.time_entries.update(invoice=self.invoice)
        self.invoice.status = "issued"
        self.invoice.save()  # 100 + 15 VAT = 115
        self.client.force_login(self.user)

    def expense(self, amount, standard_vat=False, category="Rent"):
        return self.client.post(reverse("business_expense"), {
            "date": TODAY.isoformat(), "category": Category.objects.get(name=category).pk, "party": "Landlord",
            "description": "October rent", "amount": amount, "standard_vat": "on" if standard_vat else "",
        })

    def test_default_categories_seeded(self):
        self.assertTrue(Category.objects.filter(name="Fee income", system=True).exists())
        self.assertTrue(Category.objects.filter(name="Rent", kind="expense").exists())

    def test_vat_from_gross(self):
        self.assertEqual(vat_from_gross(Decimal("115"), Decimal("15")), Decimal("15.00"))

    def test_fee_payment_posts_to_business_account_and_reversal_removes_it(self):
        payment = Payment.objects.create(invoice=self.invoice, date=TODAY, amount=Decimal("115"), created_by=self.user)
        tx = BusinessTransaction.objects.get(payment=payment)
        self.assertEqual(tx.category.name, "Fee income")
        self.assertEqual(BusinessTransaction.balance(), Decimal("115"))
        self.client.post(reverse("payment_reverse", args=[payment.pk]), {"reason": "bounced"})
        self.assertEqual(BusinessTransaction.balance(), Decimal("0"))

    def test_trust_fee_transfer_reaches_business_account(self):
        trust.receive(self.matter, Decimal("500"), self.user, date=TODAY, party="Acme", description="Deposit")
        trust.transfer_fees(self.invoice, Decimal("115"), self.user, date=TODAY)
        self.assertEqual(BusinessTransaction.balance(), Decimal("115"))

    def test_expense_with_standard_vat_and_vat_report(self):
        self.expense("1150", standard_vat=True)
        tx = BusinessTransaction.objects.get(category__name="Rent")
        self.assertEqual(tx.vat_amount, Decimal("150.00"))
        self.assertEqual(tx.signed_amount, Decimal("-1150"))
        resp = self.client.get(reverse("vat_report"), {"start": "2026-10-01", "end": "2026-10-31"})
        self.assertEqual(resp.context["output_vat"], Decimal("15.00"))
        self.assertEqual(resp.context["input_vat"], Decimal("150.00"))
        self.assertEqual(resp.context["net"], Decimal("-135.00"))

    def test_vat_payments_basis(self):
        Payment.objects.create(invoice=self.invoice, date=TODAY, amount=Decimal("57.50"), created_by=self.user)
        resp = self.client.get(reverse("vat_report"), {"start": "2026-10-01", "end": "2026-10-31", "basis": "payments"})
        self.assertEqual(resp.context["output_vat"], Decimal("7.50"))

    def test_income_statement(self):
        self.expense("1150", standard_vat=True)
        resp = self.client.get(reverse("income_statement"), {"start": "2026-01-01", "end": "2026-12-31"})
        self.assertEqual(resp.context["fees"], Decimal("100.00"))
        self.assertEqual(resp.context["total_expenses"], Decimal("1000.00"))
        self.assertEqual(resp.context["profit"], Decimal("-900.00"))

    def test_automatic_entries_cannot_be_edited(self):
        payment = Payment.objects.create(invoice=self.invoice, date=TODAY, amount=Decimal("10"), created_by=self.user)
        tx = payment.business_transaction
        self.client.post(reverse("business_entry_delete", args=[tx.pk]))
        self.assertTrue(BusinessTransaction.objects.filter(pk=tx.pk).exists())

    def test_statement_running_balance(self):
        Payment.objects.create(invoice=self.invoice, date=TODAY, amount=Decimal("15"), created_by=self.user)
        resp = self.client.get(reverse("client_statement", args=[self.client_obj.pk]))
        self.assertEqual(resp.context["closing"], Decimal("100.00"))
        self.assertEqual([line["balance"] for line in resp.context["lines"]], [Decimal("115.00"), Decimal("100.00")])

    def test_pdfs_render(self):
        resp = self.client.get(reverse("invoice_pdf", args=[self.invoice.pk]))
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))
        resp = self.client.get(reverse("client_statement", args=[self.client_obj.pk]), {"format": "pdf"})
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_email_invoice_with_pdf(self):
        resp = self.client.post(reverse("invoice_email", args=[self.invoice.pk]), {
            "to": "acme@example.com", "subject": "Fee note", "message": "Please pay",
        })
        self.assertRedirects(resp, self.invoice.get_absolute_url())
        self.assertEqual(len(mail.outbox), 1)
        name, content, mimetype = mail.outbox[0].attachments[0]
        self.assertEqual(name, "INV00001.pdf")
        self.assertTrue(content.startswith(b"%PDF"))
        self.assertEqual(mail.outbox[0].cc, ["pat@firm.test"])

    def test_email_statement(self):
        self.client.post(reverse("email_statement", args=[self.client_obj.pk]), {
            "to": "acme@example.com", "subject": "Statement", "message": "Hi",
        })
        self.assertEqual(len(mail.outbox), 1)

    def test_associate_cannot_see_accounting(self):
        assoc = get_user_model().objects.create_user("sam", password="pw-long-enough-123")
        self.client.force_login(assoc)
        self.assertEqual(self.client.get(reverse("business_cashbook")).status_code, 403)
