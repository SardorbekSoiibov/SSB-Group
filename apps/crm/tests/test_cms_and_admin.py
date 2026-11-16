import io

from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.core.testing import CompanyTestCase
from apps.crm.models import Task
from apps.notifications.models import Notification
from apps.website.models import PortfolioProject, PublicationStatus, Service


class CMSTests(CompanyTestCase):
    def setUp(self):
        self.editor = self.make_user("editor", "Kontent menejeri")

    def test_editor_creates_draft_but_cannot_publish(self):
        self.login(self.editor)
        r = self.client.post(reverse("crm:cms_create", args=["services"]), {"title": "Mobil ilovalar", "summary": "iOS va Android", "icon": "code", "order": 1})
        svc = Service.objects.get(title="Mobil ilovalar")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(svc.status, PublicationStatus.DRAFT)
        self.assertEqual(self.client.post(reverse("crm:cms_status", args=["services", svc.pk]), {"action": "publish"}).status_code, 403)
        svc.refresh_from_db()
        self.assertEqual(svc.status, PublicationStatus.DRAFT)

    def test_publisher_publishes_and_audit_is_written(self):
        svc = Service.objects.create(title="Botlar", summary="Telegram")
        self.login(self.ceo)
        self.client.post(reverse("crm:cms_status", args=["services", svc.pk]), {"action": "publish"})
        svc.refresh_from_db()
        self.assertTrue(svc.is_published)
        self.assertIsNotNone(svc.published_at)
        self.assertTrue(AuditEvent.objects.filter(action="cms.publish", target_id=str(svc.pk)).exists())
        self.assertContains(self.client.get(reverse("website:services")), "Botlar")

    def test_editor_cannot_change_published_content(self):
        p = PortfolioProject.objects.create(title="Ochiq", summary="x", status=PublicationStatus.PUBLISHED)
        self.login(self.editor)
        r = self.client.post(reverse("crm:cms_edit", args=["portfolio", p.pk]), {"title": "Buzilgan", "summary": "x"})
        self.assertEqual(r.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.title, "Ochiq")

    def test_site_settings_change_shows_on_site(self):
        self.login(self.ceo)
        self.client.get(reverse("crm:cms_site"))
        from apps.website.models import SiteSettings

        data = {f.name: getattr(SiteSettings.load(), f.name) or "" for f in SiteSettings._meta.fields if f.name not in ("id", "og_image")}
        data["hero_title"] = "Yangi sarlavha"
        self.client.post(reverse("crm:cms_site"), data)
        self.assertContains(self.client.get("/"), "Yangi sarlavha")

    def test_employee_has_no_cms_access(self):
        self.login(self.dev)
        self.assertEqual(self.client.get(reverse("crm:cms")).status_code, 403)


class AuditTests(CompanyTestCase):
    def test_audit_records_are_immutable(self):
        e = AuditEvent.objects.create(action="x", target_type="t")
        with self.assertRaises(RuntimeError):
            e.action = "y"
            e.save()
        with self.assertRaises(RuntimeError):
            e.delete()

    def test_audit_never_contains_passwords(self):
        self.login(self.dev)
        self.client.post(reverse("accounts:password_change"), {
            "old_password": "Test-Password-2026!", "new_password1": "Boshqa-parol-2026!", "new_password2": "Boshqa-parol-2026!",
        })
        for e in AuditEvent.objects.all():
            self.assertNotIn("Boshqa-parol-2026!", str(e.changes))

    def test_only_audit_viewers_see_log(self):
        self.login(self.ceo)
        self.assertEqual(self.client.get(reverse("crm:audit")).status_code, 403)
        self.login(self.founder)
        self.assertEqual(self.client.get(reverse("crm:audit")).status_code, 200)


class NotificationTests(CompanyTestCase):
    def test_reminders_are_not_duplicated(self):
        from datetime import timedelta

        from django.utils import timezone

        Task.objects.create(project=self.project, title="Ertaga", assignee=self.dev, status="assigned",
                            deadline=timezone.localdate() + timedelta(days=1))
        Task.objects.create(project=self.project, title="Kechikdi", assignee=self.dev, status="in_progress",
                            deadline=timezone.localdate() - timedelta(days=1))
        call_command("send_deadline_reminders", stdout=io.StringIO())
        call_command("send_deadline_reminders", stdout=io.StringIO())
        self.assertEqual(Notification.objects.filter(recipient=self.dev, kind="deadline_soon").count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.dev, kind="overdue").count(), 1)

    def test_open_marks_read_and_only_owner_can_open(self):
        n = Notification.objects.create(recipient=self.dev, kind="announcement", title="Salom", url="/management/")
        self.login(self.designer)
        self.assertEqual(self.client.post(reverse("crm:notification_open", args=[n.pk])).status_code, 404)
        self.login(self.dev)
        self.client.post(reverse("crm:notification_open", args=[n.pk]))
        n.refresh_from_db()
        self.assertIsNotNone(n.read_at)

    def test_muted_kinds_are_skipped(self):
        self.dev.muted_notifications = ["announcement"]
        self.dev.save()
        self.login(self.ceo)
        self.client.post(reverse("crm:announcements"), {"title": "Yig'ilish", "body": "Juma kuni"})
        self.assertFalse(Notification.objects.filter(recipient=self.dev, kind="announcement").exists())
        self.assertTrue(Notification.objects.filter(recipient=self.designer, kind="announcement").exists())


@override_settings(DEBUG=False)
class SeedDemoGuardTests(CompanyTestCase):
    def test_demo_seed_refuses_in_production(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("seed_demo")
