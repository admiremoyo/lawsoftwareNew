from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from clients.models import Client
from matters.models import Matter, WorkflowTemplate


def partner(username="pat"):
    user = get_user_model().objects.create_user(username, f"{username}@firm.test", "pw-long-enough-123")
    user.profile.role = "partner"
    user.profile.save()
    return user


class WorkflowTests(TestCase):
    def setUp(self):
        self.user = partner()
        self.client.force_login(self.user)
        self.client_obj = Client.objects.create(name="Jane")

    def test_default_workflows_exist(self):
        self.assertTrue(WorkflowTemplate.objects.filter(matter_type="conveyancing").exists())

    def test_checklist_added_when_matter_opened(self):
        self.client.post(reverse("matter_create"), {
            "client": self.client_obj.pk, "description": "Transfer", "matter_type": "conveyancing",
            "status": "open", "responsible": self.user.pk, "date_opened": "2026-10-01", "billing_type": "fixed",
        })
        matter = Matter.objects.get()
        self.assertEqual(matter.tasks.count(), 10)
        first = matter.tasks.first()
        self.assertEqual(first.due_date, date(2026, 10, 1))
        self.client.post(reverse("task_toggle", args=[first.pk]))
        first.refresh_from_db()
        self.assertTrue(first.done)
        self.assertEqual(matter.checklist_percent, 10)

    def test_edit_workflow_steps(self):
        resp = self.client.post(reverse("workflow_create"), {
            "name": "Labour dispute", "matter_type": "labour", "auto_apply": "on",
            "steps-TOTAL_FORMS": "2", "steps-INITIAL_FORMS": "0", "steps-MIN_NUM_FORMS": "0",
            "steps-MAX_NUM_FORMS": "1000",
            "steps-0-order": "1", "steps-0-title": "Refer to conciliation", "steps-0-due_after_days": "30",
            "steps-1-order": "2", "steps-1-title": "Arbitration", "steps-1-due_after_days": "",
        })
        self.assertRedirects(resp, reverse("workflow_list"))
        self.assertEqual(WorkflowTemplate.objects.get(name="Labour dispute").steps.count(), 2)


class ImportTests(TestCase):
    def setUp(self):
        self.user = partner()
        self.client.force_login(self.user)

    def upload(self, kind, content):
        return self.client.post(reverse("data_import"), {
            "kind": kind, "file": SimpleUploadedFile(f"{kind}.csv", content.encode("utf-8"), "text/csv"),
        })

    def test_client_import_preview_then_confirm(self):
        csv = "Name,Client Type,ID Number,Email\nJane Doe,individual,ID1,jane@x.com\nAcme Ltd,company,REG2,\n"
        resp = self.upload("clients", csv)
        self.assertTrue(resp.context["result"].ok)
        self.assertEqual(Client.objects.count(), 0)  # preview only
        resp = self.client.post(reverse("data_import"), {"confirm": "1"})
        self.assertRedirects(resp, reverse("client_list"))
        self.assertEqual(Client.objects.count(), 2)
        self.assertEqual(Client.objects.get(name="Acme Ltd").client_type, "company")

    def test_any_error_blocks_whole_import(self):
        resp = self.upload("clients", "name,client_type\nGood,individual\n,individual\nBad,alien\n")
        result = resp.context["result"]
        self.assertFalse(result.ok)
        self.assertEqual(len(result.errors), 2)
        self.client.post(reverse("data_import"), {"confirm": "1"})
        self.assertEqual(Client.objects.count(), 0)

    def test_matter_import_with_trust_opening_balance(self):
        client = Client.objects.create(name="Jane Doe", id_number="ID1")
        csv = ("client;description;matter_type;date_opened;old_file_number;trust_opening_balance\n"
               "ID1;Transfer of Stand 5;conveyancing;15/01/2026;OLD/1;1,500.00\n"
               f"{client.code};Estate;estates;2026-02-01;;\n")
        resp = self.upload("matters", csv)
        self.assertTrue(resp.context["result"].ok, resp.context["result"].errors)
        self.client.post(reverse("data_import"), {"confirm": "1"})
        matter = Matter.objects.get(description="Transfer of Stand 5")
        self.assertEqual(matter.date_opened, date(2026, 1, 15))
        self.assertEqual(matter.trust_balance, Decimal("1500.00"))
        self.assertIn("OLD/1", matter.notes)
        self.assertEqual(Matter.objects.count(), 2)

    def test_matter_import_unknown_client(self):
        resp = self.upload("matters", "client,description\nNobody,Something\n")
        self.assertFalse(resp.context["result"].ok)


class InterestTests(TestCase):
    def setUp(self):
        self.client.force_login(partner())

    def test_simple_interest(self):
        resp = self.client.get(reverse("interest_calculator"), {
            "principal": "10000", "rate": "10", "start": "2025-01-01", "end": "2026-01-01"})
        self.assertEqual(resp.context["result"]["interest"], Decimal("1000.00"))

    def test_in_duplum_cap(self):
        resp = self.client.get(reverse("interest_calculator"), {
            "principal": "1000", "rate": "50", "start": "2020-01-01", "end": "2026-01-01", "in_duplum": "1"})
        result = resp.context["result"]
        self.assertTrue(result["capped"])
        self.assertEqual(result["total"], Decimal("2000"))
