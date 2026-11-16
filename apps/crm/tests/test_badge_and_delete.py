"""Xodim bedjigi (ID, QR tasdiqlash, PDF) va e'lonni muallif tomonidan o'chirish."""
import os
import shutil
import tempfile

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.crm import badges
from apps.crm.models import Announcement

PASSWORD = "Test-Password-2026!"


class BadgeTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls._media = tempfile.mkdtemp(prefix="ssb-badge-")
        cls._override = override_settings(PRIVATE_MEDIA_ROOT=cls._media)
        cls._override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        try:
            super().tearDownClass()
        finally:
            cls._override.disable()
            shutil.rmtree(cls._media, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        os.environ["SSB_FOUNDER_PASSWORD"] = PASSWORD
        call_command("bootstrap_company", username="owner", no_input=True, stdout=open(os.devnull, "w"))
        cls.owner = User.objects.get(username="owner")
        cls.worker = User.objects.create_user("worker", password=PASSWORD, first_name="Ali", last_name="Valiyev", job_title="Dasturchi")
        cls.worker.set_capabilities(["announcements.view", "announcements.manage"])
        cls.other = User.objects.create_user("other", password=PASSWORD)
        cls.other.set_capabilities(["announcements.view", "announcements.manage"])

    def test_badge_id_and_signed_token(self):
        self.assertEqual(badges.badge_id(self.worker), f"SSB-{self.worker.pk:04d}")
        token = badges.badge_token(self.worker)
        self.assertEqual(badges.user_from_token(token), self.worker)
        self.assertIsNone(badges.user_from_token(f"{self.owner.pk}:" + token.split(":", 1)[1]))  # boshqa ID bilan soxta
        self.assertIsNone(badges.user_from_token("garbage"))

    def test_public_verify_page(self):
        token = badges.badge_token(self.worker)
        r = self.client.get(reverse("badge_verify", args=[token]))
        self.assertContains(r, "Tasdiqlangan xodim")
        self.assertContains(r, "Ali Valiyev")
        self.assertContains(r, badges.badge_id(self.worker))
        self.assertNotContains(r, self.worker.email or "@@none@@")
        self.assertEqual(r["X-Robots-Tag"], "noindex, nofollow")
        # Ishdan ketgan xodim — bedjik amal qilmaydi
        self.worker.status = User.Status.DEACTIVATED
        self.worker.save()
        r = self.client.get(reverse("badge_verify", args=[token]))
        self.assertContains(r, "Bedjik amal qilmaydi")
        self.assertNotContains(r, "Tasdiqlangan xodim")
        # Soxta QR
        r = self.client.get(reverse("badge_verify", args=["12:fake"]))
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, "haqiqiy emas", status_code=404)

    def test_employee_page_shows_badge_and_pdf_downloads(self):
        self.client.force_login(self.owner)
        page = self.client.get(reverse("crm:employee_detail", args=[self.worker.pk]))
        self.assertContains(page, "data-badge-card")
        self.assertContains(page, badges.badge_id(self.worker))
        self.assertContains(page, "<svg")
        pdf = self.client.get(reverse("crm:employee_badge_pdf", args=[self.worker.pk]))
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertIn("bedjik-SSB-", pdf["Content-Disposition"])

    def test_pdf_requires_permission(self):
        self.assertEqual(self.client.get(reverse("crm:employee_badge_pdf", args=[self.worker.pk])).status_code, 302)
        self.client.force_login(self.other)  # xodimlar katalogini ko'rish huquqi yo'q
        self.assertIn(self.client.get(reverse("crm:employee_badge_pdf", args=[self.worker.pk])).status_code, (403, 404))

    def test_author_and_owner_can_delete_announcement_others_cannot(self):
        a = Announcement.objects.create(title="Test e'lon", body="Matn", author=self.worker)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse("crm:announcement_delete", args=[a.pk])).status_code, 403)
        self.assertTrue(Announcement.objects.filter(pk=a.pk).exists())
        self.client.force_login(self.worker)
        page = self.client.get(reverse("crm:announcements"))
        self.assertContains(page, reverse("crm:announcement_delete", args=[a.pk]))
        self.assertEqual(self.client.get(reverse("crm:announcement_delete", args=[a.pk])).status_code, 405)
        self.assertEqual(self.client.post(reverse("crm:announcement_delete", args=[a.pk])).status_code, 302)
        self.assertFalse(Announcement.objects.filter(pk=a.pk).exists())
        self.assertTrue(AuditEvent.objects.filter(action="announcement.deleted", actor=self.worker).exists())
        b = Announcement.objects.create(title="Boshqa", body="Matn", author=self.other)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse("crm:announcement_delete", args=[b.pk])).status_code, 302)
        self.assertFalse(Announcement.objects.filter(pk=b.pk).exists())

    def test_others_do_not_see_delete_button(self):
        a = Announcement.objects.create(title="Test", body="Matn", author=self.worker)
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse("crm:announcements")), reverse("crm:announcement_delete", args=[a.pk]))
