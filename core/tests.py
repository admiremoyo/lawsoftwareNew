import shutil
import tempfile
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from billing.models import Disbursement, Invoice, InvoiceItem, Payment, TimeEntry
from clients.models import Client
from core.models import FirmSettings
from matters.models import DocumentTemplate, Matter
from trust import services as trust
from trust.models import TrustReconciliation, TrustTransaction

TODAY = date(2026, 10, 1)


class Base(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("partner", password="pw", first_name="Pat",
                                                         last_name="Partner", is_staff=True)
        self.user.profile.role = "partner"
        self.user.profile.hourly_rate = Decimal("200")
        self.user.profile.save()
        self.client_obj = Client.objects.create(name="Acme Ltd")
        self.matter = Matter.objects.create(client=self.client_obj, description="Acme v Beta",
                                            responsible=self.user, date_opened=TODAY)
        self.other = Matter.objects.create(client=self.client_obj, description="Second matter",
                                           responsible=self.user, date_opened=TODAY)
        self.client.force_login(self.user)

    def issued_invoice(self, minutes=60):
        TimeEntry.objects.create(matter=self.matter, user=self.user, date=TODAY, description="Work", minutes=minutes)
        inv = Invoice.objects.create(matter=self.matter, date=TODAY, created_by=self.user)
        self.matter.time_entries.update(invoice=inv)
        inv.status = "issued"
        inv.save()
        return inv


class NumberingTests(Base):
    def test_sequential_numbers_with_prefixes(self):
        self.assertEqual(self.client_obj.code, "CL00001")
        self.assertEqual(self.matter.file_number, "MAT00001")
        self.assertEqual(self.other.file_number, "MAT00002")
        inv = Invoice.objects.create(matter=self.matter, created_by=self.user)
        self.assertEqual(inv.number, "INV00001")


class TimeAndInvoiceTests(Base):
    def test_time_entry_uses_fee_earner_rate_then_matter_override(self):
        t = TimeEntry.objects.create(matter=self.matter, user=self.user, description="x", minutes=90)
        self.assertEqual(t.rate, Decimal("200"))
        self.assertEqual(t.amount, Decimal("300.00"))
        self.matter.hourly_rate = Decimal("100")
        self.matter.save()
        t2 = TimeEntry.objects.create(matter=self.matter, user=self.user, description="y", minutes=30)
        self.assertEqual(t2.amount, Decimal("50.00"))

    def test_invoice_totals_and_vat(self):
        inv = Invoice.objects.create(matter=self.matter, date=TODAY, created_by=self.user)
        self.assertEqual(inv.vat_rate, Decimal("15.00"))
        self.assertEqual(inv.due_date, TODAY + timedelta(days=30))
        TimeEntry.objects.create(matter=self.matter, user=self.user, description="t", minutes=60, invoice=inv)
        InvoiceItem.objects.create(invoice=inv, description="Fixed", amount=Decimal("100"))
        Disbursement.objects.create(matter=self.matter, description="Sheriff", amount=Decimal("50"),
                                    vat_applicable=True, invoice=inv, created_by=self.user)
        Disbursement.objects.create(matter=self.matter, description="Court fee", amount=Decimal("20"),
                                    invoice=inv, created_by=self.user)
        self.assertEqual(inv.fees, Decimal("300.00"))
        self.assertEqual(inv.vat, Decimal("52.50"))  # 15% of (300 + 50)
        self.assertEqual(inv.total, Decimal("422.50"))

    def test_create_issue_pay_flow_through_views(self):
        TimeEntry.objects.create(matter=self.matter, user=self.user, description="t", minutes=60)
        entry = self.matter.time_entries.get()
        resp = self.client.post(reverse("invoice_create", args=[self.matter.pk]), {
            "date": TODAY.isoformat(), "time_entries": [entry.pk],
        })
        inv = Invoice.objects.get()
        self.assertRedirects(resp, inv.get_absolute_url())
        self.assertEqual(inv.status, "draft")
        self.client.post(reverse("invoice_action", args=[inv.pk, "issue"]))
        inv.refresh_from_db()
        self.assertEqual(inv.status, "issued")
        self.client.post(reverse("payment_add", args=[inv.pk]), {
            "date": TODAY.isoformat(), "amount": "230.00", "method": "eft",
        })
        inv.refresh_from_db()
        self.assertEqual(inv.status, "paid")
        self.assertEqual(inv.balance, 0)

    def test_overpayment_rejected(self):
        inv = self.issued_invoice()
        self.client.post(reverse("payment_add", args=[inv.pk]), {
            "date": TODAY.isoformat(), "amount": "9999", "method": "eft",
        })
        self.assertFalse(inv.payments.exists())

    def test_void_releases_work_and_billed_time_is_locked(self):
        inv = self.issued_invoice()
        entry = inv.time_entries.get()
        resp = self.client.post(reverse("time_delete", args=[entry.pk]))
        self.assertTrue(TimeEntry.objects.filter(pk=entry.pk).exists())
        self.client.post(reverse("invoice_action", args=[inv.pk, "void"]))
        inv.refresh_from_db()
        entry.refresh_from_db()
        self.assertEqual(inv.status, "void")
        self.assertIsNone(entry.invoice)
        self.assertEqual(resp.status_code, 302)

    def test_cannot_void_invoice_with_payments(self):
        inv = self.issued_invoice()
        Payment.objects.create(invoice=inv, amount=Decimal("10"), created_by=self.user)
        self.client.post(reverse("invoice_action", args=[inv.pk, "void"]))
        inv.refresh_from_db()
        self.assertEqual(inv.status, "issued")


class TrustTests(Base):
    def receive(self, amount, matter=None):
        return trust.receive(matter or self.matter, Decimal(amount), self.user, date=TODAY,
                             party="Client", description="Deposit")

    def test_receipt_and_payment_balance(self):
        self.receive("1000")
        trust.pay(self.matter, Decimal("300"), self.user, date=TODAY, party="Sheriff", description="Fees")
        self.assertEqual(self.matter.trust_balance, Decimal("700"))
        self.assertEqual(TrustTransaction.total_balance(), Decimal("700"))

    def test_matter_can_never_be_overdrawn(self):
        self.receive("100")
        with self.assertRaises(ValidationError):
            trust.pay(self.matter, Decimal("100.01"), self.user, date=TODAY, party="X", description="Y")
        # Money held for another client cannot be used either.
        self.receive("5000", matter=self.other)
        with self.assertRaises(ValidationError):
            trust.pay(self.matter, Decimal("200"), self.user, date=TODAY, party="X", description="Y")
        self.assertEqual(self.matter.trust_balance, Decimal("100"))

    def test_overdraft_rejected_through_view(self):
        resp = self.client.post(reverse("trust_payment"), {
            "matter": self.matter.pk, "date": TODAY.isoformat(), "amount": "50", "party": "X", "description": "Y",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Insufficient trust funds")
        self.assertFalse(TrustTransaction.objects.exists())

    def test_fee_transfer_pays_invoice(self):
        inv = self.issued_invoice()  # 200 + 15% VAT = 230
        self.receive("1000")
        trust.transfer_fees(inv, Decimal("230"), self.user, date=TODAY)
        inv.refresh_from_db()
        self.assertEqual(inv.status, "paid")
        self.assertEqual(self.matter.trust_balance, Decimal("770"))
        payment = inv.payments.get()
        self.assertEqual(payment.method, "trust")

    def test_fee_transfer_limited_to_invoice_balance_and_trust_funds(self):
        inv = self.issued_invoice()
        self.receive("100")
        with self.assertRaises(ValidationError):
            trust.transfer_fees(inv, Decimal("150"), self.user, date=TODAY)  # more than trust
        self.receive("1000")
        with self.assertRaises(ValidationError):
            trust.transfer_fees(inv, Decimal("231"), self.user, date=TODAY)  # more than invoice

    def test_reversing_fee_transfer_restores_trust_and_reopens_invoice(self):
        inv = self.issued_invoice()
        self.receive("500")
        tx = trust.transfer_fees(inv, Decimal("230"), self.user, date=TODAY)
        trust.reverse(tx, self.user, date=TODAY, reason="Wrong matter")
        inv.refresh_from_db()
        self.assertEqual(inv.status, "issued")
        self.assertFalse(inv.payments.exists())
        self.assertEqual(self.matter.trust_balance, Decimal("500"))

    def test_matter_transfer_and_paired_reversal(self):
        self.receive("1000")
        out, inn = trust.transfer_between(self.matter, self.other, Decimal("400"), self.user, date=TODAY,
                                          description="Move")
        self.assertEqual(self.matter.trust_balance, Decimal("600"))
        self.assertEqual(self.other.trust_balance, Decimal("400"))
        trust.reverse(inn, self.user, date=TODAY, reason="Error")
        self.assertEqual(self.matter.trust_balance, Decimal("1000"))
        self.assertEqual(self.other.trust_balance, Decimal("0"))
        with self.assertRaises(ValidationError):
            trust.reverse(out, self.user, date=TODAY, reason="Again")

    def test_cannot_reverse_receipt_already_spent(self):
        rec = self.receive("100")
        trust.pay(self.matter, Decimal("80"), self.user, date=TODAY, party="X", description="Y")
        with self.assertRaises(ValidationError):
            trust.reverse(rec, self.user, date=TODAY, reason="Bounced")

    def test_cannot_close_matter_holding_trust_money(self):
        self.receive("10")
        data = {f: getattr(self.matter, f) for f in ["description", "matter_type", "billing_type"]}
        data.update(client=self.client_obj.pk, responsible=self.user.pk, status="closed",
                    date_opened=TODAY.isoformat())
        resp = self.client.post(reverse("matter_edit", args=[self.matter.pk]), data)
        self.assertContains(resp, "still holds money in trust")
        self.matter.refresh_from_db()
        self.assertEqual(self.matter.status, "open")

    def test_reconciliation(self):
        r1 = self.receive("1000")
        self.receive("200")  # not yet on the bank statement
        trust.pay(self.matter, Decimal("300"), self.user, date=TODAY, party="X", description="Y")  # not on statement
        trust.transfer_between(self.matter, self.other, Decimal("50"), self.user, date=TODAY, description="Move")
        url = reverse("trust_reconciliation_new")
        self.client.post(url, {"date": TODAY.isoformat(), "cleared": [r1.pk], "bank_statement_balance": "1000",
                               "save": "1"})
        rec = TrustReconciliation.objects.get()
        self.assertEqual(rec.cashbook_balance, Decimal("900"))
        self.assertEqual(rec.outstanding_deposits, Decimal("200"))
        self.assertEqual(rec.outstanding_payments, Decimal("300"))
        self.assertTrue(rec.is_balanced)


TEST_MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEST_MEDIA)
class DocumentAndAccessTests(Base):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEST_MEDIA, ignore_errors=True)
        super().tearDownClass()

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse("matter_list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])

    def test_generate_document_merges_fields(self):
        tpl = DocumentTemplate.objects.create(name="Demand", body="Re {{ matter.file_number }} for {{ client.name }}")
        resp = self.client.post(reverse("document_generate", args=[self.matter.pk]),
                                {"template": tpl.pk, "save_to_matter": "on"})
        self.assertEqual(resp["Content-Type"], "application/msword")
        self.assertIn("Re MAT00001 for Acme Ltd", resp.content.decode())
        self.assertEqual(self.matter.documents.count(), 1)

    def test_firm_settings_singleton(self):
        FirmSettings(name="A").save()
        FirmSettings(name="B").save()
        self.assertEqual(FirmSettings.objects.count(), 1)
        self.assertEqual(FirmSettings.load().name, "B")
