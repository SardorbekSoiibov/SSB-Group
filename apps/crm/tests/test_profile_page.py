from datetime import timedelta
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.core.testing import CompanyTestCase
from apps.enterprise import operations
from apps.enterprise.models import WorkShift


def image_file(name='rasm.png', color='#2f7fd6'):
    buffer = BytesIO()
    Image.new('RGB', (64, 64), color).save(buffer, 'PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


class ProfilePhotoTests(CompanyTestCase):
    def upload(self, file):
        return self.client.post(reverse('crm:profile_photo'), {'photo': file}, follow=True)

    def test_new_photo_replaces_the_file_and_changes_the_address(self):
        self.login(self.dev)
        self.upload(image_file())
        self.dev.refresh_from_db()
        first_name, first_version, storage = self.dev.photo.name, self.dev.photo_version, self.dev.photo.storage
        self.assertTrue(storage.exists(first_name))
        with self.captureOnCommitCallbacks(execute=True):
            response = self.upload(image_file(color='#30a46c'))
        self.dev.refresh_from_db()
        self.assertNotEqual(self.dev.photo_version, first_version)
        self.assertFalse(storage.exists(first_name))
        self.assertTrue(storage.exists(self.dev.photo.name))
        self.assertContains(response, '?v=' + self.dev.photo_version)
        self.assertEqual(self.client.get(reverse('crm:employee_photo', args=[self.dev.pk])).status_code, 200)

    def test_photo_can_be_removed(self):
        self.login(self.dev)
        self.upload(image_file())
        self.dev.refresh_from_db()
        name, storage = self.dev.photo.name, self.dev.photo.storage
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('crm:profile_photo'), {'action': 'remove'})
        self.dev.refresh_from_db()
        self.assertFalse(self.dev.photo)
        self.assertFalse(storage.exists(name))

    def test_files_that_are_not_images_are_refused(self):
        self.login(self.dev)
        for file, message in ((SimpleUploadedFile('rasm.png', b'not an image'), 'rasm emas'),
                              (SimpleUploadedFile('dastur.exe', b'MZ'), 'rasm emas')):
            response = self.upload(file)
            self.assertContains(response, message)
        response = self.client.post(reverse('crm:profile_photo'), {}, follow=True)
        self.assertContains(response, 'Rasm tanlang')
        self.dev.refresh_from_db()
        self.assertFalse(self.dev.photo)

    def test_photo_needs_a_signed_in_person_and_post(self):
        self.assertEqual(self.client.post(reverse('crm:profile_photo'), {'photo': image_file()}).status_code, 302)
        self.login(self.dev)
        self.assertEqual(self.client.get(reverse('crm:profile_photo')).status_code, 405)

    def test_chat_receives_the_photo_address(self):
        from apps.chat.views import public_person
        self.assertEqual(public_person(self.dev)['photo'], '')
        self.login(self.dev)
        self.upload(image_file())
        self.dev.refresh_from_db()
        self.assertIn('?v=' + self.dev.photo_version, public_person(self.dev)['photo'])


class PasswordFormTests(CompanyTestCase):
    def post(self, old, new, repeat=None):
        return self.client.post(reverse('accounts:password_change'), {
            'old_password': old, 'new_password1': new, 'new_password2': repeat if repeat is not None else new})

    def test_page_and_errors_are_in_uzbek(self):
        self.login(self.dev)
        page = self.client.get(reverse('accounts:password_change'))
        self.assertContains(page, 'Joriy parol')
        self.assertContains(page, 'autocomplete="current-password"')
        self.assertNotContains(page, 'Your password')
        self.assertNotContains(page, 'Old password')
        self.assertContains(self.post('wrong-old-value', 'Kuchli-Parol-2026!'), 'Joriy parol noto‘g‘ri')
        for new, message in (('12345678901234', 'raqamlardan'), ('Qisqa1!', 'kamida 10'), ('password123', 'juda oddiy')):
            response = self.post('wrong-old-value', new)
            self.assertIn(message, str(response.context['form'].errors['new_password2']))
        response = self.post('wrong-old-value', 'Kuchli-Parol-2026!', 'Boshqa-Parol-2026!')
        self.assertContains(response, 'bir xil emas')


class SchedulePageTests(CompanyTestCase):
    def setUp(self):
        super().setUp()
        self.monday = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
        self.url = reverse('enterprise:schedule')

    def at(self, days, hour):
        return timezone.make_aware(timezone.datetime(self.monday.year, self.monday.month, self.monday.day, hour) + timedelta(days=days))

    def test_week_is_seven_days_with_shifts_in_their_day_and_honest_totals(self):
        operations.save_shift(self.founder, self.dev, self.at(1, 9), self.at(1, 18), 'Ofis')
        cancelled = operations.save_shift(self.founder, self.dev, self.at(2, 9), self.at(2, 13), 'Ofis')
        operations.save_shift(self.founder, self.dev, cancelled.starts_at, cancelled.ends_at, 'Ofis', '', cancelled.pk, True)
        self.login(self.founder)
        response = self.client.get(self.url)
        days = response.context['days']
        self.assertEqual([day['name'] for day in days][:2], ['Dushanba', 'Seshanba'])
        self.assertEqual(len(days), 7)
        self.assertEqual(len(days[1]['shifts']), 1)
        self.assertEqual(response.context['stats'], {'shifts': 1, 'people': 1, 'hours': '9', 'cancelled': 1})

    def test_saving_opens_the_week_of_the_shift(self):
        self.login(self.founder)
        later = self.monday + timedelta(days=21)
        response = self.client.post(self.url, {'employee': self.dev.pk, 'starts_at': f'{later}T09:00', 'ends_at': f'{later}T18:00', 'location': 'Ofis'})
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'dan={later}', response['Location'])
        self.assertEqual(WorkShift.objects.filter(employee=self.dev).count(), 1)

    def test_editing_keeps_the_person_even_if_the_post_says_otherwise(self):
        shift = operations.save_shift(self.founder, self.dev, self.at(1, 9), self.at(1, 18), 'Ofis')
        self.login(self.founder)
        response = self.client.post(f'{self.url}?edit={shift.pk}', {'employee': self.designer.pk, 'starts_at': f'{self.monday + timedelta(days=1)}T10:00',
                                                                  'ends_at': f'{self.monday + timedelta(days=1)}T18:00', 'location': 'Masofaviy'})
        self.assertEqual(response.status_code, 302)
        shift.refresh_from_db()
        self.assertEqual((shift.employee, shift.location), (self.dev, 'Masofaviy'))

    def test_overlap_stays_in_the_form(self):
        operations.save_shift(self.founder, self.dev, self.at(1, 9), self.at(1, 18), 'Ofis')
        self.login(self.founder)
        day = self.monday + timedelta(days=1)
        response = self.client.post(self.url, {'employee': self.dev.pk, 'starts_at': f'{day}T10:00', 'ends_at': f'{day}T12:00', 'location': 'Ofis'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ustma-ust')

    def test_employee_sees_only_own_shifts_and_no_controls(self):
        operations.save_shift(self.founder, self.dev, self.at(1, 9), self.at(1, 18), 'Ofis')
        operations.save_shift(self.founder, self.designer, self.at(1, 9), self.at(1, 18), 'Ofis')
        self.login(self.dev)
        response = self.client.get(self.url)
        self.assertEqual([shift.employee for shift in response.context['shifts']], [self.dev])
        self.assertNotContains(response, 'data-shift-add')
        self.assertNotContains(response, 'shift-tools')

    def test_any_date_opens_its_full_week_monday_to_sunday(self):
        # Jadval har doim to'liq hafta: istalgan sana yoki uzun oraliq o'sha sananing haftasini ochadi.
        operations.save_shift(self.founder, self.dev, self.at(1, 9), self.at(1, 18), 'Ofis')
        self.login(self.founder)
        response = self.client.get(self.url, {'dan': str(self.monday + timedelta(days=3)), 'gacha': str(self.monday + timedelta(days=200))})
        self.assertEqual(response.context['start'], self.monday)
        self.assertEqual(len(response.context['days']), 7)
        self.assertEqual(response.context['days'][0]['date'].weekday(), 0)

    def test_series_repeats_on_chosen_weekdays_and_skips_busy_times(self):
        from apps.enterprise.models import WorkShift
        operations.save_shift(self.founder, self.dev, self.at(7, 10), self.at(7, 12), 'Ofis')  # keyingi dushanba band
        created, skipped = operations.save_shift_series(self.founder, self.dev, self.at(7, 9), self.at(7, 18), 'Ofis', days=[0, 2, 4], repeat=2)
        self.assertEqual((len(created), skipped), (5, 1))
        self.assertEqual(sorted({timezone.localtime(s.starts_at).weekday() for s in created}), [0, 2, 4])
        self.assertEqual(WorkShift.objects.filter(employee=self.dev, cancelled=False).count(), 6)
