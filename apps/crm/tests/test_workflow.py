from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.core.models import WorkspaceSettings
from apps.core.testing import CompanyTestCase
from apps.crm.models import Attachment, Inquiry, Project, Task
from apps.notifications.models import Notification
from apps.website.models import PortfolioProject, PublicationStatus, Service

S = Task.Status


class ProjectTests(CompanyTestCase):
    def test_ceo_creates_project_and_team_is_notified(self):
        self.login(self.ceo)
        r = self.client.post(reverse("crm:project_create"), {
            "name": "Yangi CRM", "priority": "high", "manager": self.lead.pk, "members": [self.dev.pk], "currency": "USD",
        })
        project = Project.objects.get(name="Yangi CRM")
        self.assertRedirects(r, project.get_absolute_url())
        self.assertTrue(project.code.startswith("SSB-"))
        self.assertTrue(Notification.objects.filter(recipient=self.dev, kind="project_status").exists())

    def test_employee_cannot_create_project(self):
        self.login(self.dev)
        self.assertEqual(self.client.get(reverse("crm:project_create")).status_code, 403)

    def test_outsider_cannot_see_project_or_tasks(self):
        task = Task.objects.create(project=self.project, title="Maxfiy", assignee=self.dev, status=S.ASSIGNED)
        self.login(self.outsider)
        self.assertEqual(self.client.get(self.project.get_absolute_url()).status_code, 403)
        self.assertEqual(self.client.get(task.get_absolute_url()).status_code, 403)
        self.assertNotContains(self.client.get(reverse("crm:projects")), "Test loyiha")

    def test_department_scoped_lead_sees_only_department(self):
        other = Project.objects.create(name="Frontend loyiha", department=self.frontend, manager=self.designer)
        self.login(self.lead)
        self.assertEqual(self.client.get(other.get_absolute_url()).status_code, 403)
        self.assertEqual(self.client.get(self.project.get_absolute_url()).status_code, 200)

    def test_start_requires_approval(self):
        p = Project.objects.create(name="Reja", manager=self.lead, department=self.backend)
        self.login(self.lead)
        self.client.post(reverse("crm:project_transition", args=[p.pk]), {"to": "in_progress"})
        p.refresh_from_db()
        self.assertEqual(p.status, "planning")
        self.client.post(reverse("crm:project_transition", args=[p.pk]), {"to": "awaiting_approval"})
        p.refresh_from_db()
        self.assertEqual(p.status, "awaiting_approval")
        self.client.post(reverse("crm:project_transition", args=[p.pk]), {"to": "in_progress"})
        p.refresh_from_db()
        self.assertEqual(p.status, "awaiting_approval", "a lead without projects.approve cannot approve")
        self.login(self.ceo)
        self.client.post(reverse("crm:project_transition", args=[p.pk]), {"to": "in_progress"})
        p.refresh_from_db()
        self.assertEqual(p.status, "in_progress")
        self.assertTrue(p.approvals.filter(kind="start", actor=self.ceo).exists())

    def test_cannot_complete_with_open_tasks(self):
        Task.objects.create(project=self.project, title="Ochiq", assignee=self.dev, status=S.IN_PROGRESS)
        self.project.status = Project.Status.UNDER_REVIEW
        self.project.save()
        self.login(self.ceo)
        self.client.post(reverse("crm:project_transition", args=[self.project.pk]), {"to": "completed"})
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, "under_review")


class TaskLifecycleTests(CompanyTestCase):
    def test_invalid_project_selection_returns_form_error(self):
        self.login(self.founder)
        for project_id in ("invalid", "999999999999999999999999999999999999"):
            with self.subTest(project_id=project_id):
                response = self.client.post(reverse("crm:task_create"), {
                    "project": project_id, "title": "Invalid project", "priority": "normal",
                })
                self.assertEqual(response.status_code, 200)
                self.assertIn("project", response.context["form"].errors)
                self.assertFalse(Task.objects.filter(title="Invalid project").exists())

    def test_invalid_initial_project_does_not_crash_task_form(self):
        self.login(self.founder)
        response = self.client.get(reverse("crm:task_create"), {"project": "invalid"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["form"].fields["parent"].queryset.exists())

    def create_task(self, **extra):
        self.login(self.lead)
        data = {"project": self.project.pk, "title": "API yozish", "assignee": self.dev.pk, "priority": "high"}
        data.update(extra)
        self.client.post(reverse("crm:task_create"), data)
        return Task.objects.get(title=data["title"])

    def test_full_lifecycle_with_review(self):
        task = self.create_task()
        self.assertEqual(task.status, S.ASSIGNED)
        self.assertTrue(Notification.objects.filter(recipient=self.dev, kind="task_assigned").exists())

        self.login(self.dev)
        self.client.post(reverse("crm:task_transition", args=[task.pk]), {"to": "in_progress"})
        task.refresh_from_db()
        self.assertEqual(task.status, S.IN_PROGRESS)

        f = SimpleUploadedFile("natija.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        self.client.post(reverse("crm:task_submit", args=[task.pk]), {"note": "Tayyor", "files": [f]})
        task.refresh_from_db()
        self.assertEqual(task.status, S.SUBMITTED, "submission must not approve the task")
        self.assertTrue(Attachment.objects.filter(task=task, is_deliverable=True).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.lead, kind="submitted").exists())

        # The assignee cannot approve their own work
        self.client.post(reverse("crm:task_review", args=[task.pk]), {"decision": "approved"})
        task.refresh_from_db()
        self.assertEqual(task.status, S.SUBMITTED)

        self.login(self.lead)
        self.client.post(reverse("crm:task_review", args=[task.pk]), {"decision": "changes_requested", "comment": "Testlar yo'q"})
        task.refresh_from_db()
        self.assertEqual(task.status, S.CHANGES_REQUESTED)

        self.login(self.dev)
        self.client.post(reverse("crm:task_transition", args=[task.pk]), {"to": "in_progress"})
        self.client.post(reverse("crm:task_submit", args=[task.pk]), {"note": "Testlar qo'shildi"})
        self.login(self.lead)
        self.client.post(reverse("crm:task_review", args=[task.pk]), {"decision": "approved", "comment": ""})
        task.refresh_from_db()
        self.assertEqual(task.status, S.APPROVED)
        self.assertEqual(task.reviews.count(), 2)
        self.assertEqual(self.project.progress(), 100)

    def test_changes_request_needs_comment(self):
        task = self.create_task()
        task.status = S.SUBMITTED
        task.save()
        self.client.post(reverse("crm:task_review", args=[task.pk]), {"decision": "changes_requested", "comment": ""})
        task.refresh_from_db()
        self.assertEqual(task.status, S.SUBMITTED)

    def test_invalid_transition_rejected(self):
        task = self.create_task()
        self.login(self.dev)
        r = self.client.post(reverse("crm:task_transition", args=[task.pk]), {"to": "approved"}, HTTP_ACCEPT="application/json")
        self.assertEqual(r.status_code, 400)
        task.refresh_from_db()
        self.assertEqual(task.status, S.ASSIGNED)

    def test_other_employee_cannot_change_task(self):
        task = self.create_task()
        self.login(self.designer)  # project member, not the assignee
        self.client.post(reverse("crm:task_transition", args=[task.pk]), {"to": "in_progress"})
        task.refresh_from_db()
        self.assertEqual(task.status, S.ASSIGNED)

    def test_dependency_blocks_start(self):
        first = self.create_task(title="Birinchi")
        second = self.create_task(title="Ikkinchi", depends_on=[first.pk])
        self.login(self.dev)
        self.client.post(reverse("crm:task_transition", args=[second.pk]), {"to": "in_progress"})
        second.refresh_from_db()
        self.assertEqual(second.status, S.ASSIGNED)

    def test_assignee_must_be_on_project_team(self):
        self.login(self.lead)
        self.client.post(reverse("crm:task_create"), {"project": self.project.pk, "title": "Begona", "assignee": self.outsider.pk, "priority": "low"})
        self.assertFalse(Task.objects.filter(title="Begona").exists())

    def test_upload_restrictions(self):
        task = self.create_task()
        self.login(self.dev)
        bad = SimpleUploadedFile("virus.exe", b"MZ", content_type="application/octet-stream")
        self.client.post(reverse("crm:task_attach", args=[task.pk]), {"files": [bad]})
        self.assertFalse(Attachment.objects.filter(task=task).exists())
        ws = WorkspaceSettings.load()
        ws.upload_max_mb = 1
        ws.save()
        big = SimpleUploadedFile("katta.pdf", b"0" * (1024 * 1024 + 10), content_type="application/pdf")
        self.client.post(reverse("crm:task_attach", args=[task.pk]), {"files": [big]})
        self.assertFalse(Attachment.objects.filter(task=task).exists())

    def test_attachments_are_private(self):
        task = self.create_task()
        self.login(self.dev)
        self.client.post(reverse("crm:task_attach", args=[task.pk]), {"files": [SimpleUploadedFile("a.txt", b"maxfiy")]})
        att = Attachment.objects.get(task=task)
        self.assertEqual(self.client.get(reverse("crm:attachment_download", args=[att.pk])).status_code, 200)
        self.login(self.outsider)
        self.assertEqual(self.client.get(reverse("crm:attachment_download", args=[att.pk])).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("crm:attachment_download", args=[att.pk])).status_code, 302)


class InquiryToPortfolioTests(CompanyTestCase):
    def test_end_to_end_workflow(self):
        service = Service.objects.create(title="CRM", summary="CRM tizimlari", status=PublicationStatus.PUBLISHED)
        # 1. client submits the public form
        form = self.client.get(reverse("website:contact")).context["form"]
        import time
        from unittest import mock

        with mock.patch("apps.website.forms.time.time", return_value=time.time() + 10):
            r = self.client.post(reverse("website:contact"), {
                "name": "Mijoz Ismi", "contact": "+998901234567", "preferred_method": "phone", "service": service.pk,
                "description": "Bizga sotuv bo'limi uchun CRM tizimi kerak, 10 ta xodim.", "budget": "",
                "issued": form.initial["issued"], "website": "",
            })
        self.assertRedirects(r, reverse("website:contact_done"))
        inquiry = Inquiry.objects.get(name="Mijoz Ismi")
        # 2. saved and leadership notified
        self.assertTrue(Notification.objects.filter(recipient=self.ceo, kind="inquiry").exists())

        # 3-4. manager reviews and assigns
        self.login(self.ceo)
        self.client.post(inquiry.get_absolute_url(), {"stage": "discussion", "assigned_to": self.lead.pk, "source": "website"})
        inquiry.refresh_from_db()
        self.assertEqual(inquiry.assigned_to, self.lead)

        # 5. converted into a project with the relationship preserved
        r = self.client.post(reverse("crm:inquiry_convert", args=[inquiry.pk]))
        inquiry.refresh_from_db()
        project = inquiry.project
        self.assertEqual(inquiry.stage, Inquiry.Stage.CONVERTED)
        self.assertEqual(project.client, inquiry.client)
        self.assertEqual(project.manager, self.lead)
        self.assertTrue(AuditEvent.objects.filter(action="inquiry.converted").exists())

        # 6-8. team + tasks + approval
        project.members.set([self.dev])
        project.status = Project.Status.IN_PROGRESS
        project.save()
        task = Task.objects.create(project=project, title="Ishlab chiqish", assignee=self.dev, status=S.SUBMITTED, created_by=self.lead)
        self.login(self.lead)
        self.client.post(reverse("crm:task_review", args=[task.pk]), {"decision": "approved"})
        self.client.post(reverse("crm:project_transition", args=[project.pk]), {"to": "under_review"})

        # 9. completion by an approver
        self.login(self.ceo)
        self.client.post(reverse("crm:project_transition", args=[project.pk]), {"to": "completed"})
        project.refresh_from_db()
        self.assertEqual(project.status, Project.Status.COMPLETED)

        # completed internal project is NOT public automatically
        self.assertFalse(PortfolioProject.objects.filter(source_project=project).exists())

        # 10. explicit approval creates a draft, still not public
        self.client.post(reverse("crm:project_to_portfolio", args=[project.pk]))
        entry = PortfolioProject.objects.get(source_project=project)
        self.assertEqual(entry.status, PublicationStatus.DRAFT)
        self.assertEqual(self.client.get(entry.get_absolute_url()).status_code, 404)

        # 11-12. publish → visible on the public site
        self.client.post(reverse("crm:cms_status", args=["portfolio", entry.pk]), {"action": "publish"})
        self.client.logout()
        self.assertContains(self.client.get(reverse("website:portfolio")), entry.title)
        self.assertEqual(self.client.get(entry.get_absolute_url()).status_code, 200)
