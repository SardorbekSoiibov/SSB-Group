from .models import AuditEvent

SENSITIVE_FIELDS = {"password", "last_login", "token"}

ACTION_LABELS = {
    "user.created": "Xodim qo'shildi",
    "user.updated": "Xodim ma'lumotlari o'zgardi",
    "user.status": "Hisob holati o'zgardi",
    "notifications.cleared": "Bildirishnomalar tozalandi",
    "user.invite_link": "Taklif havolasi yaratildi",
    "user.password_changed": "Parol o'zgartirildi",
    "user.reset_link": "Parolni tiklash havolasi yaratildi",
    "user.password_reset": "Asoschi xodimga yangi parol o'rnatdi",
    "role.created": "Rol yaratildi",
    "role.updated": "Rol huquqlari o'zgardi",
    "department.saved": "Bo'lim saqlandi",
    "project.created": "Loyiha yaratildi",
    "project.updated": "Loyiha o'zgardi",
    "project.status": "Loyiha holati o'zgardi",
    "rating.saved": "Haftalik reyting saqlandi",
    "project.erased": "Loyiha butunlay o'chirildi",
    "data.reset": "Ma'lumotlar bo'limi tozalandi",
    "project.members": "Loyiha jamoasi o'zgardi",
    "project.approval": "Loyiha tasdiqlandi",
    "project.to_portfolio": "Portfolio uchun qoralama yaratildi",
    "task.created": "Vazifa yaratildi",
    "task.updated": "Vazifa o'zgardi",
    "task.status": "Vazifa holati o'zgardi",
    "task.review": "Ish ko'rib chiqildi",
    "task.progress": "Vazifa bajarilishi yangilandi",
    "task.reassigned": "Vazifa boshqa xodimga o'tkazildi",
    "project.file": "Loyihaga fayl yuklandi",
    "inquiry.updated": "Murojaat o'zgardi",
    "inquiry.converted": "Murojaat loyihaga aylantirildi",
    "client.saved": "Mijoz saqlandi",
    "cms.saved": "Kontent saqlandi",
    "cms.publish": "Kontent nashr holati o'zgardi",
    "settings.updated": "Sozlamalar o'zgardi",
    "settings.accent": "Boshqaruv paneli rangi o'zgardi",
    "announcement.created": "E'lon yuborildi",
    "announcement.deleted": "E'lon o'chirildi",
    "auth.login": "Tizimga kirdi",
    "auth.login_failed": "Tizimga kirish rad etildi",
    "auth.logout": "Tizimdan chiqdi",
    "dashboard.layout": "Bosh sahifa joylashuvi o'zgardi",
    "desktop.downloaded": "Windows ilovasi yuklab olindi",
    "finance.decision": "Moliyaviy so'rov bo'yicha qaror qabul qilindi",
    "finance.posted": "Moliyaviy yozuv reyestrga kiritildi",
    "finance.report_export": "Moliyaviy hisobot yuklab olindi",
    "finance.requested": "Moliyaviy so'rov yuborildi",
    "finance.rule_changed": "Moliyaviy qoida o'zgardi",
    "finance.accrued": "Loyiha yakuni bo'yicha xodim daromadi hisoblandi",
    "finance.payout": "Xodimga haqiqiy to'lov qayd etildi",
    "finance.payout_confirmed": "Xodim to'lovni olganini tasdiqladi",
    "finance.payout_disputed": "Xodim to'lovga e'tiroz bildirdi",
    "finance.payout_resolved": "To'lov bo'yicha e'tiroz ko'rib chiqildi",
    "performance.approved": "Baholash tasdiqlandi",
    "performance.created": "Baholash yaratildi",
    "role.status": "Rol holati o'zgardi",
    "schedule.saved": "Ish jadvali saqlandi",
    "user.verified": "Tasdiq belgisi o'zgardi",
    "user.erased": "Xodim bazadan butunlay o'chirildi",
    "archive.section_code_changed": "Arxiv kodi o'zgartirildi",
    "archive.section_unlocked": "Arxiv bo'limi ochildi",
    "archive.section_access_denied": "Arxivga noto'g'ri kod kiritildi",
    "archive.uploaded": "Arxivga loyiha qo'shildi",
    "archive.downloaded": "Arxivdan fayl yuklab olindi",
    "archive.removed": "Arxivdan loyiha o'chirildi",
    "archive.challenge_failed": "Yuklab olish misoli noto'g'ri yechildi",
    "archive.integrity_failed": "Arxiv fayli yaxlitlik tekshiruvidan o'tmadi",
    "audit.cleared": "Audit tarixi tozalandi",
}

# Asoschi tanlay oladigan tozalash davrlari: kalit -> (kundan eski, nomi). None — hammasi.
CLEAR_PERIODS = {
    "30": (30, "30 kundan eski yozuvlar"),
    "90": (90, "90 kundan eski yozuvlar"),
    "365": (365, "1 yildan eski yozuvlar"),
    "all": (None, "Barcha yozuvlar"),
}


def _ip(request):
    return request.META.get("REMOTE_ADDR") if request else None


def _plain(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple, set)):
        return [_plain(v) for v in value]
    if hasattr(value, "all") and callable(value.all):  # querysets / m2m
        return [str(v) for v in value.all()]
    return str(value)


def form_changes(form):
    """{field: [old, new]} for a bound ModelForm, excluding sensitive fields."""
    changes = {}
    for name in form.changed_data:
        if name in SENSITIVE_FIELDS:
            continue
        old = form.initial.get(name)
        new = form.cleaned_data.get(name)
        if hasattr(old, "pk"):
            old = str(old)
        elif hasattr(form.fields[name], "queryset") and old is not None:
            qs = form.fields[name].queryset
            ids = [getattr(item, "pk", item) for item in (old if isinstance(old, (list, tuple)) else [old])]
            old = [str(o) for o in qs.filter(pk__in=ids)]
        changes[name] = [_plain(old), _plain(new)]
    return changes


def clear_events(actor, period, request=None):
    """Audit yozuvlarini o'chiradi (faqat asoschi chaqiradi) va buni o'zi yangi yozuv sifatida qayd etadi.

    Yozuvlar alohida-alohida o'zgartirib/o'chirib bo'lmaydi (model himoyasi), bu yerda esa butun davr
    bir martada, ochiq iz qoldirgan holda tozalanadi.
    """
    from datetime import timedelta

    from django.db import transaction
    from django.utils import timezone

    from apps.enterprise.erasure import erase_mode, raw_delete

    days, label = CLEAR_PERIODS[period]
    with transaction.atomic():
        qs = AuditEvent.objects.all()
        if days:
            qs = qs.filter(created_at__lt=timezone.now() - timedelta(days=days))
        count = qs.count()
        # Bazadagi "o'zgarmas tarix" trigger'i faqat shu tranzaksiya ichida, ruxsat berilgan rejimda o'tkazib yuboradi.
        with erase_mode():
            raw_delete(qs)
        record(actor, "audit.cleared", None, {"davr": label, "o'chirilgan_yozuvlar": count}, request)
    return count


def record(actor, action, target, changes=None, request=None):
    return AuditEvent.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        target_type=target._meta.label_lower if target is not None else "",
        target_id=str(target.pk) if target is not None else "",
        target_repr=str(target)[:255] if target is not None else "",
        changes=changes or {},
        ip=_ip(request),
    )
