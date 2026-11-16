"""Founder-only section reset: two steps, whole section gone, ids restart, protection back on afterwards."""
from datetime import timedelta

from django.db import DatabaseError, connection, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.chat.models import Message
from apps.core.testing import PASSWORD, CompanyTestCase
from apps.crm.models import Project
from apps.enterprise import data_reset, operations
from apps.enterprise.models import FinanceOperation, LedgerEntry, WorkShift
from apps.enterprise.tests import test_erasure as base


@override_settings(REQUIRE_MALWARE_SCAN=False, MALWARE_SCANNER='')
class DataResetTests(CompanyTestCase):
    url = reverse('enterprise:data_reset')
    setUp, tearDown, approve, money, company_history = (base.ErasureTests.setUp, base.ErasureTests.tearDown, base.ErasureTests.approve,
                                                       base.ErasureTests.money, base.ErasureTests.company_history)

    def reset(self, key, password=PASSWORD):
        return self.client.post(self.url, {'bolim': key, 'confirm_password': password})

    def shift(self, day=2):
        start = timezone.now() + timedelta(days=day)
        return operations.save_shift(self.founder, self.dev, start, start + timedelta(hours=8), 'Ofis')

    def test_only_the_founder_sees_and_uses_it(self):
        self.shift()
        for actor in (self.ceo, self.cofounder, self.lead, self.dev):
            self.login(actor)
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(self.reset('jadval').status_code, 403)
            self.assertNotContains(self.client.get(reverse('enterprise:overview')), self.url)
        self.assertTrue(WorkShift.objects.exists())
        self.login(self.founder)
        page = self.client.get(self.url)
        self.assertContains(page, 'data-secure-delete=')
        self.assertContains(page, 'Ish jadvali')

    def test_wrong_password_and_unknown_section_delete_nothing(self):
        self.shift()
        self.login(self.founder)
        self.reset('jadval', password='xato')
        self.reset('yoq-bolim')
        self.client.post(self.url, {'bolim': 'jadval'})
        self.assertTrue(WorkShift.objects.exists())

    def test_section_is_emptied_and_starts_from_one(self):
        self.shift(2); self.shift(3).delete(); self.shift(4)
        self.login(self.founder)
        self.assertRedirects(self.reset('jadval'), self.url)
        self.assertFalse(WorkShift.objects.exists())
        self.assertEqual(self.shift().pk, 1)
        trail = AuditEvent.objects.get(action='data.reset')
        self.assertEqual((trail.actor, trail.changes['section']), (self.founder, 'jadval'))

    def test_other_sections_stay(self):
        self.company_history()
        messages, ledger = Message.objects.count(), LedgerEntry.objects.count()
        self.login(self.founder)
        self.reset('jadval')
        self.assertEqual((Message.objects.count(), LedgerEntry.objects.count()), (messages, ledger))
        self.assertTrue(User.objects.filter(pk=self.dev.pk).exists())

    def test_finance_reset_and_protection_is_back_on(self):
        self.company_history()
        self.login(self.founder)
        with self.captureOnCommitCallbacks(execute=True):
            self.reset('moliya')
        self.assertFalse(LedgerEntry.objects.exists())
        self.assertFalse(FinanceOperation.objects.exists())
        operation = self.money('expense', '1000')
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('DELETE FROM enterprise_financeoperation WHERE id=%s', [operation.pk])

    def test_every_section_runs_on_real_history(self):
        self.company_history()
        self.login(self.founder)
        for key in data_reset.SECTIONS:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.reset(key).status_code, 302, key)
        self.assertFalse(Project.objects.exists())
        self.assertFalse(Message.objects.exists())
        self.assertEqual(list(User.objects.exclude(pk=self.founder.pk).filter(pk__in=[self.dev.pk, self.ceo.pk])), [])
        self.assertTrue(User.objects.filter(pk=self.founder.pk).exists())

    def test_no_section_reaches_protected_tables(self):
        for key in data_reset.SECTIONS:
            if key != 'xodimlar':
                data_reset.plan(key)
