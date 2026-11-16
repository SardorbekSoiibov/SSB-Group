from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.db import transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import PASSWORD, CompanyTestCase
from apps.crm.models import Project, Task
from apps.audit.models import AuditEvent
from apps.notifications.models import ClearedReminder, Notification
from apps.notifications.reminders import send_deadline_reminders
from apps.notifications.services import notify, Kind


class NotificationDeliveryTests(CompanyTestCase):
    def setUp(self):
        cache.clear()
        self.login(self.dev)
        self.endpoint = reverse('enterprise:api_notifications')

    def notice(self, recipient=None, **kwargs):
        return Notification.objects.create(recipient=recipient or self.dev, kind=Kind.ANNOUNCEMENT,
                                           title='Delivery test', **kwargs)

    def test_private_feed_and_read_access(self):
        own = self.notice()
        other = self.notice(self.designer)
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['id'] for item in response.json()['items']], [own.pk])
        self.assertIn('no-store', response['Cache-Control'])
        read = lambda pk: reverse('enterprise:api_notification_read', args=[pk])
        self.assertFalse(self.client.post(read(other.pk)).json()['read'])
        self.assertTrue(self.client.post(read(own.pk)).json()['read'])
        self.assertFalse(self.client.post(read(own.pk)).json()['read'])
        other.refresh_from_db(); self.assertIsNone(other.read_at)
        self.assertEqual(self.client.get(self.endpoint).json()['unread'], 0)
        self.client.logout()
        self.assertIn(self.client.get(self.endpoint).status_code, [401, 403])

    def test_new_messages_survive_bursts_and_read_between_pages(self):
        self.notice()
        start = self.client.get(self.endpoint).json()['cursor']
        rows = Notification.objects.bulk_create([
            Notification(recipient=self.dev, kind=Kind.ANNOUNCEMENT, title=f'Burst {i}') for i in range(235)])
        # Read rows still advance the cursor, without re-alerting their recipient.
        Notification.objects.filter(pk=rows[45].pk).update(read_at=timezone.now())
        self.notice(self.designer)
        delivered = []
        cursor = start
        for _ in range(3):
            data = self.client.get(self.endpoint, {'after': cursor}).json()
            self.assertGreater(data['cursor'], cursor)
            cursor = data['cursor']
            delivered.extend(item['id'] for item in data['items'])
        self.assertEqual(delivered, [row.pk for row in rows if row.pk != rows[45].pk])
        self.assertFalse(data['has_more'])
        self.assertEqual(self.client.get(self.endpoint, {'after': cursor}).json()['items'], [])

    def test_cursor_validation(self):
        for value in ['', '-1', 'oops', '9' * 40, '1.5']:
            self.assertEqual(self.client.get(self.endpoint, {'after': value}).status_code, 400)

    def test_delivery_is_transactional_and_duplicate_safe(self):
        recipients = [self.dev, self.dev, self.designer, None]
        self.assertEqual(len(notify(recipients, Kind.COMMENT, 'New comment', dedupe_key='comment:42')), 2)
        self.assertEqual(notify(recipients, Kind.COMMENT, 'New comment', dedupe_key='comment:42'), [])
        try:
            with transaction.atomic():
                notify([self.dev], Kind.COMMENT, 'Rolled back')
                raise ValueError('Rollback business event')
        except ValueError:
            pass
        self.assertFalse(Notification.objects.filter(title='Rolled back').exists())

    def test_unsafe_links_cannot_redirect_outside_workspace(self):
        for url in ['https://example.com/steal', '//example.com', 'javascript:alert(1)', '/management/\\evil.test']:
            item = self.notice(url=url)
            response = self.client.post(reverse('crm:notification_open', args=[item.pk]))
            self.assertEqual(response.url, reverse('crm:notifications'))

    def test_csrf_is_required_for_reading(self):
        item = self.notice()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.dev)
        self.assertEqual(client.post(reverse('enterprise:api_notification_read', args=[item.pk])).status_code, 403)
        item.refresh_from_db(); self.assertIsNone(item.read_at)

    def test_reminders_run_on_poll_and_ignore_cancelled_projects(self):
        today = timezone.localdate()
        Task.objects.create(project=self.project, title='Due tomorrow', assignee=self.dev,
                            status=Task.Status.ASSIGNED, deadline=today + timedelta(days=1))
        cancelled = Project.objects.create(name='Cancelled', manager=self.lead, status=Project.Status.CANCELLED,
                                          deadline=today - timedelta(days=1))
        Task.objects.create(project=cancelled, title='Do not remind', assignee=self.dev,
                            status=Task.Status.ASSIGNED, deadline=today - timedelta(days=1))
        self.client.get(self.endpoint)
        self.client.get(self.endpoint)
        self.assertEqual(Notification.objects.filter(recipient=self.dev, kind=Kind.DEADLINE_SOON).count(), 1)
        self.assertFalse(Notification.objects.filter(kind=Kind.OVERDUE).exists())
        with patch('apps.notifications.reminders.timezone.localdate', return_value=today + timedelta(days=1)):
            send_deadline_reminders()
        self.assertEqual(Notification.objects.filter(recipient=self.dev, kind=Kind.DEADLINE_SOON).count(), 2)

    def test_unread_filter_and_total_render_correctly(self):
        self.notice()
        self.notice(read_at=timezone.now())
        response = self.client.get(reverse('crm:notifications'))
        self.assertContains(response, '2 ta xabar')
        response = self.client.get(reverse('crm:notifications'), {'oqilmagan': 1})
        self.assertEqual(response.context['page'].paginator.count, 1)
        self.client.post(reverse('crm:notification_read_all'))
        self.assertEqual(self.client.get(self.endpoint).json()['unread'], 0)


class ClearNotificationsTests(CompanyTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse('crm:notification_clear')
        self.client.force_login(self.dev)
        notify([self.dev], Kind.ANNOUNCEMENT, 'Birinchi')
        notify([self.dev], Kind.ANNOUNCEMENT, 'Ikkinchi', dedupe_key='announcement:1')
        notify([self.designer], Kind.ANNOUNCEMENT, 'Boshqa odamniki')

    def clear(self, password=None):
        return self.client.post(self.url, {'confirm_password': password or PASSWORD}, follow=True)

    def test_wrong_or_missing_password_clears_nothing(self):
        self.assertContains(self.clear('wrong-password-value'), 'Parol noto')
        self.client.post(self.url)
        self.assertEqual(self.dev.notifications.count(), 2)

    def test_clears_only_own_notifications_and_is_audited(self):
        response = self.clear()
        self.assertContains(response, '2 ta bildirishnoma tozalandi')
        self.assertNotContains(response, 'data-secure-delete')
        self.assertEqual(self.dev.notifications.count(), 0)
        self.assertEqual(self.designer.notifications.count(), 1)
        self.assertTrue(AuditEvent.objects.filter(actor=self.dev, action='notifications.cleared').exists())

    def test_needs_post_and_a_signed_in_person(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        Client().post(self.url, {'confirm_password': PASSWORD})
        self.assertEqual(self.dev.notifications.count(), 2)

    def test_cleared_reminder_does_not_return_today_but_returns_tomorrow(self):
        project = Project.objects.create(code='CLR-1', name='Tozalash', manager=self.founder, created_by=self.founder)
        today = timezone.localdate()
        Task.objects.create(project=project, title='Kechikkan', assignee=self.dev, deadline=today - timedelta(days=1), created_by=self.founder)
        send_deadline_reminders()
        self.assertTrue(self.dev.notifications.filter(kind=Kind.OVERDUE).exists())
        self.clear()
        send_deadline_reminders()
        self.assertFalse(self.dev.notifications.exists())
        with patch('django.utils.timezone.localdate', return_value=today + timedelta(days=1)):
            send_deadline_reminders()
        self.assertTrue(self.dev.notifications.filter(kind=Kind.OVERDUE).exists())

    def test_new_notifications_still_arrive_after_clearing(self):
        self.clear()
        notify([self.dev], Kind.ANNOUNCEMENT, 'Yangi')
        self.assertEqual(self.dev.notifications.count(), 1)

    def test_erasing_an_employee_removes_cleared_reminders_too(self):
        ClearedReminder.objects.create(recipient=self.dev, dedupe_key='overdue:1:2026-11-04', cleared_on=timezone.localdate())
        self.dev.delete()
        self.assertFalse(ClearedReminder.objects.exists())

