"""Company archive: per-visit code, Founder rotation, shared RAR/ZIP project files, math-checked downloads."""
import secrets
import uuid
from pathlib import Path

from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import record
from apps.notifications.services import notify
from .models import ArchiveAccess, ArchiveAccessAttempt, ProjectArchive

GRANT_KEY = 'company_archive_access'
# Upper bound only: ArchiveVisitMiddleware also relocks as soon as the user navigates elsewhere.
GRANT_SECONDS = 3600
CHALLENGE_KEY = 'company_archive_challenge'
CHALLENGE_SECONDS = 300
ARCHIVE_EXTENSIONS = ('.rar', '.zip')


def require_staff(user):
    if not user.is_authenticated or not user.is_active or user.status != User.Status.ACTIVE or (user.role_id and not user.role.is_active):
        raise PermissionDenied('Arxiv faqat faol xodimlar uchun.')


def grant_access(request, policy):
    request.session[GRANT_KEY] = {'user': request.user.pk, 'version': policy.version,
        'expires': timezone.now().timestamp() + GRANT_SECONDS}


def has_archive_access(request, policy=None):
    user = request.user
    if not user.is_authenticated or not user.is_active or user.status != User.Status.ACTIVE or (user.role_id and not user.role.is_active):
        return False
    policy = policy or ArchiveAccess.load()
    grant = request.session.get(GRANT_KEY, {})
    return bool(policy.access_hash and isinstance(grant, dict) and grant.get('user') == user.pk
                and grant.get('version') == policy.version
                and isinstance(grant.get('expires'), (int,float)) and grant['expires'] > timezone.now().timestamp())


@transaction.atomic
def set_archive_code(actor, code):
    require_staff(actor)
    if not actor.is_owner:
        raise PermissionDenied('Arxiv kodini faqat Asoschi o‘zgartiradi.')
    if not isinstance(code,str) or not 8 <= len(code) <= 128 or not code.strip():
        raise ValidationError('Arxiv kodi 8–128 belgidan iborat bo‘lsin.')
    ArchiveAccess.load()
    policy = ArchiveAccess.objects.select_for_update().get(pk=1)
    policy.access_hash = make_password(code)
    policy.version += 1
    policy.updated_by = actor
    policy.save(update_fields=['access_hash','version','updated_by','updated_at'])
    record(actor, 'archive.section_code_changed', policy, {'version':policy.version})
    return policy


def verify_archive_code(request, code):
    require_staff(request.user)
    failure = None
    with transaction.atomic():
        # Stable per-user lock makes the attempt limit apply across all workers.
        User.objects.select_for_update().get(pk=request.user.pk)
        now = timezone.now()
        attempt, _ = ArchiveAccessAttempt.objects.get_or_create(user=request.user, defaults={'window_started':now})
        if (now-attempt.window_started).total_seconds() >= 900:
            attempt.failures, attempt.window_started = 0, now
        policy = ArchiveAccess.load()
        if attempt.failures >= 8:
            failure = 'Juda ko‘p urinish. 15 daqiqadan keyin qayta urinib ko‘ring.'
        elif not policy.access_hash:
            failure = 'Asoschi hali arxiv kodini belgilamagan.'
        elif not isinstance(code,str) or len(code)>128 or not check_password(code,policy.access_hash):
            attempt.failures += 1
            attempt.save(update_fields=['failures','window_started'])
            record(request.user,'archive.section_access_denied',None)
            failure = 'Arxiv kodi noto‘g‘ri.'
        else:
            attempt.failures = 0
            attempt.window_started = now
            attempt.save(update_fields=['failures','window_started'])
            grant_access(request,policy)
            record(request.user,'archive.section_unlocked',None,{'version':policy.version})
    if failure:
        raise ValidationError(failure)


def can_download_archive(request, archive):
    return has_archive_access(request)


def active_archives():
    return ProjectArchive.objects.all()


def can_remove_archive(user, archive):
    return user.is_owner or archive.uploader_id == user.pk


def remove_archive(request, pk):
    """Only the author or the Founder, inside an unlocked visit. Row and file both go; the audit line stays."""
    from .erasure import delete_files_after_commit, erase_mode, plain, raw_delete
    require_staff(request.user)
    if not has_archive_access(request):
        raise PermissionDenied('Avval arxiv bo‘limining kodini kiriting.')
    with transaction.atomic():
        archive = get_object_or_404(ProjectArchive.objects.select_for_update(), pk=pk)
        if not can_remove_archive(request.user, archive):
            raise PermissionDenied('Loyihani faqat muallifi yoki Asoschi o‘chira oladi.')
        record(request.user, 'archive.removed', archive, {
            'sha256': archive.sha256, 'filename': archive.filename, 'project_name': archive.display_project_name})
        with erase_mode():
            raw_delete(plain(ProjectArchive).filter(pk=archive.pk))
        delete_files_after_commit([(archive.file.storage, archive.file.name)])
    return archive


def new_challenge(request, archive_id):
    """A fresh arithmetic question for one file; the answer stays server-side in the session."""
    op = secrets.choice('+-×')
    if op == '×':
        a, b = 2 + secrets.randbelow(11), 2 + secrets.randbelow(11)
        answer = a * b
    else:
        a, b = 10 + secrets.randbelow(90), 1 + secrets.randbelow(50)
        if op == '-' and b > a:
            a, b = b, a
        answer = a + b if op == '+' else a - b
    request.session[CHALLENGE_KEY] = {'archive': archive_id, 'answer': answer, 'attempts': 0,
                                      'expires': timezone.now().timestamp() + CHALLENGE_SECONDS}
    return f'{a} {op} {b}'


def check_challenge(request, archive_id, raw):
    """True once for a correct answer; any answer consumes the question."""
    data = request.session.pop(CHALLENGE_KEY, None)
    if not isinstance(data, dict) or data.get('archive') != archive_id:
        return False
    if not isinstance(data.get('expires'), (int, float)) or data['expires'] <= timezone.now().timestamp():
        return False
    text = raw.strip() if isinstance(raw, str) else ''
    if not text.lstrip('-').isdigit() or len(text) > 6:
        return False
    return int(text) == data.get('answer')


def upload_archive(request, project_name, upload, upload_key):
    require_staff(request.user)
    if not has_archive_access(request):
        raise PermissionDenied('Avval arxiv bo‘limining kodini kiriting.')
    name = project_name.strip() if isinstance(project_name,str) else ''
    if not 2 <= len(name) <= 200 or any(ord(c)<32 for c in name):
        raise ValidationError('Loyiha nomi 2–200 belgidan iborat bo‘lsin.')
    try:
        key = uuid.UUID(str(upload_key))
    except (ValueError, TypeError):
        raise ValidationError('Fayl so‘rovi identifikatori noto‘g‘ri. Sahifani yangilang.')
    filename = Path(upload.name.replace('\\','/')).name[:200]
    if Path(filename).suffix.lower() not in ARCHIVE_EXTENSIONS:
        raise ValidationError('Loyihani RAR yoki ZIP arxiv ko‘rinishida yuklang.')
    from .operations import inspect_upload
    digest, scan = inspect_upload(upload)
    with transaction.atomic():
        policy = ArchiveAccess.objects.select_for_update().get(pk=1)
        if not has_archive_access(request,policy):
            raise PermissionDenied('Arxiv kodi yangilandi yoki ruxsat muddati tugadi. Kodni qayta kiriting.')
        existing = ProjectArchive.objects.filter(upload_key=key).first()
        if existing:
            if (existing.uploader_id,existing.project_name,existing.sha256,existing.filename)!=(request.user.pk,name,digest,filename):
                raise ValidationError('Bu so‘rov identifikatori boshqa faylga tegishli.')
            return existing
        item = ProjectArchive(project_name=name,uploader=request.user,file=upload,
            filename=filename,size=upload.size,sha256=digest,scan_status=scan,upload_key=key)
        try:
            item.save()
            record(request.user,'archive.uploaded',item,{'sha256':digest,'scan':scan,'project_name':name})
            recipients=User.objects.filter(is_active=True,status=User.Status.ACTIVE)
            notify(recipients,'project_status','Umumiy arxivga yangi fayl qo‘shildi',
                'Faylni ko‘rish uchun arxiv bo‘limi kodini kiriting.',
                '/management/enterprise/archives/',f'archive:{item.pk}',exclude=request.user)
        except Exception:
            if item.file and item.file._committed:
                item.file.delete(save=False)
            raise
    return item
