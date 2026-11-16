from django.urls import reverse

from apps.core.testing import CompanyTestCase
from apps.crm.models import Task

PAGES = [
    "profile", "employees", "employee_create", "roles", "role_create", "department_create",
    "projects", "project_board", "calendar", "workload", "project_create", "tasks", "task_create",
    "clients", "client_create", "inquiries", "cms", "cms_site", "announcements", "notifications",
    "settings", "audit",
]


class PageRenderTests(CompanyTestCase):
    """Rahbar uchun CRM'ning har bir sahifasi xatosiz ochiladi (shablon sintaksisi ham tekshiriladi)."""

    def test_every_page_renders_for_the_founder(self):
        self.login(self.founder)
        task = Task.objects.create(project=self.project, title="Sinov", assignee=self.dev, created_by=self.founder)
        urls = [reverse(f"crm:{name}") for name in PAGES] + [
            reverse('enterprise:overview'),
            reverse("crm:project_detail", args=[self.project.pk]),
            reverse("crm:project_task_board", args=[self.project.pk]),
            reverse("crm:task_detail", args=[task.pk]),
            reverse("crm:employee_detail", args=[self.dev.pk]),
            reverse("crm:calendar") + "?meniki=1",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
