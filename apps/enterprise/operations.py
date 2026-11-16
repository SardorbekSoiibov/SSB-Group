import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from decimal import Decimal, ROUND_HALF_UP
from urllib.request import Request, urlopen
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from apps.accounts.models import User
from apps.accounts.policies import visible_employees
from apps.audit.services import record
from apps.crm.models import Task
from apps.notifications.services import notify
from .finance import require
from .models import WorkShift, PerformanceReview, ReviewApproval


from .archive_access import set_archive_code, verify_archive_code, can_download_archive, upload_archive


def inspect_upload(upload):
    from apps.core.models import WorkspaceSettings
    maximum = min(settings.ARCHIVE_MAX_MB,WorkspaceSettings.load().archive_max_mb) * 1024 * 1024
    if not upload.size or upload.size > maximum:
        raise ValidationError(f"Fayl 0 dan katta va {settings.ARCHIVE_MAX_MB} MB dan kichik bo‘lsin.")
    extension = Path(upload.name).suffix.lower()
    allowed = {".zip", ".rar", ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".csv", ".docx", ".xlsx"}
    if extension not in allowed:
        raise ValidationError("Bu fayl turiga ruxsat yo‘q. Manba kodini ZIP yoki RAR ichida yuboring.")
    upload.seek(0)
    signature = upload.read(12)
    upload.seek(0)
    if extension in {".zip", ".docx", ".xlsx"}:
        try:
            with zipfile.ZipFile(upload) as archive:
                entries = archive.infolist()
                names=set(archive.namelist())
                if extension=='.docx' and not {'[Content_Types].xml','word/document.xml'}<=names:
                    raise ValidationError('DOCX hujjat tuzilishi noto‘g‘ri.')
                if extension=='.xlsx' and not {'[Content_Types].xml','xl/workbook.xml'}<=names:
                    raise ValidationError('XLSX hujjat tuzilishi noto‘g‘ri.')
                if len(entries) > 10000 or sum(e.file_size for e in entries) > settings.ARCHIVE_UNPACKED_MAX_MB * 1024 * 1024:
                    raise ValidationError("Arxivning ochilgan hajmi yoki fayllar soni cheklovdan oshgan.")
                for entry in entries:
                    name = entry.filename.replace('\\', '/')
                    if PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or ':' in name or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValidationError("Arxivda xavfli yo‘l yoki havola bor.")
                    if entry.file_size > 1024 * 1024 and entry.file_size / max(1, entry.compress_size) > 250:
                        raise ValidationError("Arxivning siqish nisbati xavfli.")
                    if entry.flag_bits & 1:
                        raise ValidationError("Shifrlangan ZIP qabul qilinmaydi: fayllarni tekshirib bo‘lmaydi.")
        except (zipfile.BadZipFile, OSError):
            raise ValidationError("ZIP / hujjat tuzilishi noto‘g‘ri.")
    elif extension == '.rar':
        import rarfile
        try:
            with rarfile.RarFile(upload) as archive:
                entries = archive.infolist()
                if archive.needs_password() or len(entries) > 10000 or sum(e.file_size for e in entries) > settings.ARCHIVE_UNPACKED_MAX_MB * 1024 * 1024:
                    raise ValidationError("RAR hajmi yoki shifrlanishi tekshiruvga mos emas.")
                for entry in entries:
                    name = entry.filename.replace('\\', '/')
                    if name.startswith('/') or '..' in PurePosixPath(name).parts or ':' in name or entry.is_symlink():
                        raise ValidationError("RAR ichidagi yo‘l xavfli.")
        except rarfile.Error:
            raise ValidationError("RAR fayli noto‘g‘ri.")
    elif extension == '.pdf' and not signature.startswith(b'%PDF-'):
        raise ValidationError("PDF imzosi noto‘g‘ri.")
    elif extension in {'.jpg', '.jpeg', '.png', '.webp'}:
        from PIL import Image
        try:
            image = Image.open(upload)
            image.verify()
        except Exception:
            raise ValidationError("Rasm fayli noto‘g‘ri.")
    elif extension in {'.txt','.csv'}:
        sample=upload.read(65536)
        if b'\x00' in sample:raise ValidationError('Matn faylida ikkilik ma’lumot topildi.')
        try:
            import codecs
            codecs.getincrementaldecoder('utf-8')().decode(sample,final=upload.size<=65536)
        except UnicodeDecodeError:raise ValidationError('Matn fayli UTF-8 kodlashida bo‘lsin.')
    upload.seek(0)
    digest = hashlib.sha256()
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)
    scan = "not_configured"
    if settings.MALWARE_SCANNER:
        file_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as temp:
                file_path = temp.name
                for chunk in upload.chunks():
                    temp.write(chunk)
            result = subprocess.run([settings.MALWARE_SCANNER, '--no-summary', file_path], capture_output=True, timeout=90)
            if result.returncode != 0:
                raise ValidationError("Antivirus faylni xavfsiz deb tasdiqlamadi.")
            scan = "clean"
        except (OSError, subprocess.TimeoutExpired):
            raise ValidationError("Antivirus tekshiruvi bajarilmadi. Keyinroq urinib ko‘ring.")
        finally:
            if file_path:
                Path(file_path).unlink(missing_ok=True)
            upload.seek(0)
    elif settings.REQUIRE_MALWARE_SCAN:
        raise ValidationError("Antivirus sozlanmaguncha fayl yuklash o‘chirilgan.")
    return digest.hexdigest(), scan


@transaction.atomic
@transaction.atomic
def save_shift_series(actor, employee, starts_at, ends_at, location, notes='', days=None, repeat=1):
    """Bir xil vaqtli smenani haftaning tanlangan kunlariga va keyingi `repeat` haftaga qo'yadi.

    Hafta har doim dushanbadan boshlanadi. O'tgan kunlar va band vaqtlar o'tkazib yuboriladi.
    Xodimga har smena uchun emas, bitta umumiy bildirishnoma yuboriladi. Natija: (yaratilganlar, o'tkazilganlar soni).
    """
    require(actor, "schedule.manage")
    repeat = max(1, min(int(repeat or 1), 26))
    local_start, local_end = timezone.localtime(starts_at), timezone.localtime(ends_at)
    duration = local_end - local_start
    base = local_start.date()
    monday = base - timezone.timedelta(days=base.weekday())
    weekdays = sorted(set(days)) if days else [base.weekday()]
    today = timezone.localdate()
    created, skipped, attempts, last_error = [], 0, 0, None
    for week in range(repeat):
        for weekday in weekdays:
            day = monday + timezone.timedelta(days=7 * week + weekday)
            if (day < today and repeat * len(weekdays) > 1) or (week == 0 and day < base and days):
                continue  # takrorlashda o'tgan kunlar o'tkazib yuboriladi
            attempts += 1
            begin = timezone.make_aware(datetime.combine(day, local_start.time().replace(tzinfo=None)))
            try:
                with transaction.atomic():
                    created.append(save_shift(actor, employee, begin, begin + duration, location, notes, notify_employee=False))
            except ValidationError as error:
                skipped += 1
                last_error = error
    if not created:
        if attempts == 1 and last_error:
            raise last_error  # bitta smena: aniq sababi ko'rsatiladi (masalan, ustma-ust tushish)
        raise ValidationError("Hech qanday smena qo‘shilmadi: tanlangan vaqtlar boshqa smenalar bilan ustma-ust tushmoqda yoki o‘tib ketgan.")
    first, last = timezone.localtime(created[0].starts_at), timezone.localtime(created[-1].starts_at)
    period = f"{first:%d.%m}" + (f"–{last:%d.%m.%Y}" if len(created) > 1 else f".{first:%Y}")
    notify([employee], "announcement", "Ish jadvali yangilandi",
           f"{len(created)} ta smena · {period} · {first:%H:%M}–{timezone.localtime(created[0].ends_at):%H:%M} · {location}",
           "/management/enterprise/schedule/", f"shift-series:{created[0].pk}")
    return created, skipped


@transaction.atomic
def copy_week(actor, monday):
    """O'tgan haftaning (bekor qilinmagan) smenalarini shu haftaga ko'chiradi. Band vaqtlar o'tkazib yuboriladi."""
    require(actor, "schedule.manage")
    source = WorkShift.objects.filter(cancelled=False, employee__in=visible_employees(actor),
                                      starts_at__date__range=[monday - timezone.timedelta(days=7), monday - timezone.timedelta(days=1)])
    created, skipped, people = [], 0, {}
    for shift in source.select_related("employee"):
        if not shift.employee.is_active:
            skipped += 1
            continue
        try:
            with transaction.atomic():
                new = save_shift(actor, shift.employee, shift.starts_at + timezone.timedelta(days=7), shift.ends_at + timezone.timedelta(days=7),
                                 shift.location, shift.notes, notify_employee=False)
            created.append(new)
            people.setdefault(shift.employee, 0)
            people[shift.employee] += 1
        except ValidationError:
            skipped += 1
    for person, count in people.items():
        notify([person], "announcement", "Ish jadvali yangilandi",
               f"{monday:%d.%m}–{monday + timezone.timedelta(days=6):%d.%m.%Y} haftasi uchun {count} ta smena",
               "/management/enterprise/schedule/", f"shift-week:{person.pk}:{monday.isoformat()}")
    return created, skipped


def save_shift(actor, employee, starts_at, ends_at, location, notes='', shift_id=None, cancel=False, notify_employee=True):
    require(actor, "schedule.manage")
    if not visible_employees(actor).filter(pk=employee.pk).exists():
        raise PermissionDenied
    User.objects.select_for_update().get(pk=employee.pk)
    if not employee.is_active or ends_at <= starts_at or ends_at - starts_at > timezone.timedelta(hours=24):
        raise ValidationError("Faol xodim va 24 soatdan oshmaydigan to‘g‘ri vaqt oralig‘ini tanlang.")
    shift = WorkShift.objects.select_for_update().get(pk=shift_id, employee=employee) if shift_id else None
    if not cancel and WorkShift.objects.filter(employee=employee, cancelled=False, starts_at__lt=ends_at, ends_at__gt=starts_at).exclude(pk=shift_id).exists():
        raise ValidationError("Bu vaqt boshqa ish jadvali bilan ustma-ust tushmoqda.")
    if shift is None:
        shift = WorkShift(employee=employee)
    shift.starts_at, shift.ends_at, shift.location, shift.notes = starts_at, ends_at, location, notes
    shift.cancelled, shift.administrator = cancel, actor
    shift.save()
    record(actor, "schedule.saved", shift, {"employee": employee.pk, "cancelled": cancel, "start": str(starts_at), "end": str(ends_at)})
    if notify_employee:
        notify([employee], "announcement", "Ish jadvali yangilandi", f"{timezone.localtime(starts_at):%d.%m.%Y %H:%M} · {location}", "/management/enterprise/schedule/", f"shift:{shift.pk}:{shift.updated_at.isoformat()}")
    return shift


def delete_shift(actor, shift):
    """Removes the shift from the schedule completely (no "cancelled" leftover)."""
    require(actor, "schedule.manage")
    if not visible_employees(actor).filter(pk=shift.employee_id).exists():
        raise PermissionDenied
    employee, starts_at, pk = shift.employee, shift.starts_at, shift.pk
    record(actor, "schedule.deleted", shift, {"employee": employee.pk, "start": str(starts_at), "end": str(shift.ends_at)})
    shift.delete()
    notify([employee], "announcement", "Ish jadvali yangilandi", f"{timezone.localtime(starts_at):%d.%m.%Y %H:%M} smenasi olib tashlandi",
           "/management/enterprise/schedule/", f"shift-deleted:{pk}")


def performance_metrics(employee, start, end):
    tasks = Task.objects.filter(assignee=employee)
    completed = tasks.filter(status=Task.Status.APPROVED, approved_at__date__range=[start, end])
    done = completed.count()
    ontime = sum(1 for task in completed if not task.deadline or timezone.localdate(task.approved_at) <= task.deadline)
    due = tasks.filter(deadline__range=[start, end]).exclude(status=Task.Status.CANCELLED).count()
    score = (Decimal(ontime) / max(done, 1) * 50 + min(Decimal(done) / max(due, 1), 1) * 50).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) if (done or due) else Decimal('0')
    return {"completed": done, "on_time": ontime, "due": due, "open": tasks.filter(status__in=Task.OPEN).count(),
            "projects": completed.values("project_id").distinct().count(), "score": str(score)}


def create_review(actor, employee, start, end, feedback, quality_score=None, director_score=None):
    require(actor, "performance.manage")
    if start > end or (end - start).days > 366 or not visible_employees(actor).filter(pk=employee.pk).exists():
        raise ValidationError("Davr yoki xodim noto‘g‘ri.")
    metrics = performance_metrics(employee, start, end)
    if quality_score is not None and director_score is not None:
        quality_score, director_score = Decimal(str(quality_score)), Decimal(str(director_score))
        if not (0 <= quality_score <= 100 and 0 <= director_score <= 100):
            raise ValidationError("Rahbar bahosi va sifat 0–100 oralig‘ida bo‘lsin.")
        metrics.update(quality=str(quality_score), director=str(director_score), operational_score=metrics['score'], formula='operational*0.70 + quality*0.20 + director*0.10')
        metrics['score'] = str((Decimal(metrics['score'])*Decimal('.70')+quality_score*Decimal('.20')+director_score*Decimal('.10')).quantize(Decimal('.01')))
    if metrics['completed'] or metrics['due']:
        analysis = (f"Davrda {metrics['due']} ta vazifa muddati tushgan, {metrics['completed']} tasi yakunlangan, {metrics['on_time']} tasi vaqtida topshirilgan. "
                    + ("Kechikish sabablarini muhokama qiling." if metrics['on_time'] < metrics['completed'] else "Yaxshi natijalarni davom ettiring."))
    else:
        analysis = "Bu davrda yakunlangan yoki muddati tushgan vazifa yo‘q, shuning uchun vazifalar bo‘yicha ball 0."
    if metrics['open'] > 10:
        analysis += " Ochiq vazifalar ko‘p: yuklamani qayta ko‘rib chiqing."
    source = "rules"
    if settings.PERFORMANCE_AI_ENDPOINT and settings.PERFORMANCE_AI_KEY:
        if not settings.PERFORMANCE_AI_ENDPOINT.startswith('https://'):
            raise ValidationError("AI xizmati faqat HTTPS orqali ulanadi.")
        data = json.dumps({"metrics": metrics, "task": "Give evidence-based strengths, risks and recommendations in Uzbek. Do not infer personality or recommend salary changes."}).encode()
        try:
            req = Request(settings.PERFORMANCE_AI_ENDPOINT, data=data, headers={"Authorization": f"Bearer {settings.PERFORMANCE_AI_KEY}", "Content-Type": "application/json"})
            with urlopen(req, timeout=20) as response:
                result = json.loads(response.read(50000))
            if not isinstance(result.get('analysis'), str):
                raise ValueError()
            analysis, source = result['analysis'][:10000], 'configured_ai'
        except Exception:
            raise ValidationError("AI xizmati javob bermadi. Kalit/ulanishni tekshiring yoki avtomatik tahlil rejimidan foydalaning.")
    review = PerformanceReview.objects.create(employee=employee, period_start=start, period_end=end, metrics=metrics,
        score=Decimal(metrics['score']), feedback=feedback, analysis=analysis, analysis_source=source, administrator=actor)
    record(actor, "performance.created", review, {"metrics": metrics, "source": source})
    return review


@transaction.atomic
def approve_review(actor, review):
    require(actor, "performance.manage")
    if not visible_employees(actor).filter(pk=review.employee_id).exists() or actor.pk == review.employee_id:
        raise PermissionDenied
    review = PerformanceReview.objects.select_for_update().get(pk=review.pk)
    approval, created = ReviewApproval.objects.get_or_create(review=review, defaults={"administrator": actor})
    if created:
        record(actor, "performance.approved", review)
        notify([review.employee], "reviewed", "Faoliyat bahosi tayyor", "Rahbar baholashni tasdiqladi.", "/management/enterprise/performance/", f"review:{review.pk}")
    return approval
