import csv
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import Q, Sum
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.permissions import has_perm, require_perm
from billing.models import Disbursement, Invoice, TimeEntry
from clients.models import Client
from diary.models import DiaryEntry
from matters.models import Matter, MatterTask
from trust.models import TrustTransaction

from .forms import FirmSettingsForm
from .models import AuditLog, FirmSettings


def firm_logo(request):
    """The firm logo (uploads are never served publicly)."""
    firm = FirmSettings.load()
    if not firm.logo:
        raise Http404
    return FileResponse(firm.logo.open("rb"))


def health(request):
    """Used by Docker / uptime monitors. Public, reveals nothing."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:  # noqa: BLE001
        return JsonResponse({"status": "error"}, status=503)
    return JsonResponse({"status": "ok"})


def permission_denied(request, exception=None):
    return render(request, "error.html", {
        "code": 403, "title": "Not allowed",
        "message": f"Your role doesn't allow this: {exception}." if exception and str(exception) else
        "Your role doesn't allow this action. Ask a partner if you need access.",
    }, status=403)


def not_found(request, exception=None):
    return render(request, "error.html", {"code": 404, "title": "Page not found",
                                          "message": "That page or record doesn't exist."}, status=404)


def server_error(request):
    return render(request, "error.html", {"code": 500, "title": "Something went wrong",
                                          "message": "The error has been logged. Please try again."}, status=500)


def dashboard(request):
    today = timezone.localdate()
    now = timezone.now()
    my_unbilled = TimeEntry.objects.filter(user=request.user, invoice__isnull=True, billable=True)
    month_start = today.replace(day=1)
    outstanding = [inv for inv in Invoice.objects.filter(status="issued")]
    context = {
        "today": today,
        "open_matters": Matter.objects.filter(status="open").count(),
        "active_clients": Client.objects.filter(is_active=True).count(),
        "trust_total": TrustTransaction.total_balance(),
        "debtors_total": sum((i.balance for i in outstanding), Decimal("0")),
        "my_unbilled_amount": my_unbilled.aggregate(t=Sum("amount"))["t"] or 0,
        "my_month_minutes": TimeEntry.objects.filter(user=request.user, date__gte=month_start).aggregate(
            t=Sum("minutes")
        )["t"] or 0,
        "today_entries": DiaryEntry.objects.filter(start__date=today, completed=False).select_related("matter"),
        "upcoming": DiaryEntry.objects.filter(
            start__gt=now, start__date__lte=today + timedelta(days=14), completed=False,
            entry_type__in=["court", "deadline"],
        ).select_related("matter")[:10],
        "overdue_tasks": DiaryEntry.objects.filter(start__lt=now, completed=False, assigned_to=request.user)
        .exclude(start__date=today)[:10],
        "prescribing": Matter.objects.filter(
            status="open", prescription_date__isnull=False, prescription_date__lte=today + timedelta(days=90)
        ).order_by("prescription_date")[:10],
        "recent_matters": Matter.objects.select_related("client")[:8],
        "steps_due": MatterTask.objects.filter(
            done=False, due_date__lte=today + timedelta(days=7), matter__status="open",
            matter__responsible=request.user,
        ).select_related("matter").order_by("due_date")[:10],
    }
    return render(request, "core/dashboard.html", context)


def search(request):
    q = request.GET.get("q", "").strip()
    context = {"q": q}
    if q:
        context["clients"] = Client.objects.filter(
            Q(name__icontains=q) | Q(code__icontains=q) | Q(id_number__icontains=q)
        )[:20]
        context["matters"] = Matter.objects.filter(
            Q(file_number__icontains=q) | Q(description__icontains=q) | Q(case_number__icontains=q)
            | Q(opposing_party__icontains=q) | Q(client__name__icontains=q)
        ).select_related("client")[:20]
        context["invoices"] = Invoice.objects.filter(number__icontains=q).select_related("matter")[:20]
    return render(request, "core/search.html", context)


@require_perm("firm_settings")
def firm_settings(request):
    obj = FirmSettings.load()
    form = FirmSettingsForm(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        AuditLog.record(request.user, "update", obj, "Firm settings updated")
        messages.success(request, "Settings saved.")
        return redirect("firm_settings")
    return render(request, "form.html", {"form": form, "title": "Firm settings"})


@require_perm("audit_log")
def audit_log(request):
    return render(request, "core/audit_log.html", {"entries": AuditLog.objects.select_related("user")[:500]})


# ---------------------------------------------------------------- reports

def _parse_date(value, default):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return default


def _csv(filename, header, rows):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(header)
    writer.writerows([[_csv_safe(v) for v in row] for row in rows])
    return response


def _csv_safe(value):
    """Stop spreadsheet formula injection from text fields such as client names."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def reports(request):
    return render(request, "core/reports.html")


@require_perm("financial_reports")
def report_wip(request):
    """Work in progress: unbilled time and disbursements per matter."""
    rows = []
    for matter in Matter.objects.exclude(status="closed").select_related("client", "responsible"):
        fees, disb = matter.unbilled_fees, matter.unbilled_disbursements
        if fees or disb:
            rows.append({"matter": matter, "fees": fees, "disbursements": disb, "total": fees + disb})
    rows.sort(key=lambda r: r["total"], reverse=True)
    totals = {k: sum((r[k] for r in rows), Decimal("0")) for k in ("fees", "disbursements", "total")}
    if request.GET.get("format") == "csv":
        return _csv("wip.csv", ["File", "Client", "Fees", "Disbursements", "Total"], [
            [r["matter"].file_number, r["matter"].client.name, r["fees"], r["disbursements"], r["total"]] for r in rows
        ])
    return render(request, "core/report_wip.html", {"rows": rows, "totals": totals})


@require_perm("financial_reports")
def report_debtors(request):
    """Aged debtors: outstanding fee notes bucketed by age."""
    as_at = _parse_date(request.GET.get("as_at"), timezone.localdate())
    buckets = ["current", "d30", "d60", "d90"]
    rows = {}
    for inv in Invoice.objects.filter(status="issued", date__lte=as_at).select_related("matter__client"):
        balance = inv.balance
        if balance <= 0:
            continue
        age = (as_at - inv.date).days
        bucket = "current" if age <= 30 else "d30" if age <= 60 else "d90" if age > 90 else "d60"
        client = inv.matter.client
        row = rows.setdefault(client.pk, {"client": client, **{b: Decimal("0") for b in buckets}, "total": Decimal("0")})
        row[bucket] += balance
        row["total"] += balance
    rows = sorted(rows.values(), key=lambda r: r["total"], reverse=True)
    totals = {k: sum((r[k] for r in rows), Decimal("0")) for k in buckets + ["total"]}
    if request.GET.get("format") == "csv":
        return _csv("debtors.csv", ["Client", "0-30", "31-60", "61-90", "90+", "Total"], [
            [r["client"].name] + [r[b] for b in buckets] + [r["total"]] for r in rows
        ])
    return render(request, "core/report_debtors.html", {"rows": rows, "totals": totals, "as_at": as_at})


@require_perm("trust_view")
def report_trust(request):
    """Trust balances per matter (the trust creditors listing)."""
    as_at = _parse_date(request.GET.get("as_at"), timezone.localdate())
    rows = []
    for matter in Matter.objects.select_related("client").filter(trust_transactions__isnull=False).distinct():
        bal = TrustTransaction.balance_for(matter, as_at)
        if bal:
            rows.append({"matter": matter, "balance": bal})
    total = sum((r["balance"] for r in rows), Decimal("0"))
    if request.GET.get("format") == "csv":
        return _csv("trust_balances.csv", ["File", "Client", "Balance"], [
            [r["matter"].file_number, r["matter"].client.name, r["balance"]] for r in rows
        ])
    return render(request, "core/report_trust.html", {
        "rows": rows, "total": total, "as_at": as_at, "cashbook": TrustTransaction.total_balance(as_at),
    })


@require_perm("financial_reports")
def report_time(request):
    """Recorded time per fee earner over a period."""
    today = timezone.localdate()
    start = _parse_date(request.GET.get("start"), today.replace(day=1))
    end = _parse_date(request.GET.get("end"), today)
    rows = []
    for user in get_user_model().objects.filter(is_active=True).order_by("first_name", "username"):
        qs = TimeEntry.objects.filter(user=user, date__range=(start, end))
        agg = qs.aggregate(minutes=Sum("minutes"), amount=Sum("amount"))
        billable = qs.filter(billable=True).aggregate(m=Sum("minutes"))["m"] or 0
        billed = qs.filter(invoice__isnull=False).aggregate(a=Sum("amount"))["a"] or Decimal("0")
        if agg["minutes"]:
            rows.append({"user": user, "minutes": agg["minutes"], "billable_minutes": billable,
                         "amount": agg["amount"], "billed": billed})
    return render(request, "core/report_time.html", {"rows": rows, "start": start, "end": end})


def report_matters(request):
    status = request.GET.get("status", "open")
    qs = Matter.objects.select_related("client", "responsible")
    if status:
        qs = qs.filter(status=status)
    if request.GET.get("format") == "csv":
        return _csv("matters.csv", ["File", "Client", "Description", "Type", "Status", "Responsible", "Opened"], [
            [m.file_number, m.client.name, m.description, m.get_matter_type_display(), m.get_status_display(),
             m.responsible.get_full_name() or m.responsible.username, m.date_opened] for m in qs
        ])
    return render(request, "core/report_matters.html", {"matters": qs, "status": status,
                                                        "statuses": Matter.STATUS_CHOICES})


# ---------------------------------------------------------------- data import

IMPORT_SESSION_KEY = "pending_import"


@require_perm("import_data")
def data_import(request):
    from . import importers

    kinds = {"clients": "Clients", "matters": "Matters (with optional trust opening balances)"}
    result = None
    pending = request.session.get(IMPORT_SESSION_KEY)
    if request.method == "POST":
        if "confirm" in request.POST and pending:
            kind, text = pending["kind"], pending["text"]
            dry_run = False
        else:
            kind = request.POST.get("kind")
            upload = request.FILES.get("file")
            if kind not in kinds or not upload:
                messages.error(request, "Choose what to import and a CSV file.")
                return redirect("data_import")
            if upload.size > 5 * 1024 * 1024:
                messages.error(request, "The file is too large (5 MB maximum). Split it into smaller files.")
                return redirect("data_import")
            text, dry_run = importers.decode_upload(upload), True
        if kind == "clients":
            result = importers.import_clients(text, dry_run=dry_run)
        else:
            result = importers.import_matters(text, request.user, dry_run=dry_run,
                                              allow_trust=has_perm(request.user, "trust_post"))
        if dry_run and result.ok:
            request.session[IMPORT_SESSION_KEY] = {"kind": kind, "text": text}
        else:
            request.session.pop(IMPORT_SESSION_KEY, None)
        if not dry_run and result.ok:
            AuditLog.objects.create(user=request.user, action="import", object_type=kind, object_id="",
                                    description=f"Imported {result.created} {kind} from CSV")
            messages.success(request, f"Imported {result.created} {kind}.")
            return redirect("client_list" if kind == "clients" else "matter_list")
        return render(request, "core/import.html", {"kinds": kinds, "result": result, "kind": kind,
                                                    "dry_run": dry_run})
    return render(request, "core/import.html", {"kinds": kinds})


@require_perm("import_data")
def import_template(request, kind):
    from . import importers

    if kind == "clients":
        content = importers.template_csv(importers.CLIENT_COLUMNS, importers.CLIENT_EXAMPLE)
    else:
        content = importers.template_csv(importers.MATTER_COLUMNS, importers.MATTER_EXAMPLE)
    response = HttpResponse(content, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{kind}-import-template.csv"'
    return response


def interest_calculator(request):
    """Simple interest on a debt between two dates, optionally capped at the capital (in duplum rule)."""
    result = None
    data = request.GET
    if data.get("principal"):
        try:
            principal = Decimal(data["principal"].replace(",", ""))
            rate = Decimal(data["rate"])
            start, end = date.fromisoformat(data["start"]), date.fromisoformat(data["end"])
            if end < start or principal <= 0 or rate < 0:
                raise ValueError
        except (ValueError, ArithmeticError, KeyError):
            messages.error(request, "Enter a positive amount, a rate and a valid date range.")
        else:
            days = (end - start).days
            interest = (principal * rate / Decimal(100) * Decimal(days) / Decimal(365)).quantize(Decimal("0.01"))
            capped = bool(data.get("in_duplum")) and interest > principal
            if capped:
                interest = principal
            result = {"principal": principal, "rate": rate, "days": days, "interest": interest,
                      "total": principal + interest, "capped": capped, "daily": (principal * rate / 100 / 365)
                      .quantize(Decimal("0.01")), "start": start, "end": end}
    return render(request, "core/interest.html", {"result": result, "today": timezone.localdate()})
