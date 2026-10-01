from django.db import migrations

WORKFLOWS = {
    ("Property transfer (conveyancing)", "conveyancing"): [
        ("Receive instruction and signed agreement of sale", 0),
        ("Identity / FICA (KYC) documents from seller and purchaser", 3),
        ("Request title deed and bond cancellation figures", 5),
        ("Apply for rates / municipal clearance certificate", 7),
        ("Obtain tax clearance (transfer duty / capital gains)", 21),
        ("Draft transfer documents and power of attorney; parties sign", 14),
        ("Receive purchase price or guarantees into trust", 30),
        ("Lodge documents at the Deeds Registry", 45),
        ("Registration – report to all parties", 60),
        ("Final statement of account; pay out proceeds from trust", 65),
    ],
    ("Deceased estate administration", "estates"): [
        ("Obtain death certificate, will and family details", 0),
        ("Report the estate to the Master of the High Court", 14),
        ("Letters of administration / executorship issued", 45),
        ("Advertise for creditors", 60),
        ("Open estate bank account and collect assets", 60),
        ("Inventory and valuation of assets", 90),
        ("Lodge liquidation and distribution account", 150),
        ("Advertise the account for inspection", 165),
        ("Pay creditors and distribute to heirs", 200),
        ("Close the estate and obtain discharge", 240),
    ],
    ("Civil action (litigation)", "litigation"): [
        ("Consultation; obtain documents and client statement", 0),
        ("Letter of demand", 7),
        ("Issue summons", 30),
        ("Serve summons; diarise appearance and plea dates", 35),
        ("Close of pleadings", 90),
        ("Discovery", 120),
        ("Pre-trial conference", 150),
        ("Set down for trial", 180),
        ("Trial or settlement", 240),
        ("Tax and recover costs", 270),
    ],
    ("Debt collection", "collections"): [
        ("Letter of demand", 0),
        ("Follow up on letter of demand", 10),
        ("Issue summons", 21),
        ("Apply for default judgment", 45),
        ("Writ of execution / garnishee order", 60),
        ("Recover and pay over to client", 90),
    ],
    ("Divorce", "family"): [
        ("Consultation; marriage certificate and financial details", 0),
        ("Issue summons / application", 21),
        ("Serve on spouse", 28),
        ("Negotiate deed of settlement", 60),
        ("Set down and obtain decree", 120),
        ("Implement the settlement (transfers, pension orders)", 150),
    ],
}


def seed(apps, schema_editor):
    WorkflowTemplate = apps.get_model("matters", "WorkflowTemplate")
    WorkflowStep = apps.get_model("matters", "WorkflowStep")
    for (name, matter_type), steps in WORKFLOWS.items():
        template, created = WorkflowTemplate.objects.get_or_create(name=name, defaults={"matter_type": matter_type})
        if created:
            for order, (title, days) in enumerate(steps, start=1):
                WorkflowStep.objects.create(template=template, order=order, title=title, due_after_days=days)


class Migration(migrations.Migration):
    dependencies = [("matters", "0002_workflows")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
