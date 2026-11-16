"""Deleting a project: Founder only, two steps, nothing left behind, other projects untouched."""
import uuid
from datetime import timedelta

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db import DatabaseError, connection, transaction
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import record
from apps.core.testing import PASSWORD, CompanyTestCase
from apps.crm.models import Attachment, Milestone, Project, Task, TaskComment
from apps.enterprise import finance, operations
from apps.enterprise.erasure import project_erase_preview
from apps.enterprise.forms import ReviewForm
from apps.enterprise.models import AgreementSnapshot, FinanceOperation, LedgerEntry
from apps.notifications.models import Notification


class ProjectEraseTests(CompanyTestCase):
    def setUp(self):
        cache.clear()
        self.doomed = Project.objects.create(code='DEL-1', name='Ochiriladigan', manager=self.founder, created_by=self.founder)
        self.kept = Project.objects.create(code='KEEP-1', name='Qoladigan', manager=self.founder, created_by=self.founder)
        self.task = Task.objects.create(project=self.doomed, title='Vazifa', assignee=self.dev, created_by=self.founder)
        self.other_task = Task.objects.create(project=self.kept, title='Boshqa vazifa', assignee=self.dev, created_by=self.founder)
        self.url = reverse('crm:project_erase', args=[self.doomed.pk])

    def money(self, kind, amount, **extra):
        operation = finance.request_operation(self.founder, kind=kind, amount=amount, currency='UZS', description='Sinov amali',
                                              idempotency_key=uuid.uuid4(), **extra)
        operation.refresh_from_db()
        if operation.status == FinanceOperation.Status.PENDING:
            finance.decide(self.ceo, operation.pk, True, 'Sinov uchun tasdiqlandi')
        return operation

    def history(self, project):
        project.members.add(self.dev)
        self.money('agreement', '1000000', project=project, payload={'company_percent': '50', 'shares': [{'employee': self.dev.pk, 'percent': '50'}]})
        self.money('receipt', '1000000', project=project)
        # In production these rows were committed long before; settle the deferred ledger check as a commit would.
        with connection.cursor() as cursor:
            cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
            cursor.execute('SET CONSTRAINTS ALL DEFERRED')

    def erase(self, password=PASSWORD):
        return self.client.post(self.url, {'confirm_password': password}, follow=True)

    def test_only_the_founder_can_delete_and_only_the_founder_sees_the_button(self):
        self.login(self.ceo)
        self.assertNotContains(self.client.get(self.doomed.get_absolute_url()), 'project-danger')
        self.assertEqual(self.client.post(self.url, {'confirm_password': PASSWORD}).status_code, 403)
        self.assertTrue(Project.objects.filter(pk=self.doomed.pk).exists())
        self.login(self.founder)
        self.assertContains(self.client.get(self.doomed.get_absolute_url()), 'project-danger')

    def test_wrong_password_keeps_everything(self):
        self.login(self.founder)
        self.assertContains(self.erase('wrong-password-value'), 'Parol noto')
        self.assertTrue(Project.objects.filter(pk=self.doomed.pk).exists())

    def test_removes_the_project_with_everything_tied_to_it(self):
        Milestone.objects.create(project=self.doomed, title='Bosqich')
        TaskComment.objects.create(task=self.task, author=self.dev, body='Izoh')
        attachment = Attachment(task=self.task, uploaded_by=self.dev, original_name='a.txt', size=1)
        attachment.file.save('a.txt', ContentFile(b'x'))
        name, storage = attachment.file.name, attachment.file.storage
        record(self.founder, 'project.updated', self.doomed)
        record(self.founder, 'task.created', self.task)
        Notification.objects.create(recipient=self.dev, kind='announcement', title='Eski havola', url=self.task.get_absolute_url())
        self.login(self.founder)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.erase()
        self.assertContains(response, 'loyihasi bazadan o')
        self.assertFalse(Project.objects.filter(pk=self.doomed.pk).exists())
        self.assertFalse(Task.objects.filter(pk=self.task.pk).exists())
        self.assertFalse(storage.exists(name))
        self.assertFalse(Notification.objects.filter(title='Eski havola').exists())
        self.assertFalse(AuditEvent.objects.filter(target_type='crm.project', target_id=str(self.doomed.pk)).exists())
        erased = AuditEvent.objects.get(action='project.erased')
        self.assertEqual((erased.actor, erased.changes['code']), (self.founder, 'DEL-1'))
        self.assertTrue(Task.objects.filter(pk=self.other_task.pk).exists())

    def test_money_of_this_project_goes_and_other_projects_money_stays(self):
        self.history(self.doomed)
        self.history(self.kept)
        kept_entries = LedgerEntry.objects.filter(project=self.kept).count()
        self.assertGreater(kept_entries, 0)
        self.assertTrue(any('Moliya yozuvlari' in item for item in project_erase_preview(self.doomed)))
        self.login(self.founder)
        self.erase()
        self.assertFalse(Project.objects.filter(pk=self.doomed.pk).exists())
        self.assertFalse(FinanceOperation.objects.filter(project=self.doomed.pk).exists())
        self.assertFalse(AgreementSnapshot.objects.filter(project=self.doomed.pk).exists())
        self.assertEqual(LedgerEntry.objects.filter(project=self.kept).count(), kept_entries)
        self.assertEqual(LedgerEntry.objects.exclude(project=self.kept).exclude(project__isnull=True).count(), 0)

    def test_history_protection_is_back_on_after_deleting(self):
        self.history(self.kept)
        self.login(self.founder)
        self.erase()
        entry = LedgerEntry.objects.filter(project=self.kept).first()
        with self.assertRaises(DatabaseError), transaction.atomic():
            type(entry).objects.filter(pk=entry.pk)._raw_delete('default')

    def test_status_buttons_work_with_one_comment_field(self):
        self.login(self.founder)
        page = self.client.get(self.doomed.get_absolute_url())
        self.assertContains(page, 'name="to"')
        response = self.client.post(reverse('crm:project_transition', args=[self.doomed.pk]), {'to': 'cancelled', 'comment': ''}, follow=True)
        self.doomed.refresh_from_db()
        self.assertNotEqual(self.doomed.status, 'cancelled')
        self.assertEqual(response.status_code, 200)


class ReviewFormTests(CompanyTestCase):
    def form(self, **values):
        today = timezone.localdate()
        data = {'employee': self.dev.pk, 'period_start': str(today), 'period_end': str(today), 'feedback': 'Rahbar izohi matni'}
        return ReviewForm({**data, **values}, actor=self.founder)

    def test_end_before_start_is_explained_at_the_field(self):
        form = self.form(period_start='2026-11-04', period_end='2016-11-11')
        self.assertFalse(form.is_valid())
        self.assertIn('boshlanish sanasidan oldin', form.errors['period_end'][0])

    def test_period_over_a_year_is_explained_at_the_field(self):
        form = self.form(period_start='2024-01-01', period_end='2026-01-01')
        self.assertFalse(form.is_valid())
        self.assertIn('1 yildan', form.errors['period_end'][0])

    def test_short_note_is_explained_in_uzbek(self):
        form = self.form(feedback='qisqa')
        self.assertFalse(form.is_valid())
        self.assertIn('kamida 10', form.errors['feedback'][0])

    def test_empty_form_starts_with_this_month(self):
        form = ReviewForm(actor=self.founder)
        today = timezone.localdate()
        self.assertEqual((form.initial['period_start'], form.initial['period_end']), (today.replace(day=1), today))

    def test_page_prepares_unified_weekly_evaluations(self):
        from apps.enterprise import performance_system as ps
        from apps.enterprise.models import WeeklyEvaluation
        self.login(self.founder)
        url = reverse('enterprise:performance')
        self.assertNotContains(self.client.get(url), 'AI gateway')
        response = self.client.post(url, {'week': str(ps.last_week()), **ps.DEFAULT_WEIGHTS}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(WeeklyEvaluation.objects.filter(employee=self.dev).exists())
        self.assertEqual(WeeklyEvaluation.objects.get(employee=self.dev).original_score, 0)

    def test_analysis_states_the_real_numbers(self):
        today = timezone.localdate()
        project = Project.objects.create(code='REV-1', name='Baholash', manager=self.founder, created_by=self.founder)
        Task.objects.create(project=project, title='Muddatli', assignee=self.dev, deadline=today, created_by=self.founder)
        review = operations.create_review(self.founder, self.dev, today, today, 'Rahbar izohi matni')
        self.assertIn('1 ta vazifa muddati tushgan, 0 tasi yakunlangan', review.analysis)


class RankingForEveryoneTests(CompanyTestCase):
    def setUp(self):
        today = timezone.localdate()
        self.approved = operations.create_review(self.founder, self.dev, today, today, 'Maxfiy rahbar izohi', 80, 90)
        operations.approve_review(self.founder, self.approved)
        self.draft = operations.create_review(self.founder, self.designer, today, today, 'Tasdiqlanmagan izoh', 10, 10)
        self.url = reverse('enterprise:performance_history')

    def test_every_employee_finds_the_ranking_in_the_menu_and_sees_approved_scores(self):
        self.login(self.designer)
        response = self.client.get(self.url)
        self.assertContains(response, 'Baholash va reyting')
        self.assertEqual([item.employee for item in response.context['ranking']], [self.dev])

    def test_ranking_does_not_show_other_peoples_comments_or_unapproved_scores(self):
        self.login(self.designer)
        response = self.client.get(self.url)
        self.assertNotContains(response, 'Maxfiy rahbar izohi')
        self.assertNotContains(response, 'Tasdiqlanmagan izoh')
        self.assertEqual(list(response.context['reviews']), [])

    def test_own_row_is_marked_and_own_review_stays_visible(self):
        self.login(self.dev)
        response = self.client.get(self.url)
        self.assertContains(response, '(siz)')
        self.assertContains(response, 'Maxfiy rahbar izohi')

    def test_employees_still_cannot_create_or_approve(self):
        self.login(self.designer)
        self.assertNotContains(self.client.get(self.url), 'data-record-template="review-form"')
        self.assertEqual(self.client.post(self.url, {'employee': self.dev.pk}).status_code, 405)
        self.assertIn(self.client.post(reverse('enterprise:review_approve', args=[self.draft.pk])).status_code, [302, 403])
        self.assertFalse(hasattr(type(self.draft).objects.get(pk=self.draft.pk), 'reviewapproval'))

    def test_inactive_people_leave_the_ranking(self):
        self.dev.status = self.dev.Status.DEACTIVATED
        self.dev.save()
        self.login(self.designer)
        self.assertEqual(self.client.get(self.url).context['ranking'], [])

