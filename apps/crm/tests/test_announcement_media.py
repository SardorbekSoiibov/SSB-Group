"""E'lonlar: cheksiz rasm, havola tugmasi va rasmlarni faqat ruxsatli xodimlarga ko'rsatish.

CompanyTestCase ishlatilmaydi: u bootstrap qilmaydigan eski rollarni kutadi. Bu yerda kerakli hisoblar o'zi yaratiladi."""
import os
import shutil
import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.accounts.models import User
from apps.crm.models import Announcement, AnnouncementImage

PASSWORD = "Test-Password-2026!"


def png(name="r.png", color=(0, 122, 255)):
    buf = BytesIO()
    Image.new("RGB", (40, 30), color).save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class AnnouncementMediaTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls._media = tempfile.mkdtemp(prefix="ssb-ann-")
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
        cls.reader = User.objects.create_user("reader", password=PASSWORD)
        cls.reader.set_capabilities(["announcements.view"])
        cls.outsider = User.objects.create_user("outsider", password=PASSWORD)
        cls.outsider.set_capabilities([])

    def post(self, **extra):
        data = {"title": "Jamoa yig‘ilishi", "body": "Ertaga soat 10:00 da.", "link_label": "", "link_url": ""}
        data.update(extra)
        return self.client.post(reverse("crm:announcements"), data)

    def test_many_images_and_link_are_saved_and_shown(self):
        self.client.force_login(self.owner)
        files = [png(f"r{i}.png") for i in range(6)]
        r = self.post(images=files, link_label="Ro‘yxatdan o‘tish", link_url="https://example.com/form")
        self.assertEqual(r.status_code, 302)
        a = Announcement.objects.get()
        self.assertEqual(a.images.count(), 6)
        self.assertEqual(a.link_url, "https://example.com/form")
        self.assertEqual(list(a.images.values_list("order", flat=True)), [0, 1, 2, 3, 4, 5])
        self.client.force_login(self.reader)
        page = self.client.get(reverse("crm:announcements"))
        self.assertContains(page, "Ro‘yxatdan o‘tish")
        self.assertContains(page, 'href="https://example.com/form"')
        self.assertContains(page, 'rel="noopener noreferrer"')
        self.assertContains(page, "+2")  # 4 ta ko'rinadi, qolgan 2 tasi "+2"
        img = a.images.first()
        resp = self.client.get(reverse("crm:announcement_image", args=[img.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(b"".join(resp.streaming_content).startswith(b"\x89PNG"))

    def test_images_are_private(self):
        self.client.force_login(self.owner)
        self.post(images=[png()])
        img = AnnouncementImage.objects.get()
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse("crm:announcement_image", args=[img.pk])).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("crm:announcement_image", args=[img.pk])).status_code, 302)

    def test_text_only_announcement_still_works(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.post().status_code, 302)
        self.assertFalse(Announcement.objects.get().images.exists())

    def test_unsafe_or_missing_link_is_rejected(self):
        self.client.force_login(self.owner)
        for bad in ("javascript:alert(1)", "ftp://example.com/x", "example"):
            r = self.post(link_url=bad)
            self.assertEqual(r.status_code, 200, bad)
        r = self.post(link_label="Ochish")
        self.assertContains(r, "Tugma uchun havola kiriting.")
        self.assertFalse(Announcement.objects.exists())

    def test_non_image_upload_is_rejected(self):
        self.client.force_login(self.owner)
        fake = SimpleUploadedFile("x.png", b"not an image", content_type="image/png")
        self.assertEqual(self.post(images=[fake]).status_code, 200)
        self.assertFalse(Announcement.objects.exists())

    def test_reader_cannot_post(self):
        self.client.force_login(self.reader)
        self.assertEqual(self.post().status_code, 403)

    def test_deleting_announcement_removes_files(self):
        self.client.force_login(self.owner)
        self.post(images=[png()])
        img = AnnouncementImage.objects.get()
        path = img.image.path
        self.assertTrue(os.path.exists(path))
        with self.captureOnCommitCallbacks(execute=True):
            Announcement.objects.get().delete()
        self.assertFalse(os.path.exists(path))
