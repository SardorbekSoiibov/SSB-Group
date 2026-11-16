import json
from datetime import datetime, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import DatabaseError, transaction
from django.test import override_settings
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.core.testing import CompanyTestCase
from apps.crm.models import Task, TaskReview
from apps.enterprise import performance_system as ps, finance
from apps.enterprise.models import EvaluationWeek, WeeklyEvaluation, WeeklyReward, FinanceOperation, LedgerEntry


@override_settings(PERFORMANCE_AI_ENDPOINT='', PERFORMANCE_AI_KEY='')
class UnifiedPerformanceTests(CompanyTestCase):
    def setUp(self):
        self.start = ps.last_week()
        self.accepted = Task.objects.create(project=self.project, title='Haqiqiy yakunlangan ish', assignee=self.dev,
            status=Task.Status.APPROVED, deadline=self.start+timedelta(days=4),
            approved_at=datetime.combine(self.start+timedelta(days=3), datetime.min.time(), ps.TZ), created_by=self.founder)

    def prepare(self):
        return ps.prepare(self.founder, self.start)

    def approve(self, item, manager=80):
        values = {**item.final_criteria, 'manager': str(manager)}
        return ps.review(self.founder, item.pk, 'approve', values, 'Haqiqiy dalillar tekshirildi.', 'Rahbar bahosi dalillar bilan kiritildi.')

    def publish(self):
        week = self.prepare()
        for item in week.evaluations.all():
            self.approve(item)
        return ps.publish(self.founder, week.pk)

    def test_real_evidence_and_transparent_fallback(self):
        week = self.prepare()
        item = week.evaluations.get(employee=self.dev)
        self.assertEqual(item.source, 'rules')
        self.assertEqual(item.evidence['completed'], 1)
        self.assertEqual(item.evidence['on_time'], 1)
        self.assertIn(self.accepted.title, item.analysis['achievements'])
        self.assertEqual(item.original_score, Decimal('85.00'))
        self.assertEqual(item.final_score, item.original_score)
        self.assertIn('AI tahlili mavjud emas', item.analysis['detail'])
        self.assertFalse(week.published_at)

    def test_week_boundaries_are_monday_to_sunday_tashkent(self):
        self.assertEqual(self.start.weekday(), 0)
        Task.objects.create(project=self.project, title='Keyingi hafta', assignee=self.dev, status='approved',
            approved_at=datetime.combine(self.start+timedelta(days=7), datetime.min.time(), ps.TZ), created_by=self.founder)
        evidence, _ = ps.collect(self.dev, self.start)
        self.assertEqual(evidence['completed'], 1)
        self.assertEqual(evidence['timezone'], 'Asia/Tashkent')
        with self.assertRaises(ValidationError):
            ps.prepare(self.founder, self.start+timedelta(days=1))
        with self.assertRaises(ValidationError):
            ps.prepare(self.founder, ps.last_week()+timedelta(days=7))

    def test_zero_work_is_not_invented(self):
        week = self.prepare()
        empty = week.evaluations.get(employee=self.designer)
        self.assertEqual(empty.original_score, 0)
        self.assertEqual(empty.analysis['achievements'], [])

    def test_duplicate_preparation_freezes_cohort_evidence_and_weights(self):
        week = self.prepare()
        first = list(week.evaluations.values())
        same = ps.prepare(self.founder, self.start, {**ps.DEFAULT_WEIGHTS, 'completion': 20, 'manager': 20})
        self.assertEqual(week.pk, same.pk)
        self.assertEqual(list(same.evaluations.values()), first)
        self.assertEqual(EvaluationWeek.objects.count(), 1)

    def test_custom_weights_and_validation(self):
        weights = {'completion': 100, 'quality': 0, 'contribution': 0, 'deadline': 0, 'manager': 0}
        week = ps.prepare(self.founder, self.start, weights)
        self.assertEqual(week.evaluations.get(employee=self.dev).original_score, 100)
        with self.assertRaises(ValidationError):
            ps.validate_weights({**ps.DEFAULT_WEIGHTS, 'manager': 16})

    def test_adjustments_require_explanation_and_preserve_original(self):
        item = self.prepare().evaluations.get(employee=self.dev)
        original = item.original_score
        with self.assertRaises(ValidationError):
            ps.review(self.founder, item.pk, 'approve', {**item.final_criteria, 'manager': 90}, 'Izoh yetarli uzunlikda', '')
        approved = self.approve(item, 90)
        self.assertEqual(approved.original_score, original)
        self.assertEqual(approved.final_score, Decimal('98.50'))
        self.assertTrue(AuditEvent.objects.filter(action='performance.weekly_approve', target_id=str(item.pk)).exists())
        with self.assertRaises(ValidationError):
            self.approve(approved)

    def test_return_correction_and_reapproval(self):
        item = self.prepare().evaluations.get(employee=self.dev)
        returned = ps.review(self.founder, item.pk, 'return', item.final_criteria, 'Tekshirish uchun qaytarildi.', 'Vazifa dalillarini qayta ko‘ring.')
        self.assertEqual(returned.status, 'returned')
        self.assertFalse(returned.approved_at)
        saved = ps.review(self.founder, item.pk, 'save', item.final_criteria, 'Dalillar qayta tekshirildi.', '')
        self.assertEqual(saved.status, 'draft')
        self.assertEqual(self.approve(saved).status, 'approved')

    def test_publication_requires_all_approvals_and_is_idempotent(self):
        week = self.prepare()
        with self.assertRaises(ValidationError):
            ps.publish(self.founder, week.pk)
        week = self.publish()
        self.assertEqual(week.ranking[0]['employee_id'], self.dev.pk)
        self.assertEqual([r['place'] for r in week.ranking], list(range(1, week.evaluations.count()+1)))
        self.assertEqual(ps.publish(self.founder, week.pk).ranking, week.ranking)
        self.accepted.title = 'Keyinchalik o‘zgargan nom'
        self.accepted.save()
        week.refresh_from_db()
        self.assertIn('Haqiqiy yakunlangan ish', week.ranking[0]['achievements'])

    def test_published_history_has_database_guards(self):
        week = self.publish()
        with self.assertRaises(DatabaseError), transaction.atomic():
            EvaluationWeek.objects.filter(pk=week.pk).update(ranking=[])
        item = week.evaluations.get(employee=self.dev)
        with self.assertRaises(DatabaseError), transaction.atomic():
            WeeklyEvaluation.objects.filter(pk=item.pk).update(final_score=0)

    def test_gift_reward_history_and_delivery(self):
        week = self.publish()
        reward = ps.save_reward(self.founder, week.pk, 1, 'gift', 'Kitob sovg‘asi', 100000, 'UZS', 'approved')
        self.assertEqual(reward.employee_id, self.dev.pk)
        reward = ps.save_reward(self.founder, week.pk, 1, 'gift', reward.description, reward.value, 'UZS', 'issued')
        self.assertEqual(reward.status, 'issued')
        with self.assertRaises(ValidationError):
            ps.save_reward(self.founder, week.pk, 1, 'gift', 'Boshqa sovg‘a', 100, 'UZS', 'approved')

    def test_cash_uses_existing_finance_approval_and_prevents_duplicate_bonus(self):
        week = self.publish()
        reward = ps.save_reward(self.founder, week.pk, 1, 'cash', 'Haftalik g‘olib bonusi', 100000, 'UZS', 'approved')
        # Asoschi bergan pul mukofoti darhol kuchga kiradi (moliyaviy qarorni faqat Asoschi qabul qiladi).
        self.assertEqual(reward.operation.status, 'approved')
        with self.assertRaises(ValidationError):
            ps.save_reward(self.founder, week.pk, 1, 'cash', 'Haftalik g‘olib bonusi', 100000, 'UZS', 'approved')
        self.assertEqual(FinanceOperation.objects.filter(kind='bonus').count(), 1)
        self.assertEqual(LedgerEntry.objects.filter(operation=reward.operation, category='bonus').count(), 1)

    def test_unpublished_rewards_cannot_be_approved(self):
        week = self.prepare()
        with self.assertRaises(ValidationError):
            ps.save_reward(self.founder, week.pk, 1, 'cash', 'Bonus sovg‘asi', 100, 'UZS', 'approved')
        draft = ps.save_reward(self.founder, week.pk, 2, 'recognition', 'Tashakkurnoma', 0, 'UZS', 'draft')
        self.assertEqual(draft.status, 'draft')

    def test_employee_cannot_manage_or_read_another_evaluation(self):
        week = self.prepare()
        item = week.evaluations.get(employee=self.dev)
        with self.assertRaises(PermissionDenied):
            ps.prepare(self.dev, self.start)
        with self.assertRaises(PermissionDenied):
            ps.review(self.dev, item.pk, 'approve', item.final_criteria, 'Izoh matni yetarli uzun', '')
        self.login(self.dev)
        self.assertEqual(self.client.get(reverse('enterprise:evaluation_detail', args=[item.pk])).status_code, 404)
        self.publish()
        self.assertEqual(self.client.get(reverse('enterprise:evaluation_detail', args=[item.pk])).status_code, 200)
        other = week.evaluations.get(employee=self.designer)
        self.assertEqual(self.client.get(reverse('enterprise:evaluation_detail', args=[other.pk])).status_code, 404)

    def test_director_cannot_approve_self(self):
        item = self.prepare().evaluations.get(employee=self.ceo)
        with self.assertRaises(PermissionDenied):
            ps.review(self.ceo, item.pk, 'approve', item.final_criteria, 'Izoh matni yetarli uzun', '')

    def test_pages_render_management_and_employee_views(self):
        week = self.publish()
        for user in [self.founder, self.dev]:
            self.login(user)
            for route in ['enterprise:performance', 'enterprise:rating', 'enterprise:overview', 'enterprise:performance_history']:
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200, route)
        self.assertContains(self.client.get(reverse('enterprise:rating')), 'Haftaning g‘olibi')

    def test_scheduler_is_idempotent_and_waits_for_approval(self):
        for _ in range(2):
            call_command('process_weekly_performance', actor=self.founder.username, stdout=StringIO())
        week = EvaluationWeek.objects.get(starts_on=self.start)
        count = week.evaluations.count()
        self.assertFalse(week.published_at)
        for item in week.evaluations.all():
            self.approve(item)
        call_command('process_weekly_performance', actor=self.founder.username, stdout=StringIO())
        week.refresh_from_db()
        self.assertTrue(week.published_at)
        self.assertEqual(week.evaluations.count(), count)

    @override_settings(PERFORMANCE_AI_ENDPOINT='https://ai.example/review', PERFORMANCE_AI_KEY='test-secret')
    def test_ai_structured_scores_and_analysis(self):
        evidence, criteria = ps.collect(self.dev, self.start)
        response = {'criteria': {**criteria, 'quality': '90'}, 'strengths': ['Qabul qilingan ish bor.'],
                    'weaknesses': ['Dalillarni tekshirish kerak.'], 'recommendations': ['Muddatlarni kuzating.'], 'detail': 'Haqiqiy vazifa asosidagi tahlil.'}
        with patch.object(ps, 'urlopen') as remote:
            remote.return_value.__enter__.return_value.read.return_value = json.dumps(response).encode()
            result, analysis, source = ps.analyze(evidence, criteria)
        self.assertEqual(source, 'ai')
        self.assertEqual(result['quality'], '90')
        self.assertEqual(analysis['achievements'], [self.accepted.title])

    @override_settings(PERFORMANCE_AI_ENDPOINT='https://ai.example/review', PERFORMANCE_AI_KEY='test-secret')
    def test_ai_failure_and_invalid_scores_fall_back(self):
        evidence, criteria = ps.collect(self.dev, self.start)
        for error in [TimeoutError(), ValueError()]:
            with patch.object(ps, 'urlopen', side_effect=error):
                result, analysis, source = ps.analyze(evidence, criteria)
            self.assertEqual(source, 'rules')
            self.assertEqual(result, criteria)
        with patch.object(ps, 'urlopen') as remote:
            remote.return_value.__enter__.return_value.read.return_value = b'{"criteria":{"manager":999}}'
            self.assertEqual(ps.analyze(evidence, criteria)[2], 'rules')
