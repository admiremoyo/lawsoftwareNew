"""CSV import of clients and matters, for firms moving from another system.

Each import is validated in full first; nothing is saved unless every row is valid.
"""
import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from clients.models import Client
from matters.models import Matter

CLIENT_COLUMNS = ["name", "client_type", "id_number", "vat_number", "contact_person", "email", "phone",
                  "physical_address", "postal_address", "notes"]
MATTER_COLUMNS = ["client", "description", "matter_type", "responsible", "date_opened", "status", "case_number",
                  "court", "opposing_party", "opposing_attorney", "prescription_date", "old_file_number",
                  "trust_opening_balance"]

CLIENT_TYPES = {"individual": "individual", "person": "individual", "company": "company",
                "organisation": "company", "organization": "company", "trust": "company", "": "individual"}
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d")


class ImportResult:
    def __init__(self):
        self.rows = []
        self.errors = []
        self.created = 0

    @property
    def ok(self):
        return not self.errors


def decode_upload(upload):
    raw = upload.read()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def read_csv(text):
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    reader.fieldnames = [(f or "").strip().lower().replace(" ", "_") for f in reader.fieldnames or []]
    return [{k: (v or "").strip() for k, v in row.items() if k} for row in reader]


def parse_date(value):
    if not value:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"'{value}' is not a date (use YYYY-MM-DD or DD/MM/YYYY)")


def import_clients(text, dry_run=True):
    result = ImportResult()
    rows = read_csv(text)
    if not rows or "name" not in rows[0]:
        result.errors.append("The file needs a header row with at least a 'name' column.")
        return result
    seen = set()
    for n, row in enumerate(rows, start=2):
        errors = []
        if not row.get("name"):
            errors.append("name is required")
        ctype = CLIENT_TYPES.get(row.get("client_type", "").lower())
        if ctype is None:
            errors.append(f"client_type '{row['client_type']}' must be individual or company")
        key = (row.get("name", "").lower(), row.get("id_number", "").lower())
        if key in seen:
            errors.append("duplicate of an earlier row")
        seen.add(key)
        if row.get("id_number") and Client.objects.filter(id_number__iexact=row["id_number"]).exists():
            errors.append(f"a client with ID/registration {row['id_number']} already exists")
        result.rows.append({"line": n, "data": row, "errors": errors})
        result.errors += [f"Line {n}: {e}" for e in errors]
    if result.ok and not dry_run:
        with transaction.atomic():
            for item in result.rows:
                row = item["data"]
                Client.objects.create(client_type=CLIENT_TYPES[row.get("client_type", "").lower()],
                                      **{c: row.get(c, "") for c in CLIENT_COLUMNS if c != "client_type"})
                result.created += 1
    return result


def _find_client(value):
    return (Client.objects.filter(code__iexact=value).first()
            or Client.objects.filter(id_number__iexact=value).first()
            or Client.objects.filter(name__iexact=value).first())


def import_matters(text, user, dry_run=True, allow_trust=False):
    from trust import services as trust

    User = get_user_model()
    result = ImportResult()
    rows = read_csv(text)
    if not rows or not {"client", "description"} <= set(rows[0]):
        result.errors.append("The file needs a header row with at least 'client' and 'description' columns.")
        return result
    types = {k for k, _ in Matter.TYPE_CHOICES}
    statuses = {k for k, _ in Matter.STATUS_CHOICES}
    parsed = []
    for n, row in enumerate(rows, start=2):
        errors, values = [], {}
        client = _find_client(row.get("client", "")) if row.get("client") else None
        if not client:
            errors.append(f"client '{row.get('client', '')}' not found (use the client code, ID number or exact name)")
        if not row.get("description"):
            errors.append("description is required")
        mtype = (row.get("matter_type") or "other").lower()
        if mtype not in types:
            errors.append(f"matter_type '{mtype}' must be one of {', '.join(sorted(types))}")
        status = (row.get("status") or "open").lower().replace(" ", "_")
        if status not in statuses:
            errors.append(f"status '{status}' must be open, on_hold or closed")
        responsible = user
        if row.get("responsible"):
            responsible = User.objects.filter(username__iexact=row["responsible"]).first()
            if not responsible:
                errors.append(f"user '{row['responsible']}' not found")
        try:
            opened = parse_date(row.get("date_opened")) or timezone.localdate()
            prescription = parse_date(row.get("prescription_date"))
        except ValueError as exc:
            errors.append(str(exc))
            opened = prescription = None
        balance = Decimal("0")
        if row.get("trust_opening_balance"):
            try:
                balance = Decimal(row["trust_opening_balance"].replace(",", ""))
            except InvalidOperation:
                errors.append(f"trust_opening_balance '{row['trust_opening_balance']}' is not a number")
            if balance < 0:
                errors.append("trust_opening_balance can't be negative")
            if balance and not allow_trust:
                errors.append("you don't have permission to post trust balances")
            if balance and status == "closed":
                errors.append("a closed matter can't hold a trust balance")
        values = dict(client=client, description=row.get("description", ""), matter_type=mtype, status=status,
                      responsible=responsible, date_opened=opened, prescription_date=prescription,
                      case_number=row.get("case_number", ""), court=row.get("court", ""),
                      opposing_party=row.get("opposing_party", ""),
                      opposing_attorney=row.get("opposing_attorney", ""),
                      notes=f"Previous file number: {row['old_file_number']}" if row.get("old_file_number") else "")
        parsed.append((values, balance))
        result.rows.append({"line": n, "data": row, "errors": errors})
        result.errors += [f"Line {n}: {e}" for e in errors]
    if result.ok and not dry_run:
        with transaction.atomic():
            for values, balance in parsed:
                matter = Matter.objects.create(**values)
                if balance:
                    trust.receive(matter, balance, user, date=matter.date_opened, party="Opening balance",
                                  description="Trust balance brought forward from previous system")
                result.created += 1
    return result


def template_csv(columns, example):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(columns)
    writer.writerow(example)
    return out.getvalue()


CLIENT_EXAMPLE = ["Jane Doe", "individual", "63-123456-A-42", "", "", "jane@example.com", "+000 111 222",
                  "7 Jacaranda Ave", "", "Referred by Mr X"]
MATTER_EXAMPLE = ["Jane Doe", "Transfer of Stand 1182", "conveyancing", "", "2026-01-15", "open", "", "", "",
                  "", "", "OLD/123", "1500.00"]
