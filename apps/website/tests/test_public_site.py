import time
from unittest import mock

from django.core.cache import cache
from django.urls import reverse

from apps.core.testing import CompanyTestCase
from apps.crm.models import Inquiry
from apps.website.models import PortfolioProject, PublicationStatus, Service, TeamMember


def payload(form, **extra):
    data = {
        "name": "Ali", "contact": "@ali_test", "preferred_method": "telegram",
        "description": "Restoranimiz uchun Telegram bot kerak, buyurtma qabul qilsin.",
        "issued": form.initial["issued"], "website": "",
    }
    data.update(extra)
    return data


class PublicPagesTests(CompanyTestCase):
    def test_pages_render(self):
        for name in ("home", "about", "services", "portfolio", "team", "contact", "privacy"):
            self.assertEqual(self.client.get(reverse(f"website:{name}")).status_code, 200, name)
        self.assertEqual(self.client.get("/robots.txt").status_code, 200)
        self.assertEqual(self.client.get("/sitemap.xml").status_code, 200)

    def test_hero_has_html_content_and_3d_stage(self):
        r = self.client.get(reverse("website:home"))
        self.assertContains(r, "<h1")
        self.assertContains(r, "Loyiha boshlash")
        self.assertContains(r, "data-hero-stage")
        self.assertContains(r, "hero-poster")  # no-WebGL fallback

    def test_only_published_content_is_public(self):
        draft = PortfolioProject.objects.create(title="Maxfiy loyiha", summary="x")
        archived = PortfolioProject.objects.create(title="Eski loyiha", summary="x", status=PublicationStatus.ARCHIVED)
        live = PortfolioProject.objects.create(title="Ochiq loyiha", summary="x", status=PublicationStatus.PUBLISHED)
        r = self.client.get(reverse("website:portfolio"))
        self.assertContains(r, "Ochiq loyiha")
        self.assertNotContains(r, "Maxfiy loyiha")
        self.assertNotContains(r, "Eski loyiha")
        self.assertEqual(self.client.get(draft.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(archived.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(live.get_absolute_url()).status_code, 200)
        draft_service = Service.objects.create(title="Yashirin xizmat", summary="x")
        self.assertNotContains(self.client.get(reverse("website:services")), "Yashirin xizmat")
        self.assertEqual(self.client.get(draft_service.get_absolute_url()).status_code, 404)

    def test_draft_preview_only_for_cms_editors(self):
        draft = PortfolioProject.objects.create(title="Qoralama", summary="x")
        url = draft.get_absolute_url() + "?preview=1"
        self.assertEqual(self.client.get(url).status_code, 404)
        self.login(self.dev)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.login(self.ceo)
        self.assertContains(self.client.get(url), "Oldindan ko‘rish")

    def test_team_page_shows_only_public_fields(self):
        self.dev.phone = "+998 99 111 22 33"
        self.dev.save()
        TeamMember.objects.create(user=self.dev, name="Dev Public", public_title="Backend", status=PublicationStatus.PUBLISHED)
        r = self.client.get(reverse("website:team"))
        self.assertContains(r, "Dev Public")
        self.assertNotContains(r, "+998 99 111 22 33")
        self.assertNotContains(r, "@" + self.dev.username)

    def test_management_requires_login(self):
        r = self.client.get(reverse("enterprise:overview"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("accounts:login"), r["Location"])


class InquiryFormTests(CompanyTestCase):
    def setUp(self):
        cache.clear()

    def form(self):
        return self.client.get(reverse("website:contact")).context["form"]

    def test_valid_submission_is_saved(self):
        f = self.form()
        with mock.patch("apps.website.forms.time.time", return_value=time.time() + 10):
            r = self.client.post(reverse("website:contact"), payload(f))
        self.assertRedirects(r, reverse("website:contact_done"))
        self.assertTrue(Inquiry.objects.filter(contact="@ali_test", stage="new").exists())

    def test_validation_errors(self):
        f = self.form()
        with mock.patch("apps.website.forms.time.time", return_value=time.time() + 10):
            r = self.client.post(reverse("website:contact"), payload(f, description="qisqa", contact=""))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Inquiry.objects.exists())
        self.assertContains(r, "kamida 20 belgi")

    def test_honeypot_and_too_fast_submissions_are_dropped(self):
        f = self.form()
        with mock.patch("apps.website.forms.time.time", return_value=time.time() + 10):
            self.client.post(reverse("website:contact"), payload(f, website="http://spam"))
        self.client.post(reverse("website:contact"), payload(f))  # submitted instantly
        self.client.post(reverse("website:contact"), payload(f, issued="tampered"))
        self.assertFalse(Inquiry.objects.exists())

    def test_rate_limit(self):
        f = self.form()
        with mock.patch("apps.website.forms.time.time", return_value=time.time() + 10):
            for i in range(6):
                self.client.post(reverse("website:contact"), payload(f, contact=f"@user{i}"))
        self.assertEqual(Inquiry.objects.count(), 5)
