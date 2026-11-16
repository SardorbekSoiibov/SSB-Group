import os

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.core.models import DEFAULT_ACCENT, WorkspaceSettings

PASSWORD = "Test-Password-2026!"


class PanelAccentTests(TestCase):
    """Boshqaruv paneli rangi kompaniya bo'yicha bitta; faqat direktor (Asoschi) o'zgartiradi."""

    url = reverse("crm:settings_accent")

    @classmethod
    def setUpTestData(cls):
        os.environ["SSB_FOUNDER_PASSWORD"] = PASSWORD
        call_command("bootstrap_company", username="founder", no_input=True, stdout=open(os.devnull, "w"))
        cls.founder = User.objects.get(username="founder")
        everything = ["settings.manage", "employees.manage", "roles.manage", "dashboard.executive"]
        cls.ceo = User.objects.create_user("ceo", password=PASSWORD)
        cls.ceo.set_capabilities(everything)
        cls.cofounder = User.objects.create_user("cofounder", password=PASSWORD)
        cls.cofounder.set_capabilities(everything)
        cls.lead = User.objects.create_user("lead", password=PASSWORD)
        cls.lead.set_capabilities(["projects.own"])
        cls.dev = User.objects.create_user("dev", password=PASSWORD)
        cls.dev.set_capabilities([])

    def login(self, user):
        self.client.force_login(user)

    def test_default_is_ios_blue_for_everyone(self):
        self.assertEqual(WorkspaceSettings.load().accent_color, DEFAULT_ACCENT)
        self.login(self.dev)
        page = self.client.get(reverse("enterprise:overview"))
        self.assertContains(page, "--accent-custom:#007aff")
        self.assertNotContains(page, "data-accent-url")

    def test_owner_changes_colour_for_whole_company(self):
        self.login(self.founder)
        self.assertContains(self.client.get(reverse("enterprise:overview")), "data-accent-url")
        response = self.client.post(self.url, {"accent": "#34C759"}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["accent"], "#34c759")
        self.assertEqual(WorkspaceSettings.load().accent_color, "#34c759")
        self.assertTrue(AuditEvent.objects.filter(action="settings.accent", actor=self.founder).exists())
        # Boshqa xodim ham shu rangni ko'radi.
        self.login(self.dev)
        self.assertContains(self.client.get(reverse("enterprise:overview")), "--accent-custom:#34c759")

    def test_nobody_else_can_change_colour(self):
        for user in (self.ceo, self.cofounder, self.lead, self.dev):
            self.login(user)
            response = self.client.post(self.url, {"accent": "#ff3b30"}, HTTP_ACCEPT="application/json")
            self.assertEqual(response.status_code, 403, user.username)
        self.assertEqual(WorkspaceSettings.load().accent_color, DEFAULT_ACCENT)
        self.assertFalse(AuditEvent.objects.filter(action="settings.accent").exists())

    def test_invalid_colour_is_rejected(self):
        self.login(self.founder)
        for value in ("", "red", "#12345", "#gggggg", "#1234567", "url(x)"):
            response = self.client.post(self.url, {"accent": value}, HTTP_ACCEPT="application/json")
            self.assertEqual(response.status_code, 400, value)
        self.assertEqual(WorkspaceSettings.load().accent_color, DEFAULT_ACCENT)

    def test_get_is_not_allowed_and_guest_is_redirected(self):
        self.login(self.founder)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.post(self.url, {"accent": "#ff3b30"}).status_code, 302)
        self.assertEqual(WorkspaceSettings.load().accent_color, DEFAULT_ACCENT)
