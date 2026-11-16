from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.core.testing import CompanyTestCase
from apps.enterprise.absence_models import AbsenceRequest
from apps.enterprise.models import WorkShift
from apps.notifications.models import Notification


class AbsenceRequestTests(CompanyTestCase):
    def send(self, user, **extra):
        self.login(user)
        day = timezone.localdate() + timedelta(days=1)
        data = {'date_from': day.isoformat(), 'date_to': day.isoformat(), 'reason': 'Shifokor qabuliga boraman'}
        data.update(extra)
        return self.client.post(reverse('enterprise:absence_create'), data)

    def test_employee_request_reaches_founder(self):
        self.send(self.dev)
        item = AbsenceRequest.objects.get()
        self.assertEqual(item.status, AbsenceRequest.Status.PENDING)
        self.assertTrue(Notification.objects.filter(recipient=self.founder, kind='approval').exists())
        self.login(self.founder)
        page = self.client.get(reverse('enterprise:schedule'))
        self.assertContains(page, 'Shifokor qabuliga boraman')

    def test_reason_is_required(self):
        self.send(self.dev, reason='')
        self.assertFalse(AbsenceRequest.objects.exists())

    def test_founder_approval_cancels_shifts_and_answers_employee(self):
        day = timezone.localdate() + timedelta(days=1)
        start = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time())) + timedelta(hours=9)
        shift = WorkShift.objects.create(employee=self.dev, starts_at=start, ends_at=start + timedelta(hours=8), location='Ofis', administrator=self.founder)
        self.send(self.dev)
        item = AbsenceRequest.objects.get()
        self.login(self.founder)
        self.client.post(reverse('enterprise:absence_decide', args=[item.pk]), {'action': 'approve', 'note': 'Sog‘ bo‘ling'})
        item.refresh_from_db(); shift.refresh_from_db()
        self.assertEqual(item.status, AbsenceRequest.Status.APPROVED)
        self.assertTrue(shift.cancelled)
        self.assertTrue(Notification.objects.filter(recipient=self.dev, title__contains='tasdiqlandi').exists())

    def test_only_founder_decides(self):
        self.send(self.dev)
        item = AbsenceRequest.objects.get()
        self.login(self.ceo)
        self.assertEqual(self.client.post(reverse('enterprise:absence_decide', args=[item.pk]), {'action': 'approve'}).status_code, 403)
        item.refresh_from_db()
        self.assertEqual(item.status, AbsenceRequest.Status.PENDING)

    def test_rejection_is_reported(self):
        self.send(self.dev)
        item = AbsenceRequest.objects.get()
        self.login(self.founder)
        self.client.post(reverse('enterprise:absence_decide', args=[item.pk]), {'action': 'reject'})
        item.refresh_from_db()
        self.assertEqual(item.status, AbsenceRequest.Status.REJECTED)
        self.assertTrue(Notification.objects.filter(recipient=self.dev, title__contains='rad etildi').exists())
