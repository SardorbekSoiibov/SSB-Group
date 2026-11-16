import json
from datetime import date, timedelta

from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import CompanyTestCase
from apps.enterprise import operations, schedule_ai
from apps.enterprise.models import WorkShift

TODAY = date(2026, 11, 4)  # Wednesday
WEEK = date(2026, 11, 2)


class ScheduleAiParsingTests(CompanyTestCase):
    def setUp(self):
        self.dev.first_name, self.dev.last_name = 'Sardor', 'Karimov'
        self.dev.save()
        self.designer.first_name, self.designer.last_name = 'Sardorbek', 'Aliyev'
        self.designer.save()

    def ask(self, text, week=WEEK):
        return schedule_ai.propose(self.founder, text, week, TODAY)

    def days(self, result):
        return [shift['date'] for shift in result['shifts']]

    def test_weekday_range_with_hours_and_place(self):
        result = self.ask('Sardor dushanbadan jumagacha 9 dan 18 gacha ofisda')
        self.assertEqual(self.days(result), [f'2026-11-0{day}' for day in range(2, 7)])
        self.assertEqual({(s['employee'], s['start'], s['end'], s['location']) for s in result['shifts']}, {(self.dev.pk, '09:00', '18:00', 'Ofis')})

    def test_a_longer_name_is_not_taken_for_a_shorter_one(self):
        result = self.ask('Sardorbekga ertaga')
        self.assertEqual({s['employee'] for s in result['shifts']}, {self.designer.pk})

    def test_suffixes_apostrophes_and_clock_format(self):
        result = self.ask('Karimovga SESHANBA kuni 10:30-15:00 uydan')
        self.assertEqual(self.days(result), ['2026-11-03'])
        self.assertEqual((result['shifts'][0]['start'], result['shifts'][0]['end'], result['shifts'][0]['location']), ('10:30', '15:00', 'Masofaviy'))

    def test_list_of_days_next_week_and_duty(self):
        result = self.ask('Sardor keyingi hafta dushanba va chorshanba navbatchilik')
        self.assertEqual(self.days(result), ['2026-11-09', '2026-11-11'])
        self.assertEqual(result['shifts'][0]['location'], 'Navbatchilik')

    def test_calendar_dates(self):
        self.assertEqual(self.days(self.ask('Sardor 12-noyabr 8-17')), ['2026-11-12'])
        self.assertEqual(self.ask('Sardor 12-noyabr 8-17')['shifts'][0]['start'], '08:00')
        self.assertEqual(self.days(self.ask('Sardor 10.11 dan 12.11 gacha')), ['2026-11-10', '2026-11-11', '2026-11-12'])

    def test_relative_days_and_working_week(self):
        self.assertEqual(self.days(self.ask('Sardor bugun')), ['2026-11-04'])
        self.assertEqual(self.days(self.ask('Sardor ertaga')), ['2026-11-05'])
        self.assertEqual(len(self.ask('Sardor ish kunlari')['shifts']), 5)

    def test_everyone_excludes_the_person_writing(self):
        employees = {s['employee'] for s in self.ask('hammaga ertaga')['shifts']}
        self.assertIn(self.dev.pk, employees)
        self.assertNotIn(self.founder.pk, employees)

    def test_missing_parts_are_asked_for_and_continue_the_message(self):
        self.assertTrue(self.ask('ertaga 9 dan 18 gacha')['need'])
        self.assertTrue(self.ask('Sardor')['need'])
        self.assertEqual(self.days(self.ask('Sardor ertaga')), ['2026-11-05'])

    def test_bad_input_gets_an_explanation_not_a_crash(self):
        for text in ('Sardor 31-noyabr', 'Sardor ertaga 25 dan 26 gacha', 'Sardor ertaga 9 dan 9 gacha', '', 'salom'):
            result = self.ask(text)
            self.assertEqual(result['shifts'], [], text)
            self.assertTrue(result['reply'], text)

    def test_two_people_with_one_name_ask_for_the_surname(self):
        self.designer.first_name = 'Sardor'
        self.designer.save()
        result = self.ask('Sardor ertaga')
        self.assertTrue(result['need'])
        self.assertIn('Familiyasini', result['reply'])
        self.assertEqual({s['employee'] for s in self.ask('Sardor Aliyev ertaga')['shifts']}, {self.designer.pk})

    def test_night_shift_ends_next_day(self):
        result = self.ask('Sardor ertaga 22 dan 6 gacha')
        saved, _ = schedule_ai.apply(self.founder, result['shifts'])
        self.assertEqual((saved[0].ends_at - saved[0].starts_at), timedelta(hours=8))

    def test_busy_time_is_marked_and_skipped_on_saving(self):
        day = timezone.localdate() + timedelta(days=1)
        result = schedule_ai.propose(self.founder, 'Sardor ertaga')
        saved, _ = schedule_ai.apply(self.founder, result['shifts'])
        self.assertEqual(len(saved), 1)
        again = schedule_ai.propose(self.founder, 'Sardor ertaga')
        self.assertTrue(again['shifts'][0]['busy'])
        saved, skipped = schedule_ai.apply(self.founder, again['shifts'])
        self.assertEqual((len(saved), skipped), (0, 1))
        self.assertEqual(WorkShift.objects.filter(employee=self.dev, starts_at__date=day).count(), 1)


class ScheduleAiAccessTests(CompanyTestCase):
    def setUp(self):
        self.dev.first_name = 'Sardor'
        self.dev.save()
        self.ask_url, self.apply_url = reverse('enterprise:schedule_ai'), reverse('enterprise:schedule_ai_apply')

    def post(self, url, data):
        return self.client.post(url, json.dumps(data), content_type='application/json')

    def test_manager_asks_then_applies(self):
        self.login(self.founder)
        answer = self.post(self.ask_url, {'text': 'Sardor ertaga 9 dan 18 gacha'}).json()
        self.assertEqual(len(answer['shifts']), 1)
        self.assertFalse(WorkShift.objects.filter(employee=self.dev).exists())
        saved = self.post(self.apply_url, {'shifts': answer['shifts']})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(WorkShift.objects.filter(employee=self.dev).count(), 1)
        self.assertIn('dan=', saved.json()['url'])

    def test_employees_cannot_use_it(self):
        self.login(self.dev)
        self.assertEqual(self.post(self.ask_url, {'text': 'Sardor ertaga'}).status_code, 403)
        start = timezone.localdate().isoformat()
        shift = {'employee': self.dev.pk, 'date': start, 'start': '09:00', 'end': '18:00', 'location': 'Ofis'}
        self.assertEqual(self.post(self.apply_url, {'shifts': [shift]}).status_code, 403)
        self.assertFalse(WorkShift.objects.exists())

    def test_tampered_or_empty_plans_are_refused(self):
        self.login(self.founder)
        self.assertEqual(self.post(self.apply_url, {'shifts': []}).status_code, 400)
        self.assertEqual(self.post(self.apply_url, {'shifts': 'x'}).status_code, 400)
        self.assertEqual(self.client.post(self.apply_url, 'not json', content_type='application/json').status_code, 400)
        with self.assertRaises(PermissionDenied):
            schedule_ai.apply(self.founder, [{'employee': 999999, 'date': '2026-11-05', 'start': '09:00', 'end': '18:00', 'location': 'Ofis'}])


class ScheduleForEveryoneTests(CompanyTestCase):
    def test_every_employee_finds_the_page_and_sees_only_their_shifts(self):
        start = timezone.now() + timedelta(hours=1)
        operations.save_shift(self.founder, self.dev, start, start + timedelta(hours=8), 'Ofis')
        operations.save_shift(self.founder, self.designer, start, start + timedelta(hours=8), 'Ofis')
        self.login(self.dev)
        response = self.client.get(reverse('enterprise:schedule'))
        self.assertContains(response, 'Ish jadvalim')
        self.assertEqual([shift.employee for shift in response.context['shifts']], [self.dev])
        self.assertNotContains(response, 'data-shift-add')
        self.assertNotContains(response, 'data-schedule-ai')

    def test_employee_cannot_add_a_shift(self):
        self.login(self.dev)
        day = timezone.localdate()
        response = self.client.post(reverse('enterprise:schedule'), {'employee': self.dev.pk, 'starts_at': f'{day}T09:00', 'ends_at': f'{day}T18:00', 'location': 'Ofis'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(WorkShift.objects.exists())

    def test_manager_sees_everyone_and_the_controls(self):
        start = timezone.now() + timedelta(hours=1)
        operations.save_shift(self.founder, self.dev, start, start + timedelta(hours=8), 'Ofis')
        self.login(self.founder)
        response = self.client.get(reverse('enterprise:schedule'))
        self.assertEqual(len(response.context['shifts']), 1)
        self.assertContains(response, 'data-shift-add')
        self.assertContains(response, 'data-schedule-ai')
