import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models

DEFAULT_CATEGORIES = [
    ("Fee income", "income", True),
    ("Interest received", "income", False),
    ("Other income", "income", False),
    ("Capital introduced", "income", False),
    ("Rent", "expense", False),
    ("Salaries and wages", "expense", False),
    ("Bank charges", "expense", False),
    ("Stationery and printing", "expense", False),
    ("Telephone and internet", "expense", False),
    ("Electricity and water", "expense", False),
    ("Law Society fees and insurance", "expense", False),
    ("Professional indemnity insurance", "expense", False),
    ("Computer and software", "expense", False),
    ("Motor vehicle and travel", "expense", False),
    ("Repairs and maintenance", "expense", False),
    ("Legal research and subscriptions", "expense", False),
    ("Disbursements paid for clients", "expense", False),
    ("Drawings", "expense", False),
    ("Other expenses", "expense", False),
]


def seed(apps, schema_editor):
    Category = apps.get_model("accounting", "Category")
    for name, kind, system in DEFAULT_CATEGORIES:
        Category.objects.get_or_create(name=name, defaults={"kind": kind, "system": system})
    # Fee payments recorded before the business cash book existed.
    Payment = apps.get_model("billing", "Payment")
    BusinessTransaction = apps.get_model("accounting", "BusinessTransaction")
    fee_income = Category.objects.get(name="Fee income")
    for p in Payment.objects.select_related("invoice__matter__client"):
        BusinessTransaction.objects.create(
            date=p.date, type="receipt", category=fee_income, party=p.invoice.matter.client.name,
            description=f"Payment of {p.invoice.number}", reference=p.reference, amount=p.amount,
            signed_amount=p.amount, payment=p, created_by_id=p.created_by_id,
        )


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("billing", "0002_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("kind", models.CharField(choices=[("income", "Income"), ("expense", "Expense")], max_length=10)),
                ("system", models.BooleanField(default=False, help_text="Used automatically by the system; can't be removed.")),
            ],
            options={"ordering": ["kind", "name"], "verbose_name_plural": "categories"},
        ),
        migrations.CreateModel(
            name="BusinessTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(default=django.utils.timezone.localdate)),
                ("type", models.CharField(choices=[("receipt", "Money in"), ("payment", "Money out")], max_length=10)),
                ("party", models.CharField(blank=True, max_length=200, verbose_name="received from / paid to")),
                ("description", models.CharField(max_length=300)),
                ("reference", models.CharField(blank=True, max_length=100)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14, verbose_name="amount (incl. VAT)")),
                ("vat_amount", models.DecimalField(decimal_places=2, default=Decimal("0"), help_text="Input VAT you can claim back on this expense.", max_digits=14, verbose_name="VAT included")),
                ("signed_amount", models.DecimalField(decimal_places=2, editable=False, max_digits=14)),
                ("reconciled", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="accounting.category")),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("payment", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="business_transaction", to="billing.payment")),
            ],
            options={"ordering": ["date", "id"]},
        ),
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
