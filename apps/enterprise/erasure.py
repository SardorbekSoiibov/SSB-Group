"""Permanent deletion across the whole database, reachable only through the two-step confirmation.

History tables are protected by database triggers. Those triggers stay active for everything else:
erase_mode() opens them for the current transaction only, after the caller has verified the password.
"""
from contextlib import contextmanager
from decimal import Decimal

from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied
from django.db import connection, models, transaction
from django.db.models import ProtectedError, Q
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import record
from apps.chat.models import Message
from apps.crm.models import Attachment, InquiryNote, Milestone, ProjectComment, ProjectFile, Task, TaskComment
from apps.notifications.models import Notification
from apps.website.models import TeamMember
from .models import (AgreementSnapshot, ApprovalDecision, ApprovalRule, ArchiveAccess, ArchivePolicy, EvaluationWeek,
                     FinanceOperation, LedgerEntry, PayoutDetail, PayoutEvent, PerformanceReview, ProjectArchive,
                     ReviewApproval, WeeklyEvaluation, WeeklyReward, WorkShift)
from .absence_models import AbsenceRequest

# Rows the employee only signed off for other people: those people's records stay, the Founder takes over the signature.
REASSIGNED = [(ApprovalRule, 'updated_by'), (ArchiveAccess, 'updated_by'), (ArchivePolicy, 'updated_by'),
              (FinanceOperation, 'administrator'), (LedgerEntry, 'administrator'), (AgreementSnapshot, 'confirmed_by'),
              (PerformanceReview, 'administrator'), (ReviewApproval, 'administrator'), (WorkShift, 'administrator'),
              (EvaluationWeek, 'created_by'), (WeeklyEvaluation, 'reviewed_by'), (WeeklyReward, 'updated_by'),
              (PayoutEvent, 'actor'), (AbsenceRequest, 'decided_by')]


def _erase_payouts(operations):
    """Payout receipt history belongs to its payout operation and goes with it."""
    raw_delete(plain(PayoutEvent).filter(Q(operation__in=operations) | Q(correction__in=operations)))
    for detail in PayoutDetail.objects.filter(operation__in=operations).exclude(proof=''):
        delete_files_after_commit([(detail.proof.storage, detail.proof.name)])
    raw_delete(plain(PayoutDetail).filter(operation__in=operations))


def plain(model):
    """A queryset without the append-only guards, for use inside erase_mode() only."""
    return models.QuerySet(model=model)


def raw_delete(queryset):
    return queryset._raw_delete(queryset.db)


@contextmanager
def erase_mode():
    if not connection.in_atomic_block:
        raise RuntimeError('erase_mode must run inside a transaction.')
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('ssb.authorized_erase', 'on', true)")
    yield
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('ssb.authorized_erase', 'off', true)")


def delete_files_after_commit(files):
    def run():
        for storage, name in files:
            try:
                storage.delete(name)
            except OSError:
                pass
    if files:
        transaction.on_commit(run)


def finance_rows(employee):
    operations = list(FinanceOperation.objects.filter(employee=employee, agreementsnapshot__isnull=True).values_list('pk', flat=True))
    entries = set(LedgerEntry.objects.filter(Q(employee=employee) | Q(operation__in=operations)).values_list('pk', flat=True))
    while True:
        more = set(LedgerEntry.objects.filter(corrects__in=entries).exclude(pk__in=entries).values_list('pk', flat=True))
        if not more:
            return operations, entries
        entries |= more


def weekly_rewards(employee, operations):
    return WeeklyReward.objects.filter(Q(employee=employee) | Q(operation__in=operations))


def _erase_weekly_history(employee, operations):
    """Other people keep their published places: nobody moves up, the row of the removed person just goes."""
    rewards = [str(pk) for pk in weekly_rewards(employee, operations).values_list('pk', flat=True)]
    evaluations = [str(pk) for pk in WeeklyEvaluation.objects.filter(employee=employee).values_list('pk', flat=True)]
    raw_delete(plain(AuditEvent).filter(Q(target_type='enterprise.weeklyreward', target_id__in=rewards)
                                        | Q(target_type='enterprise.weeklyevaluation', target_id__in=evaluations)))
    raw_delete(plain(WeeklyReward).filter(pk__in=rewards))
    raw_delete(plain(WeeklyEvaluation).filter(pk__in=evaluations))
    mentioned = [{'employee_id': employee.pk}]
    for week in EvaluationWeek.objects.filter(ranking__contains=mentioned):
        kept = [row for row in week.ranking if row.get('employee_id') != employee.pk]
        plain(EvaluationWeek).filter(pk=week.pk).update(ranking=kept)
    for event in AuditEvent.objects.filter(action='performance.week_published', changes__ranking__contains=mentioned):
        kept = [row for row in event.changes['ranking'] if row.get('employee_id') != employee.pk]
        plain(AuditEvent).filter(pk=event.pk).update(changes={**event.changes, 'ranking': kept})


def erase_preview(employee):
    """What the first confirmation step shows. Counts come from the same rows the erase removes."""
    operations, entries = finance_rows(employee)
    reviews = PerformanceReview.objects.filter(employee=employee).count()
    rows = [('Chat xabarlari (ikkala tomondan)', Message.objects.filter(Q(sender=employee) | Q(recipient=employee)).count()),
            ('Moliya yozuvlari (balans va hisobotlar o‘zgaradi)', len(entries)),
            ('Moliyaviy amallar', len(operations)),
            ('Baholashlar', reviews),
            ('Haftalik baholashlar', WeeklyEvaluation.objects.filter(employee=employee).count()),
            ('Haftalik mukofotlar', weekly_rewards(employee, operations).count()),
            ('Ish jadvali yozuvlari', WorkShift.objects.filter(employee=employee).count()),
            ('Arxivdagi loyihalari va fayllari', ProjectArchive.objects.filter(uploader=employee).count()),
            ('Vazifa, loyiha va murojaat izohlari', TaskComment.objects.filter(author=employee).count() + ProjectComment.objects.filter(author=employee).count() + InquiryNote.objects.filter(author=employee).count()),
            ('Bildirishnomalar', Notification.objects.filter(recipient=employee).count()),
            ('Audit yozuvlari', AuditEvent.objects.filter(Q(actor=employee) | Q(target_type='accounts.user', target_id=str(employee.pk))).count()),
            ('Saytdagi jamoa kartasi', TeamMember.objects.filter(user=employee).count())]
    items = ['Hisob, profil, rasm va ochiq sessiyalar'] + [f'{label}: {count}' for label, count in rows if count]
    shares = AgreementSnapshot.objects.filter(shares__contains=[{'employee': employee.pk}]).count()
    if shares:
        items.append(f'Kelishuvlardagi ulushi kompaniyaga o‘tadi: {shares}')
    return items


def _without_share(shares, company, employee_id):
    kept = [share for share in shares if share.get('employee') != employee_id]
    freed = sum((Decimal(str(share['percent'])) for share in shares if share.get('employee') == employee_id), Decimal(0))
    return kept, Decimal(str(company)) + freed


def _release_shares(employee):
    """Later receipts split by these percentages, so a removed person's part goes back to the company."""
    for snapshot in AgreementSnapshot.objects.filter(shares__contains=[{'employee': employee.pk}]):
        shares, company = _without_share(snapshot.shares, snapshot.company_percent, employee.pk)
        plain(AgreementSnapshot).filter(pk=snapshot.pk).update(shares=shares, company_percent=company)
    for operation in FinanceOperation.objects.filter(payload__shares__contains=[{'employee': employee.pk}]):
        shares, company = _without_share(operation.payload['shares'], operation.payload.get('company_percent', 0), employee.pk)
        plain(FinanceOperation).filter(pk=operation.pk).update(payload={**operation.payload, 'shares': shares, 'company_percent': str(company)})


def project_finance_rows(project):
    """Operations and entries belong together, so the set grows until no linked row is left outside it."""
    operations = set(FinanceOperation.objects.filter(project=project).values_list('pk', flat=True))
    operations |= set(AgreementSnapshot.objects.filter(project=project).values_list('operation_id', flat=True))
    entries = set(LedgerEntry.objects.filter(Q(project=project) | Q(agreement__project=project)).values_list('pk', flat=True))
    while True:
        more_entries = set(LedgerEntry.objects.filter(Q(operation__in=operations) | Q(corrects__in=entries)).values_list('pk', flat=True)) - entries
        more_operations = set(LedgerEntry.objects.filter(pk__in=entries | more_entries).values_list('operation_id', flat=True)) - operations
        if not more_entries and not more_operations:
            return operations, entries
        entries |= more_entries
        operations |= more_operations


def project_erase_preview(project):
    """What the first confirmation step shows. Counts come from the same rows the erase removes."""
    operations, entries = project_finance_rows(project)
    tasks = Task.objects.filter(project=project)
    rows = [('Vazifalar', tasks.count()), ('Bosqichlar', Milestone.objects.filter(project=project).count()),
            ('Vazifa izohlari', TaskComment.objects.filter(task__in=tasks).count()),
            ('Vazifa fayllari', Attachment.objects.filter(task__in=tasks).count()),
            ('Loyiha fayllari', ProjectFile.objects.filter(project=project).count()),
            ('Arxivdagi fayllari', ProjectArchive.objects.filter(project=project).count()),
            ('Moliya yozuvlari (balans va hisobotlar o‘zgaradi)', len(entries)),
            ('Moliyaviy amallar', len(operations))]
    return ['Loyiha va uning tarixi'] + [f'{label}: {count}' for label, count in rows if count]


def erase_project(actor, project, request=None):
    if not actor.is_owner:
        raise PermissionDenied('Loyihani faqat Asoschi o‘chira oladi.')
    summary = {'code': project.code, 'name': project.name}
    files = []
    with transaction.atomic():
        with connection.cursor() as cursor:
            # The same lock finance writers and reports use: no money operation can interleave with this.
            cursor.execute('SELECT pg_advisory_xact_lock(73910233)')
        summary['removed'] = project_erase_preview(project)
        tasks = list(Task.objects.filter(project=project))
        task_ids = [str(task.pk) for task in tasks]
        links = [project.get_absolute_url()] + [task.get_absolute_url() for task in tasks]
        for attachment in Attachment.objects.filter(task__in=tasks).exclude(file=''):
            files.append((attachment.file.storage, attachment.file.name))
        for archive in ProjectArchive.objects.filter(project=project).exclude(file=''):
            files.append((archive.file.storage, archive.file.name))
        for item in ProjectFile.objects.filter(project=project).exclude(file=''):
            files.append((item.file.storage, item.file.name))
        if project.cover:
            files.append((project.cover.storage, project.cover.name))
        with erase_mode():
            operations, entries = project_finance_rows(project)
            raw_delete(plain(LedgerEntry).filter(pk__in=entries))
            raw_delete(plain(ApprovalDecision).filter(operation__in=operations))
            _erase_payouts(operations)
            raw_delete(plain(AgreementSnapshot).filter(Q(project=project) | Q(operation__in=operations)))
            raw_delete(plain(FinanceOperation).filter(pk__in=operations))
            raw_delete(plain(ProjectArchive).filter(project=project))
            ArchivePolicy.objects.filter(project=project).delete()
            Notification.objects.filter(url__in=links).delete()
            raw_delete(plain(AuditEvent).filter(Q(target_type='crm.project', target_id=str(project.pk)) | Q(target_type='crm.task', target_id__in=task_ids)))
            project.delete()
        record(actor, 'project.erased', None, summary, request)
        delete_files_after_commit(files)
    return summary


def _end_sessions(employee):
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        if session.get_decoded().get('_auth_user_id') == str(employee.pk):
            session.delete()


def erase_employee(actor, employee, request=None):
    if not actor.is_owner:
        raise PermissionDenied('Xodimni faqat Asoschi o‘chira oladi.')
    if employee.pk == actor.pk or employee.is_owner:
        raise PermissionDenied('Asoschi hisobini o‘chirib bo‘lmaydi.')
    employee_id = employee.pk
    files = []
    with transaction.atomic():
        with connection.cursor() as cursor:
            # The same lock finance writers and reports use: no money operation can interleave with this.
            cursor.execute('SELECT pg_advisory_xact_lock(73910233)')
        summary = erase_preview(employee)
        with erase_mode():
            _end_sessions(employee)
            operations, entries = finance_rows(employee)
            raw_delete(plain(LedgerEntry).filter(pk__in=entries))
            raw_delete(plain(ApprovalDecision).filter(Q(operation__in=operations) | Q(administrator=employee)))
            _erase_weekly_history(employee, operations)
            _erase_payouts(operations)
            raw_delete(plain(FinanceOperation).filter(pk__in=operations))
            plain(FinanceOperation).filter(employee=employee).update(employee=None)
            _release_shares(employee)
            reviews = list(PerformanceReview.objects.filter(employee=employee).values_list('pk', flat=True))
            raw_delete(plain(ReviewApproval).filter(review__in=reviews))
            raw_delete(plain(PerformanceReview).filter(pk__in=reviews))
            WorkShift.objects.filter(employee=employee).delete()
            AbsenceRequest.objects.filter(employee=employee).delete()
            for model, field in REASSIGNED:
                plain(model).filter(**{field: employee}).update(**{field: actor})
            for archive in ProjectArchive.objects.filter(uploader=employee):
                if archive.file:
                    files.append((archive.file.storage, archive.file.name))
            raw_delete(plain(ProjectArchive).filter(uploader=employee))
            messages = Message.objects.filter(Q(sender=employee) | Q(recipient=employee))
            for message in messages.exclude(attachment=''):
                files.append((message.attachment.storage, message.attachment.name))
            Notification.objects.filter(dedupe_key__in=[f'chat:{pk}' for pk in messages.values_list('pk', flat=True)]).delete()
            messages.delete()
            TaskComment.objects.filter(author=employee).delete()
            ProjectComment.objects.filter(author=employee).delete()
            InquiryNote.objects.filter(author=employee).delete()
            for member in TeamMember.objects.filter(user=employee):
                photo = (member.photo.storage, member.photo.name) if member.photo else None
                try:
                    with transaction.atomic():
                        member.delete()
                    if photo:
                        files.append(photo)
                except ProtectedError:
                    TeamMember.objects.filter(pk=member.pk).update(user=None)
            raw_delete(plain(AuditEvent).filter(Q(actor=employee) | Q(target_type='accounts.user', target_id=str(employee_id))))
            if employee.photo:
                files.append((employee.photo.storage, employee.photo.name))
            if employee.contract:
                files.append((employee.contract.storage, employee.contract.name))
            employee.delete()
        # Deliberately holds no name: only the fact that an account was removed, and by whom.
        record(actor, 'user.erased', None, {'employee_id': employee_id, 'removed': summary}, request)
        delete_files_after_commit(files)
    return summary
