from datetime import date, datetime, timedelta

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import CompanyTestCase
from apps.crm.models import Project, Task, TaskReview
from apps.enterprise import weekly_rating as wr
from apps.enterprise.models import WeeklyPlace, WeeklyRating
from apps.notifications.models import Notification

WEDNESDAY = date(2026, 11, 4)
SUNDAY = date(2026, 11, 8)


def at(day, hour=12):
    return timezone.make_aware(datetime(day.year, day.month, day.day, hour))


class CalendarTests(CompanyTestCase):
    def test_week_closes_on_the_next_sunday_and_a_sunday_opens_a_new_one(self):
        self.assertEqual(wr.current_week(WEDNESDAY), SUNDAY)
        self.assertEqual(wr.current_week(date(2026, 11, 7)), SUNDAY)
        self.assertEqual(wr.current_week(SUNDAY), date(2026, 11, 15))

    def test_label(self):
        self.assertEqual(wr.week_label(SUNDAY), '1–7 noyabr')
        self.assertEqual(wr.week_label(date(2026, 11, 1)), '25–31 oktabr')
        self.assertEqual(wr.week_label(date(2026, 12, 6)), '29 noyabr – 5 dekabr')


class FactsTests(CompanyTestCase):
    def setUp(self):
        self.project = Project.objects.create(code='WR-1', name='Hisobot loyihasi', manager=self.founder, created_by=self.founder)

    def task(self, title, approved=None, deadline=None, status=Task.Status.APPROVED, submitted=None, person=None):
        return Task.objects.create(project=self.project, title=title, assignee=person or self.dev, status=status, approved_at=approved,
                                   deadline=deadline, submitted_at=submitted, created_by=self.founder)

    def row(self, person=None):
        return next(row for row in wr.week_facts(SUNDAY) if row['person'] == (person or self.dev))

    def test_counts_only_this_weeks_accepted_work_with_real_numbers(self):
        self.task('Vaqtida', at(date(2026, 11, 3)), date(2026, 11, 5))
        self.task('Kechikkan', at(date(2026, 11, 6)), date(2026, 11, 2))
        self.task('Oldingi hafta', at(date(2026, 10, 30)))
        self.task('Keyingi hafta', at(SUNDAY, 1))
        fix = self.task('Tuzatilgan', at(date(2026, 11, 5)))
        TaskReview.objects.create(task=fix, reviewer=self.founder, decision=TaskReview.Decision.CHANGES)
        self.task('Tekshiruvda', status=Task.Status.SUBMITTED, submitted=at(date(2026, 11, 5)))
        self.task('Ochiq kechikkan', status=Task.Status.IN_PROGRESS, deadline=date(2026, 11, 3))
        row = self.row()
        self.assertEqual({task.title for task in row['tasks']}, {'Vaqtida', 'Kechikkan', 'Tuzatilgan'})
        self.assertEqual((row['done'], row['on_time'], row['late'], row['corrections'], row['waiting'], row['overdue']), (3, 2, 1, 1, 1, 1))
        self.assertEqual(row['projects'], ['Hisobot loyihasi'])
        self.assertEqual(row['score'], 30 + 10 - 2 - 3)

    def test_sunday_midnight_is_the_exact_border(self):
        self.task('Oxirgi soniya', timezone.make_aware(datetime(2026, 11, 7, 23, 59, 59)))
        self.task('Keyingi haftaning birinchisi', timezone.make_aware(datetime(2026, 11, 8, 0, 0, 0)))
        self.assertEqual([task.title for task in self.row()['tasks']], ['Oxirgi soniya'])

    def test_suggestion_orders_by_work_and_leaves_out_people_with_no_work(self):
        self.task('Bitta', at(date(2026, 11, 3)), person=self.designer)
        self.task('Birinchi', at(date(2026, 11, 3)))
        self.task('Ikkinchi', at(date(2026, 11, 4)))
        rows = wr.week_facts(SUNDAY)
        self.assertEqual((rows[0]['person'], rows[0]['suggested']), (self.dev, 1))
        self.assertEqual((rows[1]['person'], rows[1]['suggested']), (self.designer, 2))
        self.assertTrue(all(row['suggested'] == 0 for row in rows[2:]))

    def test_founder_is_not_rated(self):
        self.assertNotIn(self.founder, [row['person'] for row in wr.week_facts(SUNDAY)])


class SavingTests(CompanyTestCase):
    def save(self, places, prize='Bonus', actor=None, today=WEDNESDAY, week=SUNDAY):
        return wr.save_places(actor or self.founder, week, prize, places, today)

    def test_rules(self):
        for places, prize, message in (({}, 'Bonus', 'Kamida 1'), ({self.dev.pk: 2}, 'Bonus', 'ketma-ket'), ({self.dev.pk: 1, self.designer.pk: 1}, 'Bonus', 'ketma-ket'),
                                       ({self.dev.pk: 1, self.designer.pk: 3}, 'Bonus', 'ketma-ket'), ({self.dev.pk: 1}, '  ', 'sovg'), ({self.founder.pk: 1}, 'Bonus', 'Ro‘yxatda')):
            with self.assertRaisesMessage(ValidationError, message):
                self.save(places, prize)
        self.assertFalse(WeeklyPlace.objects.exists())

    def test_only_the_boss_can_save(self):
        with self.assertRaises(ValidationError):
            self.save({self.dev.pk: 1}, actor=self.dev)

    def test_boss_can_change_until_sunday_and_not_after(self):
        self.save({self.dev.pk: 1})
        self.save({self.designer.pk: 1, self.dev.pk: 2}, 'Yangi sovg‘a')
        rating = WeeklyRating.objects.get(publish_on=SUNDAY)
        self.assertEqual(rating.prize, 'Yangi sovg‘a')
        self.assertEqual(rating.places.get(place=1).employee, self.designer)
        with self.assertRaisesMessage(ValidationError, 'e’lon qilingan'):
            self.save({self.dev.pk: 1}, today=SUNDAY)

    def test_a_forgotten_week_can_still_be_set_on_sunday_and_publishes_at_once(self):
        self.assertIn(SUNDAY, wr.editable_weeks(SUNDAY))
        self.save({self.dev.pk: 1}, today=date(2026, 11, 9))
        self.assertTrue(wr.is_published(WeeklyRating.objects.get(publish_on=SUNDAY), date(2026, 11, 9)))

    def test_older_weeks_cannot_be_changed(self):
        with self.assertRaises(ValidationError):
            self.save({self.dev.pk: 1}, week=date(2026, 10, 25))


class PublishingTests(CompanyTestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.week = wr.current_week(self.today)
        self.url = reverse('enterprise:rating')

    def place(self, week, prize='Maxfiy sovg‘a'):
        rating = WeeklyRating.objects.create(publish_on=week, prize=prize)
        WeeklyPlace.objects.create(rating=rating, employee=self.dev, place=1)
        WeeklyPlace.objects.create(rating=rating, employee=self.designer, place=2)
        return rating

    def test_employees_see_nothing_before_sunday(self):
        self.place(self.week)
        self.login(self.designer)
        response = self.client.get(self.url)
        self.assertNotContains(response, 'Maxfiy sovg‘a')
        self.assertNotContains(response, 'rate-winner')
        self.assertNotContains(self.client.get(self.url, {'hafta': self.week.isoformat()}), 'Maxfiy sovg‘a')

    def test_everyone_sees_the_result_after_sunday(self):
        self.place(self.week - timedelta(days=7))
        self.login(self.designer)
        response = self.client.get(self.url)
        self.assertContains(response, 'Maxfiy sovg‘a')
        self.assertContains(response, self.dev.display_name)
        self.assertContains(response, '(siz)')
        self.assertContains(response, 'Haftalik reyting')

    def test_announced_once_winner_congratulated_and_clearing_does_not_repeat_it(self):
        self.place(self.week - timedelta(days=7))
        wr.announce_due()
        wr.announce_due()
        self.assertEqual(self.dev.notifications.filter(title__startswith='Tabriklaymiz').count(), 1)
        self.assertEqual(self.designer.notifications.filter(title__startswith='Haftalik reyting').count(), 1)
        self.assertFalse(self.dev.notifications.filter(title__startswith='Haftalik reyting').exists())
        Notification.objects.all().delete()
        wr.announce_due()
        self.assertFalse(Notification.objects.exists())

    def test_future_week_is_not_announced(self):
        self.place(self.week)
        wr.announce_due()
        self.assertFalse(Notification.objects.exists())

    def test_employee_cannot_reach_the_boss_screen_or_post(self):
        self.login(self.designer)
        self.assertNotContains(self.client.get(self.url, {'belgilash': '1'}), 'rate-form')
        response = self.client.post(self.url, {'hafta': self.week.isoformat(), 'prize': 'x', f'place_{self.designer.pk}': '1'})
        self.assertEqual(response.status_code, 405)
        self.assertFalse(WeeklyPlace.objects.exists())

    def test_manual_place_assignment_is_no_longer_available(self):
        self.login(self.founder)
        page = self.client.get(self.url, {'belgilash': '1'})
        self.assertNotContains(page, 'rate-form')
        response = self.client.post(self.url, {'hafta': self.week.isoformat(), 'prize': 'Bonus', f'place_{self.dev.pk}': '1'})
        self.assertEqual(response.status_code, 405)
        self.assertFalse(WeeklyRating.objects.exists())

    def test_bad_week_in_the_address_does_not_break_the_page(self):
        self.login(self.founder)
        for value in ('abc', '2026-13-45'):
            self.assertEqual(self.client.get(self.url, {'week': value}).status_code, 200)
            self.assertEqual(self.client.post(self.url, {'hafta': value, 'prize': 'x'}).status_code, 405)

    def test_erasing_an_employee_removes_their_places(self):
        from apps.enterprise.erasure import erase_employee
        self.place(self.week - timedelta(days=7))
        erase_employee(self.founder, self.dev)
        self.assertFalse(WeeklyPlace.objects.filter(employee_id=self.dev.pk).exists())
