from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.website.models import PublicationStatus, Service, SiteSettings


class ContentCacheTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_home_is_served_from_cache_after_first_request(self):
        SiteSettings.load()  # birinchi yaratilishi ham kontent o'zgarishi hisoblanadi
        self.client.get(reverse("website:home"))
        with self.assertNumQueries(2):  # faqat ATOMIC_REQUESTS tranzaksiyasi (savepoint)
            self.client.get(reverse("website:home"))

    def test_cms_change_invalidates_cached_home(self):
        self.client.get(reverse("website:home"))
        Service.objects.create(title="Kesh sinovi xizmati", slug="kesh-sinovi", summary="Qisqa", status=PublicationStatus.PUBLISHED)
        self.assertContains(self.client.get(reverse("website:home")), "Kesh sinovi xizmati")

    def test_settings_change_is_visible_immediately(self):
        self.client.get(reverse("website:home"))
        settings = SiteSettings.load()
        settings.company_name = "Yangi Nom"
        settings.save()
        self.assertContains(self.client.get(reverse("website:home")), "Yangi Nom")

    def test_cached_page_gets_a_fresh_csrf_token_per_visitor(self):
        from django.test import Client

        first = Client(enforce_csrf_checks=True)
        first.get(reverse("website:home"))
        second = Client(enforce_csrf_checks=True)
        page = second.get(reverse("website:home")).content.decode()
        self.assertNotIn("__ssb_csrf_slot__", page)
        token = page.split('name="csrfmiddlewaretoken" value="', 1)[1].split('"', 1)[0]
        response = second.post(reverse("website:contact"), {"csrfmiddlewaretoken": token, "name": "A"})
        self.assertNotEqual(response.status_code, 403)

    def test_staff_never_get_the_guest_page(self):
        from apps.accounts.models import User

        self.client.get(reverse("website:home"))
        user = User.objects.create_user("kesh", password="x-Parol-2026-uzun")
        self.client.force_login(user)
        self.assertNotContains(self.client.get(reverse("website:home")), "Shaxsiy kabinet")
