"""Permanent deletion: two steps, everywhere in the database, and the protection stays on afterwards."""
import inspect
import shutil
import tempfile
import uuid
from datetime import timedelta
from decimal import Decimal

from django.apps import apps
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection, transaction
from django.db.models import PROTECT, ForeignKey
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.audit.services import record
from apps.chat.models import Message
from apps.core.testing import PASSWORD, CompanyTestCase, unlocked_archive_request
from apps.crm.models import Milestone, Task, TaskComment
from apps.enterprise import erasure, finance, operations, performance_system as ps
from apps.enterprise.erasure import erase_preview
from apps.enterprise.models import (AgreementSnapshot, FinanceOperation, LedgerEntry, PerformanceReview, ProjectArchive,
                                    WeeklyEvaluation, WeeklyReward, WorkShift)
from apps.enterprise.tests.test_archive_access import project
from apps.notifications.models import Notification
from apps.website.models import TeamMember


@override_settings(REQUIRE_MALWARE_SCAN=False, MALWARE_SCANNER='')
class ErasureTests(CompanyTestCase):
    def setUp(self):
        cache.clear()
        self.media = tempfile.mkdtemp(prefix='ssb-erase-test-')
        self.override = override_settings(PRIVATE_MEDIA_ROOT=self.media)
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media, ignore_errors=True)

    def approve(self, operation):
        operation.refresh_from_db()
        if operation.status == FinanceOperation.Status.PENDING:
            finance.decide(self.ceo, operation.pk, True, 'Sinov uchun tasdiqlandi')

    def money(self, kind, amount, **extra):
        operation = finance.request_operation(self.founder, kind=kind, amount=amount, currency='UZS', description='Sinov amali',
                                               idempotency_key=uuid.uuid4(), **extra)
        self.approve(operation)
        return operation

    def company_history(self):
        self.money('agreement', '10000000', project=self.project, payload={
            'company_percent': '30', 'shares': [{'employee': self.dev.pk, 'percent': '50'}, {'employee': self.designer.pk, 'percent': '20'}]})
        self.money('receipt', '10000000', project=self.project)
        self.money('salary', '500000', employee=self.dev)
        today = timezone.localdate()
        review = operations.create_review(self.founder, self.dev, today - timedelta(days=7), today, 'Ish sifati izohi', 80, 90)
        operations.approve_review(self.founder, review)
        start = timezone.now() + timedelta(days=1)
        operations.save_shift(self.founder, self.dev, start, start + timedelta(hours=8), 'Ofis')
        self.archive = operations.upload_archive(unlocked_archive_request(self.dev), 'Dev loyihasi', project(), uuid.uuid4())
        self.message = Message.objects.create(sender=self.dev, recipient=self.designer, body='Maxfiy suhbat')
        Notification.objects.create(recipient=self.designer, kind='chat_message', title='Dev', body='Maxfiy suhbat', dedupe_key=f'chat:{self.message.pk}')
        self.task = Task.objects.create(project=self.project, title='Vazifa', assignee=self.dev, created_by=self.founder)
        TaskComment.objects.create(task=self.task, author=self.dev, body='Mening izohim')
        self.card = TeamMember.objects.create(user=self.dev, name='Dev Public', public_title='Dasturchi')
        record(self.dev, 'user.updated', self.dev, {'first_name': ['a', 'b']})
        record(self.founder, 'user.status', self.dev, {'status': ['a', 'b']})
        # In production these rows were committed long before; settle the deferred ledger check as a commit would.
        with connection.cursor() as cursor:
            cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
            cursor.execute('SET CONSTRAINTS ALL DEFERRED')

    def erase(self, user=None, password=PASSWORD):
        return self.client.post(reverse('crm:employee_erase', args=[(user or self.dev).pk]), {'confirm_password': password})

    def test_only_the_founder_with_the_right_password_can_erase(self):
        url = reverse('crm:employee_erase', args=[self.dev.pk])
        for actor in (self.ceo, self.cofounder, self.lead):
            self.login(actor)
            self.assertEqual(self.erase(password=PASSWORD).status_code, 403)
        self.login(self.founder)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.erase(password='noto‘g‘ri-parol')
        self.assertTrue(User.objects.filter(pk=self.dev.pk).exists())
        self.assertEqual(self.client.post(reverse('crm:employee_erase', args=[self.founder.pk]), {'confirm_password': PASSWORD}).status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.founder.pk).exists())

    def test_repeated_wrong_passwords_lock_the_step(self):
        self.login(self.founder)
        for _ in range(5):
            self.erase(password='xato')
        self.erase()
        self.assertTrue(User.objects.filter(pk=self.dev.pk).exists())

    def test_first_step_lists_what_will_go(self):
        self.company_history()
        self.login(self.founder)
        page = self.client.get(reverse('crm:employee_detail', args=[self.dev.pk]))
        self.assertContains(page, 'data-secure-delete=')
        self.assertContains(page, 'Moliya yozuvlari')
        self.assertContains(page, 'Chat xabarlari')
        self.login(self.ceo)
        self.assertNotContains(self.client.get(reverse('crm:employee_detail', args=[self.dev.pk])), reverse('crm:employee_erase', args=[self.dev.pk]))

    def test_employee_disappears_from_the_whole_database(self):
        self.company_history()
        designer_before = list(LedgerEntry.objects.filter(employee=self.designer).values_list('pk', 'amount'))
        receipts_before = LedgerEntry.objects.filter(category='receipt').count()
        file_name, storage = self.archive.file.name, self.archive.file.storage
        pk, username = self.dev.pk, self.dev.username
        self.login(self.founder)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertRedirects(self.erase(), reverse('crm:employees'))
        self.assertFalse(User.objects.filter(pk=pk).exists())
        self.assertFalse(LedgerEntry.objects.filter(employee_id=pk).exists())
        self.assertFalse(FinanceOperation.objects.filter(employee_id=pk).exists())
        self.assertFalse(PerformanceReview.objects.filter(employee_id=pk).exists())
        self.assertFalse(WorkShift.objects.filter(employee_id=pk).exists())
        self.assertFalse(ProjectArchive.objects.filter(uploader_id=pk).exists())
        self.assertFalse(storage.exists(file_name))
        self.assertFalse(Message.objects.filter(pk=self.message.pk).exists())
        self.assertFalse(Notification.objects.filter(dedupe_key=f'chat:{self.message.pk}').exists())
        self.assertFalse(TaskComment.objects.filter(author_id=pk).exists())
        self.assertFalse(TeamMember.objects.filter(pk=self.card.pk).exists())
        self.assertFalse(AuditEvent.objects.filter(actor_id=pk).exists())
        self.assertFalse(AuditEvent.objects.filter(target_type='accounts.user', target_id=str(pk)).exists())
        # The work itself and other people's money stay.
        self.task.refresh_from_db()
        self.assertIsNone(self.task.assignee_id)
        self.assertEqual(list(LedgerEntry.objects.filter(employee=self.designer).values_list('pk', 'amount')), designer_before)
        self.assertEqual(LedgerEntry.objects.filter(category='receipt').count(), receipts_before)
        # The trail says something was removed and by whom, not who it was.
        trail = AuditEvent.objects.get(action='user.erased')
        self.assertEqual(trail.actor, self.founder)
        self.assertNotIn(username, str(trail.changes) + trail.target_repr)

    def test_the_share_returns_to_the_company_and_later_receipts_still_work(self):
        self.company_history()
        self.login(self.founder)
        self.erase()
        agreement = AgreementSnapshot.objects.get(project=self.project)
        self.assertEqual([share['employee'] for share in agreement.shares], [self.designer.pk])
        self.assertEqual(agreement.company_percent, Decimal('80'))
        self.money('receipt', '1000000', project=self.project)
        self.assertEqual(sum(e.amount for e in LedgerEntry.objects.filter(employee=self.designer, category='earning')), Decimal('2200000'))

    def test_signatures_on_other_peoples_records_move_to_the_founder(self):
        lead_operation = finance.request_operation(self.founder, kind='expense', amount='1000', currency='UZS', description='Xarajat', idempotency_key=uuid.uuid4())
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('ssb.authorized_erase','on',true)")
            cursor.execute('UPDATE enterprise_financeoperation SET administrator_id=%s WHERE id=%s', [self.lead.pk, lead_operation.pk])
            cursor.execute("SELECT set_config('ssb.authorized_erase','off',true)")
        self.login(self.founder)
        self.erase(self.lead)
        self.assertFalse(User.objects.filter(username='lead').exists())
        lead_operation.refresh_from_db()
        self.assertEqual(lead_operation.administrator, self.founder)

    def test_protection_is_back_on_right_after_an_erase(self):
        self.company_history()
        self.login(self.founder)
        self.erase()
        entry = LedgerEntry.objects.filter(employee=self.designer).first()
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('DELETE FROM enterprise_ledgerentry WHERE id=%s', [entry.pk])
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('DELETE FROM audit_auditevent')
        self.assertTrue(LedgerEntry.objects.filter(pk=entry.pk).exists())

    def test_preview_matches_an_empty_account(self):
        self.assertEqual(erase_preview(self.outsider), ['Hisob, profil, rasm va ochiq sessiyalar'])

    def published_week(self):
        week = ps.prepare(self.founder, ps.last_week())
        for item in week.evaluations.all():
            manager = '100' if item.employee_id == self.dev.pk else '0'
            ps.review(self.founder, item.pk, 'approve', {**item.final_criteria, 'manager': manager},
                      'Dalillar tekshirildi.', 'Rahbar bahosi kiritildi.')
        return ps.publish(self.founder, week.pk)

    def test_evaluated_employee_with_a_cash_reward_can_be_erased(self):
        week = self.published_week()
        self.assertEqual(week.ranking[0]['employee_id'], self.dev.pk)
        other_places = {row['employee_id']: row['place'] for row in week.ranking[1:]}
        reward = ps.save_reward(self.founder, week.pk, 1, 'cash', 'Pul mukofoti', '1000', 'UZS', 'approved')
        self.assertEqual(reward.employee_id, self.dev.pk)
        pk, name, operation = self.dev.pk, self.dev.display_name, reward.operation_id
        self.login(self.founder)
        self.assertContains(self.client.get(reverse('crm:employee_detail', args=[pk])), 'Haftalik baholashlar')
        self.assertRedirects(self.erase(), reverse('crm:employees'))
        self.assertFalse(User.objects.filter(pk=pk).exists())
        self.assertFalse(WeeklyEvaluation.objects.filter(employee_id=pk).exists())
        self.assertFalse(WeeklyReward.objects.filter(pk=reward.pk).exists())
        self.assertFalse(FinanceOperation.objects.filter(pk=operation).exists())
        week.refresh_from_db()
        self.assertEqual({row['employee_id']: row['place'] for row in week.ranking}, other_places)
        self.assertEqual(self.client.get(reverse('enterprise:rating'), {'week': week.starts_on}).status_code, 200)
        published = AuditEvent.objects.get(action='performance.week_published')
        self.assertNotIn(name, str(published.changes))
        self.assertFalse(AuditEvent.objects.filter(target_type='enterprise.weeklyreward', target_id=str(reward.pk)).exists())

    def test_reviewer_signatures_on_weekly_history_move_to_the_founder(self):
        week = ps.prepare(self.ceo, ps.last_week())
        item = week.evaluations.get(employee=self.dev)
        ps.review(self.ceo, item.pk, 'approve', {**item.final_criteria, 'manager': '80'}, 'Dalillar tekshirildi.', 'Rahbar bahosi kiritildi.')
        draft = ps.save_reward(self.ceo, week.pk, 1, 'gift', 'Sovg‘a', '0', 'UZS', 'draft')
        self.login(self.founder)
        self.erase(self.ceo)
        self.assertFalse(User.objects.filter(pk=self.ceo.pk).exists())
        week.refresh_from_db(); item.refresh_from_db(); draft.refresh_from_db()
        self.assertEqual((week.created_by, item.reviewed_by, draft.updated_by), (self.founder,) * 3)

    def test_weekly_history_stays_protected_outside_an_erase(self):
        week = self.published_week()
        for statement in ('DELETE FROM enterprise_weeklyevaluation', "UPDATE enterprise_evaluationweek SET ranking='[]'"):
            with self.assertRaises(DatabaseError):
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(statement)
        self.login(self.founder)
        self.erase()
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('DELETE FROM enterprise_weeklyevaluation WHERE week_id=%s', [week.pk])

    def test_every_protected_link_to_a_user_is_handled_by_the_erase(self):
        """A new table with a PROTECT link to User must be added to the erase, or the Founder gets a 500."""
        source = inspect.getsource(erasure)
        for model in apps.get_models():
            for field in model._meta.get_fields():
                if isinstance(field, ForeignKey) and field.related_model is User and field.remote_field.on_delete is PROTECT:
                    self.assertIn(model.__name__, source, f'{model.__name__}.{field.name} is not handled in erasure.py')

    def test_milestone_needs_the_password(self):
        milestone = Milestone.objects.create(project=self.project, title='Bosqich')
        url = reverse('crm:milestone_toggle', args=[self.project.pk, milestone.pk])
        self.login(self.founder)
        self.client.post(url, {'delete': '1', 'confirm_password': 'xato'})
        self.assertTrue(Milestone.objects.filter(pk=milestone.pk).exists())
        self.client.post(url, {'delete': '1', 'confirm_password': PASSWORD})
        self.assertFalse(Milestone.objects.filter(pk=milestone.pk).exists())
