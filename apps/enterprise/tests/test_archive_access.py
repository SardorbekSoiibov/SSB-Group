"""Company archive: Founder code asked on every visit, shared RAR/ZIP projects, math-checked downloads."""
import shutil
import tempfile
import uuid
import zipfile
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import CompanyTestCase, unlocked_archive_request
from apps.enterprise import operations
from apps.enterprise.archive_access import CHALLENGE_KEY, GRANT_KEY, has_archive_access
from apps.enterprise.forms import ArchiveCodeForm
from apps.enterprise.models import ArchiveAccess, ArchiveAccessAttempt, ProjectArchive
from apps.notifications.models import Notification

CODE = 'company-archive-2026'
ARCHIVES = '/management/enterprise/archives/'


def zip_bytes(text):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr(zipfile.ZipInfo('loyiha/README.txt', date_time=(2026, 1, 1, 0, 0, 0)), text)
    return buffer.getvalue()


def project(name='work.zip', text='Completed work'):
    return SimpleUploadedFile(name, zip_bytes(text))


def release(response):
    # response.close() would fire request_finished and close the test transaction's DB connection.
    for close in response._resource_closers:
        close()


@override_settings(REQUIRE_MALWARE_SCAN=False, MALWARE_SCANNER='')
class ArchiveAccessTests(CompanyTestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp(prefix='ssb-archive-test-')
        self.media_override = override_settings(PRIVATE_MEDIA_ROOT=self.media)
        self.media_override.enable()

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.media, ignore_errors=True)

    def unlock(self, user, code=CODE):
        self.login(user)
        return self.client.post(reverse('enterprise:archive_unlock'), {'code': code})

    def upload(self, name='Mehmonxona tizimi', text='Completed work', key=None, filename='work.zip'):
        return self.client.post(reverse('enterprise:archives'), {
            'project_name': name, 'upload_key': str(key or uuid.uuid4()), 'file': project(filename, text)})

    def download(self, archive, answer=None):
        """Second step: open the question page, then answer it."""
        url = reverse('enterprise:archive_download', args=[archive.pk])
        page = self.client.get(url)
        if page.status_code != 200:
            return page
        correct = self.client.session[CHALLENGE_KEY]['answer']
        return self.client.post(url, {'answer': str(correct if answer is None else answer)})

    def unlocked(self):
        return self.client.get(reverse('enterprise:archives')).context['unlocked']

    # --- Founder code management -------------------------------------------------

    def test_only_founder_sets_code_and_it_is_stored_hashed(self):
        policy = operations.set_archive_code(self.founder, CODE)
        self.assertTrue(policy.access_hash)
        self.assertNotIn(CODE, policy.access_hash)
        for actor in (self.ceo, self.cofounder, self.lead, self.dev):
            with self.assertRaises(PermissionDenied):
                operations.set_archive_code(actor, 'another-code-2026')
            self.login(actor)
            response = self.client.post(reverse('enterprise:archive_code'), {'code': 'x' * 10, 'confirm_code': 'x' * 10})
            self.assertEqual(response.status_code, 403)
        self.assertEqual(ArchiveAccess.load().version, policy.version)

    def test_code_length_and_confirmation_are_validated(self):
        with self.assertRaises(ValidationError):
            operations.set_archive_code(self.founder, 'short')
        self.assertFalse(ArchiveCodeForm({'code': 'abcdefgh1', 'confirm_code': 'abcdefgh2'}).is_valid())
        self.login(self.founder)
        response = self.client.post(reverse('enterprise:archive_code'), {'code': 'abcdefgh1', 'confirm_code': 'abcdefgh2'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ArchiveAccess.load().access_hash)

    def test_founder_setting_code_unlocks_own_session(self):
        self.login(self.founder)
        response = self.client.post(reverse('enterprise:archive_code'), {'code': CODE, 'confirm_code': CODE})
        self.assertRedirects(response, reverse('enterprise:archives'))
        self.assertTrue(self.unlocked())

    # --- Step 1: code on every visit ----------------------------------------------

    def test_locked_section_hides_files_and_rejects_upload_and_download(self):
        archive = operations.upload_archive(unlocked_archive_request(self.dev, CODE), 'Eski loyiha', project('a.zip'), uuid.uuid4())
        self.login(self.designer)
        response = self.client.get(reverse('enterprise:archives'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['unlocked'])
        self.assertNotContains(response, 'a.zip')
        self.assertEqual(self.upload().status_code, 403)
        self.assertEqual(ProjectArchive.objects.count(), 1)
        url = reverse('enterprise:archive_download', args=[archive.pk])
        self.assertRedirects(self.client.get(url), reverse('enterprise:archives'))
        self.assertEqual(self.client.post(url, {'answer': '1'}).status_code, 403)

    def test_unconfigured_code_cannot_be_unlocked(self):
        response = self.unlock(self.dev, 'anything-at-all')
        self.assertContains(response, 'Asoschi hali kirish kodini o‘rnatmagan')
        self.assertNotContains(response, 'id="archive-unlock-form"')
        self.assertNotIn(GRANT_KEY, self.client.session)

    def test_leaving_the_section_asks_for_the_code_again(self):
        operations.set_archive_code(self.founder, CODE)
        self.unlock(self.dev)
        self.assertTrue(self.unlocked())
        self.assertTrue(self.unlocked())  # Reloading the archive keeps the visit.
        # Background traffic while the archive is open does not end the visit.
        self.client.get(reverse('enterprise:api_notifications'))
        self.client.get(reverse('enterprise:overview'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.client.get(reverse('enterprise:overview'), HTTP_SEC_FETCH_MODE='cors', HTTP_SEC_FETCH_DEST='empty')
        self.assertIn(GRANT_KEY, self.client.session)
        # Opening another page in the browser relocks it.
        self.client.get(reverse('enterprise:overview'), HTTP_SEC_FETCH_MODE='navigate', HTTP_SEC_FETCH_DEST='document')
        self.assertNotIn(GRANT_KEY, self.client.session)
        self.assertFalse(self.unlocked())
        # Same without fetch metadata headers (older clients).
        self.unlock(self.dev)
        self.client.get(reverse('enterprise:schedule'))
        self.assertFalse(self.unlocked())

    def test_wrong_codes_are_rate_limited_per_user(self):
        operations.set_archive_code(self.founder, CODE)
        for _ in range(8):
            self.assertContains(self.unlock(self.dev, 'wrong-code-value'), 'Arxiv kodi noto‘g‘ri')
        response = self.unlock(self.dev, CODE)
        self.assertContains(response, 'Juda ko‘p urinish')
        self.assertNotIn(GRANT_KEY, self.client.session)
        self.assertRedirects(self.unlock(self.designer, CODE), reverse('enterprise:archives'))
        ArchiveAccessAttempt.objects.filter(user=self.dev).update(window_started=timezone.now() - timedelta(minutes=16))
        self.assertRedirects(self.unlock(self.dev, CODE), reverse('enterprise:archives'))
        self.assertEqual(ArchiveAccessAttempt.objects.get(user=self.dev).failures, 0)

    def test_grant_expires_after_one_hour_and_lock_revokes_it(self):
        operations.set_archive_code(self.founder, CODE)
        self.unlock(self.dev)
        self.assertTrue(self.unlocked())
        later = timezone.now() + timedelta(hours=1, seconds=5)
        with patch('apps.enterprise.archive_access.timezone.now', return_value=later):
            self.assertFalse(self.unlocked())
        self.client.post(reverse('enterprise:archive_lock'))
        self.assertNotIn(GRANT_KEY, self.client.session)
        self.assertFalse(self.unlocked())

    def test_grant_belongs_to_one_user_and_inactive_role_loses_access(self):
        operations.set_archive_code(self.founder, CODE)
        self.unlock(self.dev)
        grant = self.client.session[GRANT_KEY]
        self.login(self.designer)
        session = self.client.session
        session[GRANT_KEY] = grant
        session.save()
        self.assertFalse(self.unlocked())
        role = self.dev.role
        role.is_active = False
        role.save(update_fields=['is_active'])
        self.dev.refresh_from_db()
        self.assertFalse(has_archive_access(unlocked_archive_request(self.dev)))
        self.login(self.dev)
        self.assertNotEqual(self.client.get(reverse('enterprise:archives')).status_code, 200)

    # --- Shared RAR/ZIP projects and authors -------------------------------------

    def test_employee_adds_project_with_author_and_everyone_unlocked_downloads(self):
        operations.set_archive_code(self.founder, CODE)
        self.unlock(self.dev)
        response = self.upload(name='Mijoz uchun sayt', text='Delivered source', filename='sayt.zip')
        self.assertRedirects(response, reverse('enterprise:archives'))
        archive = ProjectArchive.objects.get()
        self.assertEqual((archive.project_name, archive.project_id, archive.uploader), ('Mijoz uchun sayt', None, self.dev))
        self.assertTrue(archive.file.path.startswith(self.media))
        self.assertTrue(Notification.objects.filter(recipient=self.designer, dedupe_key=f'archive:{archive.pk}').exists())
        self.assertFalse(Notification.objects.filter(recipient=self.dev, dedupe_key=f'archive:{archive.pk}').exists())
        self.unlock(self.outsider)
        page = self.client.get(reverse('enterprise:archives'))
        self.assertContains(page, 'Mijoz uchun sayt')
        self.assertContains(page, 'Muallif')
        self.assertContains(page, self.dev.display_name)
        download = self.download(archive)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(b''.join(download.streaming_content), zip_bytes('Delivered source'))
        self.assertIn('no-store', download['Cache-Control'])
        release(download)

    def test_only_rar_or_zip_projects_are_accepted(self):
        operations.set_archive_code(self.founder, CODE)
        self.unlock(self.dev)
        response = self.client.post(reverse('enterprise:archives'), {
            'project_name': 'Matn', 'upload_key': str(uuid.uuid4()), 'file': SimpleUploadedFile('notes.txt', b'plain text')})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'RAR yoki ZIP')
        with self.assertRaises(ValidationError):
            operations.upload_archive(unlocked_archive_request(self.dev), 'Rasm', SimpleUploadedFile('a.png', b'x'), uuid.uuid4())
        self.assertEqual(ProjectArchive.objects.count(), 0)

    def test_repeated_upload_key_does_not_create_duplicates(self):
        operations.set_archive_code(self.founder, CODE)
        self.unlock(self.dev)
        key = uuid.uuid4()
        self.upload(key=key)
        self.upload(key=key)
        self.assertEqual(ProjectArchive.objects.count(), 1)
        response = self.upload(key=key, name='Boshqa nom')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'boshqa faylga tegishli')
        self.assertEqual(ProjectArchive.objects.count(), 1)

    def test_invalid_project_name_is_rejected(self):
        operations.set_archive_code(self.founder, CODE)
        self.unlock(self.dev)
        self.assertEqual(self.upload(name='x').status_code, 200)
        with self.assertRaises(ValidationError):
            operations.upload_archive(unlocked_archive_request(self.dev), 'bad\x00name', project(), uuid.uuid4())
        self.assertEqual(ProjectArchive.objects.count(), 0)

    # --- Step 2: math question before each download -------------------------------

    def test_download_requires_correct_math_answer(self):
        operations.set_archive_code(self.founder, CODE)
        archive = operations.upload_archive(unlocked_archive_request(self.dev), 'Loyiha', project(text='body'), uuid.uuid4())
        self.unlock(self.designer)
        url = reverse('enterprise:archive_download', args=[archive.pk])
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, '= ?')
        challenge = self.client.session[CHALLENGE_KEY]
        self.assertNotContains(page, f'value="{challenge["answer"]}"')
        # Wrong answer: no file, a new question.
        wrong = self.client.post(url, {'answer': str(challenge['answer'] + 1)})
        self.assertEqual(wrong.status_code, 400)
        self.assertNotIn('Content-Disposition', wrong)
        self.assertContains(wrong, 'Javob noto‘g‘ri', status_code=400)
        # Replaying the old correct answer after a failure does not work: each answer consumes the question.
        self.assertEqual(self.client.post(url, {'answer': str(challenge['answer'])}).status_code, 400)
        # Garbage input is rejected without a server error.
        self.client.get(url)
        self.assertEqual(self.client.post(url, {'answer': '1e9'}).status_code, 400)
        response = self.download(archive)
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])
        release(response)
        self.assertNotIn(CHALLENGE_KEY, self.client.session)
        # The confirmation cookie exists only after a correct answer and only echoes a safe token.
        self.client.cookies.pop('ssb_archive_download', None)
        self.client.get(url)
        answer = self.client.session[CHALLENGE_KEY]['answer']
        started = self.client.post(url, {'answer': answer, 'download_token': 'abc123def456'})
        self.assertEqual(started.cookies['ssb_archive_download'].value, 'abc123def456')
        release(started)
        self.client.get(url)
        answer = self.client.session[CHALLENGE_KEY]['answer']
        unsafe = self.client.post(url, {'answer': answer, 'download_token': 'a;b=c<script>'})
        self.assertNotIn('ssb_archive_download', unsafe.cookies)
        release(unsafe)
        self.client.get(url)
        answer = self.client.session[CHALLENGE_KEY]['answer']
        refused = self.client.post(url, {'answer': answer + 1, 'download_token': 'abc123def456'})
        self.assertEqual(refused.status_code, 400)
        self.assertNotIn('ssb_archive_download', refused.cookies)

    def test_question_is_bound_to_one_file_and_expires(self):
        operations.set_archive_code(self.founder, CODE)
        request = unlocked_archive_request(self.dev)
        first = operations.upload_archive(request, 'Birinchi', project('a.zip', 'a'), uuid.uuid4())
        second = operations.upload_archive(request, 'Ikkinchi', project('b.zip', 'b'), uuid.uuid4())
        self.unlock(self.designer)
        self.client.get(reverse('enterprise:archive_download', args=[first.pk]))
        answer = self.client.session[CHALLENGE_KEY]['answer']
        self.assertEqual(self.client.post(reverse('enterprise:archive_download', args=[second.pk]), {'answer': answer}).status_code, 400)
        self.client.get(reverse('enterprise:archive_download', args=[first.pk]))
        answer = self.client.session[CHALLENGE_KEY]['answer']
        later = timezone.now() + timedelta(minutes=6)
        with patch('apps.enterprise.archive_access.timezone.now', return_value=later):
            self.assertEqual(self.client.post(reverse('enterprise:archive_download', args=[first.pk]), {'answer': answer}).status_code, 400)

    def test_code_rotation_revokes_existing_grants(self):
        operations.set_archive_code(self.founder, CODE)
        archive = operations.upload_archive(unlocked_archive_request(self.dev), 'Loyiha', project(text='body'), uuid.uuid4())
        self.unlock(self.designer)
        response = self.download(archive)
        self.assertEqual(response.status_code, 200)
        release(response)
        operations.set_archive_code(self.founder, 'rotated-code-2026')
        self.assertRedirects(self.client.get(reverse('enterprise:archive_download', args=[archive.pk])), reverse('enterprise:archives'))
        self.assertContains(self.unlock(self.designer, CODE), 'Arxiv kodi noto‘g‘ri')
        self.assertRedirects(self.unlock(self.designer, 'rotated-code-2026'), reverse('enterprise:archives'))

    def test_tampered_file_fails_integrity_check(self):
        operations.set_archive_code(self.founder, CODE)
        archive = operations.upload_archive(unlocked_archive_request(self.dev), 'Loyiha', project(text='original'), uuid.uuid4())
        with open(archive.file.path, 'wb') as handle:
            handle.write(b'tampered')
        self.unlock(self.dev)
        self.assertEqual(self.download(archive).status_code, 403)

    def test_page_shows_stats_sorting_and_readable_sizes(self):
        from apps.enterprise.templatetags.boshqaruv import plain_filesize
        self.assertEqual(plain_filesize(160), '160 bayt')
        self.assertEqual(plain_filesize(2048), '2,0 KB')
        operations.set_archive_code(self.founder, CODE)
        request = unlocked_archive_request(self.dev)
        operations.upload_archive(request, 'Beta', project('b.zip', 'kichik'), uuid.uuid4())
        operations.upload_archive(unlocked_archive_request(self.lead), 'Alfa', project('a.zip', 'katta matn' * 40), uuid.uuid4())
        self.unlock(self.designer)
        url = reverse('enterprise:archives')
        response = self.client.get(url)
        self.assertEqual((response.context['stats']['total'], response.context['stats']['authors']), (2, 2))
        self.assertEqual([i.project_name for i in self.client.get(url, {'sort': 'name'}).context['items']], ['Alfa', 'Beta'])
        self.assertEqual([i.project_name for i in self.client.get(url, {'sort': 'old'}).context['items']], ['Beta', 'Alfa'])
        # An unknown sort value falls back to the default instead of reaching the database.
        self.assertEqual(self.client.get(url, {'sort': 'password'}).context['sort'], 'new')

    def test_author_or_founder_removes_a_project_completely(self):
        from apps.audit.models import AuditEvent
        from apps.core.testing import PASSWORD
        operations.set_archive_code(self.founder, CODE)
        mine = operations.upload_archive(unlocked_archive_request(self.dev), 'Mening', project('m.zip', 'm'), uuid.uuid4())
        other = operations.upload_archive(unlocked_archive_request(self.lead), 'Boshqa', project('o.zip', 'o'), uuid.uuid4())
        storage, path = mine.file.storage, mine.file.name
        url = reverse('enterprise:archive_delete', args=[mine.pk])
        good = {'confirm_password': PASSWORD}
        # A locked visit and a GET request cannot delete.
        self.login(self.dev)
        self.assertEqual(self.client.post(url, good).status_code, 403)
        self.unlock(self.dev)
        self.assertEqual(self.client.get(url).status_code, 405)
        # Another employee cannot delete it, nor see the control on it.
        self.unlock(self.designer)
        self.assertEqual(self.client.post(url, good).status_code, 403)
        self.assertNotContains(self.client.get(reverse('enterprise:archives')), 'data-secure-delete=')
        # A wrong password deletes nothing.
        self.unlock(self.dev)
        self.client.post(url, {'confirm_password': 'xato'})
        self.assertTrue(ProjectArchive.objects.filter(pk=mine.pk).exists())
        page = self.client.get(reverse('enterprise:archives'))
        self.assertContains(page, url)
        self.assertNotContains(page, reverse('enterprise:archive_delete', args=[other.pk]))
        with self.captureOnCommitCallbacks(execute=True):
            self.assertRedirects(self.client.post(url, good), reverse('enterprise:archives'))
        self.assertFalse(storage.exists(path))
        self.assertFalse(ProjectArchive.objects.filter(pk=mine.pk).exists())
        self.assertEqual(self.client.get(reverse('enterprise:archive_download', args=[mine.pk])).status_code, 404)
        self.assertEqual(self.client.post(url, good).status_code, 404)
        self.assertTrue(AuditEvent.objects.filter(action='archive.removed').exists())
        self.unlock(self.founder, CODE)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('enterprise:archive_delete', args=[other.pk]), good)
        self.assertEqual(ProjectArchive.objects.count(), 0)

    def test_search_and_legacy_project_archives(self):
        operations.set_archive_code(self.founder, CODE)
        request = unlocked_archive_request(self.dev)
        operations.upload_archive(request, 'Mehmonxona', project('hotel.zip', 'h'), uuid.uuid4())
        operations.upload_archive(request, 'Klinika', project('clinic.zip', 'c'), uuid.uuid4())
        legacy = ProjectArchive.objects.create(project=self.project, uploader=self.dev, file='project-archives/legacy.zip',
                                               filename='legacy.zip', size=1, sha256='0' * 64, scan_status='skipped')
        self.assertEqual(legacy.display_project_name, self.project.name)
        self.unlock(self.designer)
        response = self.client.get(reverse('enterprise:archives'), {'q': 'klinika'})
        self.assertEqual([item.filename for item in response.context['items']], ['clinic.zip'])
        response = self.client.get(reverse('enterprise:archives'), {'q': self.project.name})
        self.assertEqual([item.filename for item in response.context['items']], ['legacy.zip'])
