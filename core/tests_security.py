from datetime import date

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from billing.models import Invoice, TimeEntry
from clients.models import Client
from diary.models import DiaryEntry
from matters.models import DocumentTemplate, Matter


class SecurityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("pat", "pat@firm.test", "pw-long-enough-123",
                                                         first_name="Pat", last_name="P")
        self.user.profile.role = "partner"
        self.user.profile.save()
        self.client.force_login(self.user)
        self.client_obj = Client.objects.create(name="=HYPERLINK(\"http://evil\")")
        self.matter = Matter.objects.create(client=self.client_obj, description="M", responsible=self.user,
                                            date_opened=date(2026, 10, 1))

    def generate(self, body):
        tpl = DocumentTemplate.objects.create(name="T", body=body)
        return self.client.post(reverse("document_generate", args=[self.matter.pk]), {"template": tpl.pk})

    def test_precedent_cannot_call_model_methods(self):
        TimeEntry.objects.create(matter=self.matter, user=self.user, description="x", minutes=60)
        invoice = Invoice.objects.create(matter=self.matter, created_by=self.user, status="issued")
        self.generate("{{ matter.invoices.first.void }}{{ matter.delete }}{{ client.delete }}")
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "issued")
        self.assertTrue(Matter.objects.filter(pk=self.matter.pk).exists())

    def test_precedent_merge_fields_still_work(self):
        resp = self.generate("{{ matter.file_number }} / {{ matter.responsible }} / {{ firm.name }}")
        self.assertIn(f"{self.matter.file_number} / Pat P", resp.content.decode())

    def test_precedent_blocked_tags(self):
        resp = self.client.post(reverse("template_create"), {"name": "Bad", "body": "{% debug %}"})
        self.assertContains(resp, "can&#x27;t use include")
        resp = self.generate("{% include 'base.html' %}")
        self.assertEqual(resp.status_code, 302)  # refused with a message, nothing rendered

    def test_open_redirect_blocked(self):
        entry = DiaryEntry.objects.create(title="x", assigned_to=self.user, start="2026-10-01T09:00Z")
        for evil in ["https://evil.example", "//evil.example", "/\\evil.example"]:
            resp = self.client.post(reverse("diary_toggle", args=[entry.pk]), {"next": evil})
            self.assertFalse("evil" in resp["Location"], evil)

    def test_csv_export_neutralises_formulas(self):
        resp = self.client.get(reverse("report_matters"), {"status": "", "format": "csv"})
        self.assertIn("'=HYPERLINK", resp.content.decode())

    def test_password_reset_rate_limited(self):
        cache.clear()
        self.client.logout()
        for _ in range(8):
            self.client.post("/password-reset/", {"email": "pat@firm.test"})
        self.assertEqual(len(mail.outbox), 5)

    def test_financial_records_read_only_in_admin(self):
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        invoice = Invoice.objects.create(matter=self.matter, created_by=self.user)
        resp = self.client.post(f"/admin/billing/invoice/{invoice.pk}/delete/", {"post": "yes"})
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Invoice.objects.filter(pk=invoice.pk).exists())
