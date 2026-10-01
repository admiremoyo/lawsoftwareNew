"""Load a small demo firm so you can click around: `python manage.py seed_demo`."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from billing.models import Disbursement, Invoice, TimeEntry
from clients.models import Client
from core.models import FirmSettings
from diary.models import DiaryEntry
from matters.models import DocumentTemplate, FileNote, Matter
from trust import services as trust


class Command(BaseCommand):
    help = "Create demo users, clients, matters, time, fee notes and trust entries."

    @staticmethod
    def _profile(user, role, initials, rate):
        profile = user.profile  # created by the post_save signal
        profile.role, profile.initials, profile.hourly_rate = role, initials, Decimal(rate)
        profile.save()

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Allow seeding when DEBUG is off.")

    def handle(self, *args, **options):
        from django.conf import settings

        if not settings.DEBUG and not options["force"]:
            self.stderr.write("Refusing to load demo data (with weak demo passwords) on a production server. "
                              "Use --force on a demo/sales instance only.")
            return
        if Client.objects.exists():
            self.stdout.write(self.style.WARNING("Data already exists – skipping demo seed."))
            return
        User = get_user_model()
        today = timezone.localdate()

        firm = FirmSettings.load()
        firm.name = "Demo & Partners Legal Practitioners"
        firm.address = "1st Floor, Legal House\n12 Main Street"
        firm.phone = "+000 000 0000"
        firm.email = "info@demo-law.example"
        firm.business_bank_details = "Demo Bank – Business account 1234567890"
        firm.trust_bank_name = "Demo Bank"
        firm.trust_account_number = "TRUST-9876543210"
        firm.save()

        admin = User.objects.create_superuser("admin", "admin@demo-law.example", "demo-admin-2026",
                                              first_name="Alex", last_name="Partner")
        self._profile(admin, "partner", "AP", "250")
        assoc = User.objects.create_user("associate", "assoc@demo-law.example", "demo-associate-2026",
                                         first_name="Sam", last_name="Associate")
        self._profile(assoc, "associate", "SA", "150")

        acme = Client.objects.create(client_type="company", name="Acme Trading (Pvt) Ltd", contact_person="J. Banda",
                                     email="legal@acme.example", phone="+000 111 2222",
                                     physical_address="45 Industrial Road", id_number="REG 2019/0042")
        jane = Client.objects.create(name="Jane Mutasa", email="jane@example.com", phone="+000 333 4444",
                                     physical_address="7 Jacaranda Avenue", id_number="63-123456-A-42")
        estate = Client.objects.create(name="Estate Late Peter Ndlovu", contact_person="Mary Ndlovu (executrix)")

        m1 = Matter.objects.create(client=acme, description="Acme v Beta Logistics – breach of contract",
                                   matter_type="litigation", responsible=admin, date_opened=today - timedelta(days=75),
                                   opposing_party="Beta Logistics", opposing_attorney="Smith & Co",
                                   court="High Court", case_number="HC 1234/26",
                                   prescription_date=today + timedelta(days=45))
        m2 = Matter.objects.create(client=jane, description="Transfer of Stand 1182, Greendale",
                                   matter_type="conveyancing", responsible=assoc, date_opened=today - timedelta(days=30),
                                   billing_type="fixed", fixed_fee=Decimal("1200"))
        m3 = Matter.objects.create(client=estate, description="Administration of estate", matter_type="estates",
                                   responsible=admin, date_opened=today - timedelta(days=120))
        m4 = Matter.objects.create(client=acme, description="Debt collection – Gamma Stores", matter_type="collections",
                                   responsible=assoc, date_opened=today - timedelta(days=10))

        from matters.models import WorkflowTemplate

        for matter, done in [(m1, 4), (m2, 3), (m3, 5), (m4, 1)]:
            for workflow in WorkflowTemplate.objects.filter(matter_type=matter.matter_type):
                workflow.apply_to(matter)
            for task in matter.tasks.all()[:done]:
                task.done, task.done_by, task.done_at = True, matter.responsible, timezone.now()
                task.save()

        FileNote.objects.create(matter=m1, author=admin, date=today - timedelta(days=70),
                                note="Consultation with client. Received contract and correspondence bundle.")
        FileNote.objects.create(matter=m1, author=admin, date=today - timedelta(days=40),
                                note="Summons issued and served on defendant.")

        for days, user, desc, minutes in [
            (70, admin, "Consultation with client; perusal of contract", 90),
            (60, assoc, "Drafting summons and declaration", 180),
            (40, admin, "Settling pleadings", 60),
            (5, assoc, "Preparing discovery affidavit", 120),
        ]:
            TimeEntry.objects.create(matter=m1, user=user, date=today - timedelta(days=days), description=desc,
                                     minutes=minutes)
        TimeEntry.objects.create(matter=m3, user=admin, date=today - timedelta(days=100),
                                 description="Reporting estate to Master; preparing inventory", minutes=150)
        TimeEntry.objects.create(matter=m4, user=assoc, date=today - timedelta(days=3),
                                 description="Letter of demand", minutes=30)
        Disbursement.objects.create(matter=m1, date=today - timedelta(days=40), description="Sheriff's fees – service",
                                    amount=Decimal("45.00"), created_by=admin)
        Disbursement.objects.create(matter=m1, date=today - timedelta(days=40), description="Court filing fee",
                                    amount=Decimal("30.00"), created_by=admin)

        # Bill the early litigation work and settle part of it from trust.
        inv = Invoice.objects.create(matter=m1, date=today - timedelta(days=35), created_by=admin)
        m1.time_entries.filter(date__lte=today - timedelta(days=40)).update(invoice=inv)
        m1.disbursements.update(invoice=inv)
        inv.status = "issued"
        inv.save()

        trust.receive(m1, Decimal("2000.00"), admin, date=today - timedelta(days=72), party="Acme Trading (Pvt) Ltd",
                      description="Deposit on fees and costs", reference="EFT 55120")
        trust.transfer_fees(inv, Decimal("1000.00"), admin, date=today - timedelta(days=30))
        trust.receive(m2, Decimal("85000.00"), assoc, date=today - timedelta(days=20), party="Purchaser – T. Moyo",
                      description="Purchase price held in trust pending registration", reference="EFT 99812")
        trust.receive(m3, Decimal("5400.00"), admin, date=today - timedelta(days=90), party="Demo Bank",
                      description="Proceeds of deceased's savings account")
        trust.pay(m3, Decimal("400.00"), admin, date=today - timedelta(days=60), party="Master of the High Court",
                  description="Estate duty and Master's fees", reference="CHQ 001")

        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        DiaryEntry.objects.create(title="Pre-trial conference – Acme v Beta", entry_type="court", matter=m1,
                                  assigned_to=admin, start=now + timedelta(days=6, hours=1), location="High Court, Court 4")
        DiaryEntry.objects.create(title="Consultation – Jane Mutasa (sign transfer docs)", entry_type="appointment",
                                  matter=m2, assigned_to=assoc, start=now + timedelta(hours=3))
        DiaryEntry.objects.create(title="Plea due from defendant", entry_type="deadline", matter=m1, assigned_to=admin,
                                  start=now + timedelta(days=10))
        DiaryEntry.objects.create(title="Follow up on letter of demand", entry_type="task", matter=m4, assigned_to=assoc,
                                  start=now - timedelta(days=1))

        DocumentTemplate.objects.create(name="Letter of demand", matter_type="collections", body=(
            "{{ firm.name }}\n{{ firm.address }}\n\n{{ today }}\n\nOur ref: {{ matter.file_number }}\n\n"
            "Dear Sir/Madam\n\nRE: {{ matter.description|upper }}\n\n"
            "We act on behalf of {{ client.name }}. Our client instructs us that you are indebted to it in the "
            "amount of $______ which remains unpaid despite demand.\n\n"
            "We hereby demand payment within 10 (ten) days of the date of this letter, failing which we hold "
            "instructions to institute legal proceedings against you without further notice.\n\n"
            "Yours faithfully\n\n{{ author }}\n{{ firm.name }}"
        ))
        DocumentTemplate.objects.create(name="Letter of engagement", body=(
            "{{ today }}\n\n{{ client.name }}\n{{ client.physical_address }}\n\n"
            "Dear {{ client.name }}\n\nRE: {{ matter.description }} (our ref {{ matter.file_number }})\n\n"
            "Thank you for instructing {{ firm.name }}. This letter sets out the scope of our mandate and the "
            "basis on which our fees will be charged.\n\n...\n\nYours faithfully\n{{ author }}"
        ))

        from accounting.models import BusinessTransaction, Category, vat_from_gross

        for days, cat, party, desc, amount, vat in [
            (60, "Rent", "City Properties", "Office rent", "1150.00", True),
            (30, "Rent", "City Properties", "Office rent", "1150.00", True),
            (25, "Salaries and wages", "Staff", "Salaries", "3200.00", False),
            (12, "Telephone and internet", "Telco", "Internet and phones", "230.00", True),
            (5, "Stationery and printing", "Office Mart", "Paper and toner", "115.00", True),
        ]:
            BusinessTransaction.objects.create(
                date=today - timedelta(days=days), type="payment", category=Category.objects.get(name=cat),
                party=party, description=desc, amount=Decimal(amount),
                vat_amount=vat_from_gross(Decimal(amount), firm.vat_rate) if vat else Decimal("0"), created_by=admin,
            )
        BusinessTransaction.objects.create(
            date=today - timedelta(days=74), type="receipt", category=Category.objects.get(name="Capital introduced"),
            party="Partners", description="Opening capital", amount=Decimal("10000"), created_by=admin,
        )

        self.stdout.write(self.style.SUCCESS(
            "Demo data created. Log in as admin / demo-admin-2026 (partner) or associate / demo-associate-2026."
        ))
