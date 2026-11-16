"""Ishga kela olmaslik: xodim so‘rov yuboradi → asoschi(lar)ga boradi → asoschi qarori xodimga qaytadi."""

from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import record
from apps.notifications.services import notify

from .absence_models import AbsenceRequest
from .models import WorkShift

SCHEDULE_URL = "/management/enterprise/schedule/"
MAX_DAYS = 31


def _fmt(day):
    return f"{day:%d.%m.%Y}"


def period_text(item):
    return _fmt(item.date_from) if item.date_from == item.date_to else f"{_fmt(item.date_from)} – {_fmt(item.date_to)}"


def founders():
    return list(User.objects.filter(role__is_owner=True, is_active=True, status=User.Status.ACTIVE))


def submit(employee, date_from, date_to, reason):
    reason = (reason or "").strip()
    today = timezone.localdate()
    if employee.is_owner:
        raise ValidationError("Asoschi uchun so‘rov kerak emas.")
    if not date_from or not date_to or date_to < date_from:
        raise ValidationError("Sanalarni to‘g‘ri tanlang.")
    if date_from < today - timedelta(days=1):
        raise ValidationError("O‘tib ketgan kunlar uchun so‘rov yuborib bo‘lmaydi.")
    if (date_to - date_from).days + 1 > MAX_DAYS:
        raise ValidationError(f"Bir so‘rov {MAX_DAYS} kundan oshmasin.")
    if len(reason) < 5:
        raise ValidationError("Sababni qisqacha yozing (kamida 5 belgi).")
    with transaction.atomic():
        User.objects.select_for_update().get(pk=employee.pk)
        if AbsenceRequest.objects.filter(employee=employee, status=AbsenceRequest.Status.PENDING,
                                         date_from__lte=date_to, date_to__gte=date_from).exists():
            raise ValidationError("Bu kunlar uchun so‘rovingiz allaqachon ko‘rib chiqilmoqda.")
        item = AbsenceRequest.objects.create(employee=employee, date_from=date_from, date_to=date_to, reason=reason[:1000])
        record(employee, "absence.requested", item, {"from": str(date_from), "to": str(date_to)})
    notify(founders(), "approval", f"{employee.display_name} ishga kela olmasligini bildirdi",
           f"{period_text(item)} · Sabab: {item.reason[:160]}", SCHEDULE_URL, exclude=employee)
    return item


def decide(actor, pk, approve, note=""):
    if not actor.is_owner:
        raise PermissionDenied
    note = (note or "").strip()[:500]
    with transaction.atomic():
        item = AbsenceRequest.objects.select_for_update().select_related("employee").get(pk=pk)
        if item.status != AbsenceRequest.Status.PENDING:
            raise ValidationError("Bu so‘rov allaqachon ko‘rib chiqilgan.")
        item.status = AbsenceRequest.Status.APPROVED if approve else AbsenceRequest.Status.REJECTED
        item.decided_by, item.decision_note, item.decided_at = actor, note, timezone.now()
        item.save(update_fields=["status", "decided_by", "decision_note", "decided_at"])
        cancelled = 0
        if approve:
            # Shu kunlardagi smenalar bekor qilinadi, jadval haqiqiy holatni ko‘rsatadi.
            shifts = WorkShift.objects.select_for_update().filter(
                employee=item.employee, cancelled=False,
                starts_at__date__gte=item.date_from, starts_at__date__lte=item.date_to)
            for shift in shifts:
                shift.cancelled, shift.administrator = True, actor
                shift.notes = (shift.notes + "\n" if shift.notes else "") + "Ishga kela olmaslik so‘rovi tasdiqlandi."
                shift.save()
                cancelled += 1
        record(actor, "absence.decided", item, {"approved": approve, "note": note, "cancelled_shifts": cancelled})
    verdict = "tasdiqlandi" if approve else "rad etildi"
    body = period_text(item) + (f" · Izoh: {note}" if note else "")
    notify([item.employee], "reviewed", f"Ishga kela olmaslik so‘rovingiz {verdict}", body, SCHEDULE_URL)
    return item
