"""Founder-only reset of whole data sections ("Ma'lumotlarni tozalash").

Each section names its own tables. Every table that cannot exist without them (a non-null or CASCADE
link) is removed with them; nullable links from other sections are only cleared. Accounts, roles and
system settings are never part of a reset. After the delete the id counters start again from 1, so the
section is really new. Runs inside erase_mode(), the only way past the append-only history triggers.
"""
from django.apps import apps
from django.core.exceptions import PermissionDenied
from django.core.management.color import no_style
from django.db import connection, models, transaction

from apps.audit.services import record
from .erasure import delete_files_after_commit, erase_employee, erase_mode, erase_project, plain, raw_delete

# Never deleted by a reset, whatever links to what.
PROTECTED = {'accounts.User', 'accounts.Role', 'accounts.Department', 'core.WorkspaceSettings', 'website.SiteSettings',
             'enterprise.ArchiveAccess', 'contenttypes.ContentType', 'auth.Permission', 'auth.Group', 'sessions.Session'}

SECTIONS = {
    'loyihalar': ('Loyihalar va vazifalar', 'Loyihalar, vazifalar, bosqichlar, izohlar, fayllar va ularga bog‘liq moliya yozuvlari.',
                  ['crm.Project', 'crm.ProjectAssignment', 'crm.ProjectComment', 'crm.ProjectFile', 'crm.ProjectApproval',
                   'crm.Milestone', 'crm.Task', 'crm.TaskAssignment', 'crm.TaskComment', 'crm.Attachment', 'crm.TaskReview',
                   'crm.TaskEvent']),
    'moliya': ('Moliya', 'Barcha moliyaviy amallar, reyestr yozuvlari, kelishuvlar va to‘lovlar. Balanslar noldan boshlanadi.',
               ['enterprise.FinanceOperation', 'enterprise.ApprovalDecision', 'enterprise.AgreementSnapshot',
                'enterprise.LedgerEntry', 'enterprise.PayoutDetail', 'enterprise.PayoutEvent']),
    'jadval': ('Ish jadvali', 'Barcha smenalar va ishga kela olmaslik so‘rovlari.',
               ['enterprise.WorkShift', 'enterprise.AbsenceRequest']),
    'baholash': ('Baholash va reyting', 'Baholashlar, haftalik reytinglar, o‘rinlar va mukofotlar.',
                 ['enterprise.PerformanceReview', 'enterprise.ReviewApproval', 'enterprise.WeeklyRating', 'enterprise.WeeklyPlace',
                  'enterprise.EvaluationWeek', 'enterprise.WeeklyEvaluation', 'enterprise.WeeklyReward']),
    'chat': ('Xodimlar chati', 'Barcha xabarlar, reaksiyalar va fayllar.', ['chat.Message', 'chat.Reaction']),
    'bildirishnomalar': ('Bildirishnomalar', 'Hamma xodimlarning bildirishnomalari va yuborish tarixi.',
                         ['notifications.Notification', 'notifications.ClearedReminder', 'notifications.ExternalDelivery']),
    'arxiv': ('Xavfsiz arxiv', 'Arxivdagi barcha fayllar va kirish urinishlari. Arxiv kodi saqlanadi.',
              ['enterprise.ProjectArchive', 'enterprise.ArchivePolicy', 'enterprise.ArchiveAccessAttempt']),
    'mijozlar': ('Mijozlar va murojaatlar', 'Mijozlar bazasi, saytdan kelgan murojaatlar va ularning izohlari.',
                 ['crm.Client', 'crm.Inquiry', 'crm.InquiryNote']),
    'elonlar': ('E’lonlar', 'E’lonlar taxtasidagi barcha e’lonlar va rasmlari.', ['crm.Announcement', 'crm.AnnouncementImage']),
    'jihozlar': ('Jihozlar', 'Barcha jihozlar va ularning tarixi.', ['crm.Equipment', 'crm.EquipmentEvent']),
    'hamkorlar': ('Hamkorlar', 'Hamkorlar, logotiplar va shartnoma fayllari.', ['crm.Partner']),
    'audit': ('Audit tarixi', 'Butun audit jurnali. Tozalashning o‘zi yangi jurnalning birinchi yozuvi bo‘ladi.', ['audit.AuditEvent']),
    'xodimlar': ('Xodimlar', 'Asoschidan boshqa barcha xodim hisoblari va ularning shaxsiy ma’lumotlari.', []),
}


def _model(label):
    return apps.get_model(label)


def plan(key):
    """(models to empty, [(model, field)] nullable links to clear). Raises if a protected table would be hit."""
    chosen = [_model(label) for label in SECTIONS[key][2]]
    seen, cleared = set(chosen), []
    changed = True
    while changed:
        changed = False
        for model in apps.get_models(include_auto_created=True):
            if model in seen:
                continue
            for field in model._meta.concrete_fields:
                if not isinstance(field, models.ForeignKey) or field.related_model not in seen:
                    continue
                if field.null and field.remote_field.on_delete is not models.CASCADE:
                    if (model, field) not in cleared:
                        cleared.append((model, field))
                    continue
                seen.add(model)
                chosen.append(model)
                changed = True
                break
    cleared = [(model, field) for model, field in cleared if model not in seen]
    hit = sorted(m._meta.label for m in chosen if m._meta.label in PROTECTED)
    if hit:
        raise RuntimeError(f'Reset of {key!r} would reach protected tables: {hit}')
    return chosen, cleared


def _people(actor):
    from apps.accounts.models import User
    return [user for user in User.objects.exclude(pk=actor.pk) if not user.is_owner]


def preview(key, actor):
    """What the first confirmation step lists: every table that is emptied, with its current row count."""
    if key == 'xodimlar':
        people = _people(actor)
        return len(people), [f'Xodim hisoblari: {len(people)} ta', 'Ularning chat, baholash, moliya, jadval va boshqa shaxsiy yozuvlari',
                             'Sizning (Asoschi) hisobingiz saqlanadi']
    chosen, cleared = plan(key)
    total, items = 0, []
    for model in chosen:
        if model._meta.auto_created:
            continue
        count = plain(model).count()
        total += count
        if count:
            items.append(f'{str(model._meta.verbose_name_plural).capitalize()}: {count} ta')
    if not items:
        items.append('Bu bo‘limda hozir hech qanday yozuv yo‘q')
    for model, field in cleared:
        if plain(model).filter(**{f'{field.name}__isnull': False}).exists():
            items.append(f'{str(model._meta.verbose_name_plural).capitalize()} saqlanadi, faqat bog‘lanish uziladi')
    items.append('Bo‘lim noldan boshlanadi (raqamlash 1 dan)')
    return total, items


def sections(actor):
    return [{'key': key, 'title': title, 'text': text, **dict(zip(('total', 'items'), preview(key, actor)))}
            for key, (title, text, _labels) in SECTIONS.items()]


def _files(chosen):
    files = []
    for model in chosen:
        fields = [f for f in model._meta.concrete_fields if isinstance(f, models.FileField)]
        if not fields:
            continue
        for row in plain(model).only('pk', *[f.name for f in fields]):
            for field in fields:
                value = getattr(row, field.name)
                if value:
                    files.append((value.storage, value.name))
    return files


def reset_section(actor, key, request=None):
    if not actor.is_owner:
        raise PermissionDenied('Ma’lumotlarni faqat Asoschi tozalay oladi.')
    if key not in SECTIONS:
        raise PermissionDenied('Bunday bo‘lim yo‘q.')
    title = SECTIONS[key][0]
    if key == 'xodimlar':
        people = _people(actor)
        for person in people:
            erase_employee(actor, person, request)
        record(actor, 'data.reset', None, {'section': key, 'title': title, 'removed': len(people)}, request)
        return len(people)
    with transaction.atomic():
        with connection.cursor() as cursor:
            # The same lock finance writers and reports use: no money operation can interleave with this.
            cursor.execute('SELECT pg_advisory_xact_lock(73910233)')
        if key == 'loyihalar':
            from apps.crm.models import Project
            for project in Project.objects.all():
                erase_project(actor, project, request)
        total, _items = preview(key, actor)
        chosen, cleared = plan(key)
        files = _files(chosen)
        with erase_mode():
            for model, field in cleared:
                plain(model).filter(**{f'{field.name}__isnull': False}).update(**{field.name: None})
            for model in chosen:
                raw_delete(plain(model).all())
        with connection.cursor() as cursor:
            for statement in connection.ops.sequence_reset_sql(no_style(), chosen):
                cursor.execute(statement)
        record(actor, 'data.reset', None, {'section': key, 'title': title, 'removed': total}, request)
        delete_files_after_commit(files)
    return total
