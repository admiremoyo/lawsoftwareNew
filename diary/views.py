import calendar
from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.utils import safe_next

from .forms import DiaryEntryForm
from .models import DiaryEntry


def diary(request):
    """Month view plus an agenda list for the selected fee earner."""
    today = timezone.localdate()
    try:
        year, month = int(request.GET.get("year", today.year)), int(request.GET.get("month", today.month))
        first = date(year, month, 1)
    except ValueError:
        first = today.replace(day=1)
    user_id = request.GET.get("user", str(request.user.pk))
    tz = timezone.get_current_timezone()
    last = date(first.year, first.month, calendar.monthrange(first.year, first.month)[1])
    qs = DiaryEntry.objects.filter(
        start__gte=datetime.combine(first, time.min, tzinfo=tz),
        start__lte=datetime.combine(last, time.max, tzinfo=tz),
    ).select_related("matter", "assigned_to")
    if user_id:
        qs = qs.filter(assigned_to_id=user_id)
    by_day = {}
    for entry in qs:
        by_day.setdefault(timezone.localtime(entry.start).date(), []).append(entry)
    weeks = [
        [{"date": d, "in_month": d.month == first.month, "entries": by_day.get(d, [])} for d in week]
        for week in calendar.Calendar(firstweekday=0).monthdatescalendar(first.year, first.month)
    ]
    prev_month = (first - timedelta(days=1)).replace(day=1)
    next_month = (last + timedelta(days=1))
    return render(request, "diary/diary.html", {
        "weeks": weeks, "first": first, "today": today, "prev": prev_month, "next": next_month,
        "users": get_user_model().objects.filter(is_active=True), "selected_user": user_id,
        "agenda": qs.filter(completed=False, start__date__gte=today)[:30] if first <= today <= last else qs[:30],
    })


def entry_form(request, pk=None):
    entry = get_object_or_404(DiaryEntry, pk=pk) if pk else None
    initial = {"assigned_to": request.user, "matter": request.GET.get("matter")}
    if request.GET.get("date"):
        initial["start"] = f"{request.GET['date']}T09:00"
    form = DiaryEntryForm(request.POST or None, instance=entry, initial=initial)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(request, "Diary entry saved.")
        if obj.matter and request.GET.get("matter"):
            return redirect(obj.matter.get_absolute_url() + "?tab=diary")
        start = timezone.localtime(obj.start)
        return redirect(f"/diary/?year={start.year}&month={start.month}&user={obj.assigned_to_id}")
    return render(request, "form.html", {"form": form, "title": "Diary entry", "delete_url":
                                         f"/diary/{entry.pk}/delete/" if entry else None})


def entry_toggle(request, pk):
    entry = get_object_or_404(DiaryEntry, pk=pk)
    if request.method == "POST":
        entry.completed = not entry.completed
        entry.save(update_fields=["completed"])
    return redirect(safe_next(request, "/diary/"))


def entry_delete(request, pk):
    entry = get_object_or_404(DiaryEntry, pk=pk)
    if request.method == "POST":
        entry.delete()
        messages.success(request, "Diary entry deleted.")
    return redirect("diary")
