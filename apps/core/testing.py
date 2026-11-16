"""Shared fixtures for the test suite."""

import os
import shutil
import tempfile

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.accounts.models import Department, Role, User
from apps.crm.models import Project

PASSWORD = "Test-Password-2026!"

# Haqiqiy tizimda har bir xodimning huquqlari shaxsan belgilanadi (accounts 0008). Testlar esa tayyor
# huquq to'plamlari bilan yozilgan, shuning uchun ular faqat test bazasida shu nomlar bilan yaratiladi.
_EXEC = ["finance.view", "finance.manage", "finance.approve", "finance.distribute", "archive.manage", "schedule.manage",
         "performance.view", "performance.manage", "dashboard.customize", "dashboard.executive", "employees.view"]
TEST_ROLES = {
    "Hammuassis": {"rank": 10, "dashboard": "cofounder", "capabilities": _EXEC + [
        "projects.approve", "projects.budget", "tasks.review", "clients.view", "inquiries.manage", "audit.view",
        "cms.edit", "announcements.manage"]},
    "Bosh direktor": {"rank": 20, "dashboard": "management", "capabilities": _EXEC + [
        "employees.manage", "projects.view_all", "projects.create", "projects.edit", "projects.assign", "projects.approve",
        "projects.archive", "projects.budget", "tasks.review", "clients.view", "clients.manage", "inquiries.manage",
        "cms.edit", "cms.publish", "announcements.manage"]},
    "Jamoa rahbari": {"rank": 40, "dashboard": "management", "scope": "department", "capabilities": [
        "employees.view", "projects.view_all", "projects.create", "projects.edit", "projects.assign", "tasks.review"]},
    "Xodim": {"rank": 60, "dashboard": "employee", "capabilities": []},
}


def ensure_test_roles():
    for name, spec in TEST_ROLES.items():
        Role.objects.get_or_create(name=name, defaults=spec)


class CompanyTestCase(TestCase):
    """Default roles + a small company: founder, CEO, team lead, two employees, an outsider."""

    @classmethod
    def setUpClass(cls):
        # Uploaded test files go to a throwaway directory, never the real private_media.
        cls._private_media = tempfile.mkdtemp(prefix="ssb-test-private-")
        cls._private_media_override = override_settings(PRIVATE_MEDIA_ROOT=cls._private_media)
        cls._private_media_override.enable()
        try:
            super().setUpClass()
        except Exception:
            cls._private_media_override.disable()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            super().tearDownClass()
        finally:
            cls._private_media_override.disable()
            shutil.rmtree(cls._private_media, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        os.environ["SSB_FOUNDER_PASSWORD"] = PASSWORD
        call_command("bootstrap_company", username="founder", no_input=True, stdout=open(os.devnull, "w"))
        ensure_test_roles()
        cls.founder = User.objects.get(username="founder")
        cls.backend = Department.objects.get(name="Ichki qism")
        cls.frontend = Department.objects.get(name="Tashqi qism")
        cls.ceo = cls.make_user("ceo", "Bosh direktor")
        cls.cofounder = cls.make_user("cofounder", "Hammuassis")
        cls.lead = cls.make_user("lead", "Jamoa rahbari", cls.backend)
        cls.dev = cls.make_user("dev", "Xodim", cls.backend)
        cls.designer = cls.make_user("designer", "Xodim", cls.frontend)
        cls.outsider = cls.make_user("outsider", "Xodim", cls.frontend)
        cls.project = Project.objects.create(
            name="Test loyiha", manager=cls.lead, department=cls.backend, status=Project.Status.IN_PROGRESS, created_by=cls.founder,
        )
        cls.project.members.set([cls.dev, cls.designer])

    @classmethod
    def make_user(cls, username, role, department=None):
        u = User(username=username, first_name=username.title(), role=Role.objects.get(name=role), department=department)
        u.set_password(PASSWORD)
        u.save()
        return u

    def login(self, user):
        self.client.force_login(user)


def unlocked_archive_request(user, code="temporary-archive-code"):
    """A request whose session already passed the company archive code (for setting up fixtures)."""
    from django.contrib.sessions.backends.db import SessionStore
    from django.test import RequestFactory

    from apps.enterprise.archive_access import grant_access
    from apps.enterprise.models import ArchiveAccess

    policy = ArchiveAccess.load()
    if not policy.access_hash:
        from apps.enterprise.archive_access import set_archive_code

        owner = User.objects.filter(role__is_owner=True, is_active=True).first()
        policy = set_archive_code(owner, code)
    request = RequestFactory().post("/")
    request.user = user
    request.session = SessionStore()
    grant_access(request, policy)
    return request
