"""Task and project assignment, walked through the real pages the way Founder and employees use them."""
from datetime import timedelta
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.audit.models import AuditEvent
from apps.core.testing import PASSWORD, CompanyTestCase
from apps.crm.models import (
    Attachment, Project, ProjectAssignment, ProjectComment, ProjectFile, Task, TaskAssignment, TaskComment, TaskEvent, TaskReview,
)
from apps.enterprise.erasure import erase_preview
from apps.notifications.models import Notification

S = Task.Status


def picture(name="muqova.png"):
    buffer = BytesIO()
    Image.new("RGB", (40, 30), "#0071e3").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class WorkspaceCase(CompanyTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.team = [cls.make_user(f"xodim{i}", "Xodim", cls.frontend) for i in range(1, 6)]
        cls.stranger = cls.make_user("begona", "Xodim", cls.backend)

    def post_task(self, title, assignee, project=None, **extra):
        data = {"project": (project or self.project).pk, "title": title, "assignee": assignee.pk, "priority": "high",
                "description": f"{title} bo'yicha ko'rsatma", **extra}
        response = self.client.post(reverse("crm:task_create"), data)
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["form"].errors)
        return Task.objects.get(title=title)

    def start(self, task, person):
        self.login(person)
        self.client.post(reverse("crm:task_transition", args=[task.pk]), {"to": "accepted"})
        self.client.post(reverse("crm:task_transition", args=[task.pk]), {"to": "in_progress"})
        task.refresh_from_db()

    def submit(self, task, note="Tayyor", files=None):
        self.client.post(reverse("crm:task_submit", args=[task.pk]), {"note": note, **({"files": files} if files else {})})
        task.refresh_from_db()

    def review(self, task, decision, comment=""):
        response = self.client.post(reverse("crm:task_review", args=[task.pk]), {"decision": decision, "comment": comment})
        task.refresh_from_db()
        return response


class FullScenarioTests(WorkspaceCase):
    """The fifteen acceptance scenarios, in order, on one project."""

    def test_project_from_creation_to_reviewed_work(self):
        roles = ["Frontend", "Backend", "UI/UX dizayn", "Marketing", "Test qilish"]
        # 1-3. Founder creates the project, five people, a responsibility each.
        self.login(self.founder)
        data = {"name": "SSB Group sayti", "description": "Korporativ sayt", "objectives": "Mijozlarni ko'paytirish", "priority": "high",
                "manager": self.lead.pk, "members": [p.pk for p in self.team], "currency": "USD", "cover": picture()}
        data.update({f"responsibility_{p.pk}": role for p, role in zip(self.team, roles)})
        self.client.post(reverse("crm:project_create"), data)
        project = Project.objects.get(name="SSB Group sayti")
        self.assertEqual(project.status, Project.Status.NEW)
        self.assertEqual(project.members.count(), 5)
        self.assertEqual(dict(project.assignments.exclude(user=self.lead).values_list("user", "responsibility")),
                         {p.pk: role for p, role in zip(self.team, roles)})
        self.assertEqual(Notification.objects.filter(kind="project_status", recipient__in=self.team).count(), 5)

        # 4. Individual tasks.
        tasks = [self.post_task(f"Ish {i}", person, project, deadline=str(timezone.localdate() + timedelta(days=5))) for i, person in enumerate(self.team, 1)]
        self.assertTrue(all(task.status == S.ASSIGNED and task.assigned_at for task in tasks))
        self.assertEqual(Notification.objects.filter(kind="task_assigned", recipient__in=self.team).count(), 5)

        for person, own in zip(self.team, tasks):
            self.login(person)
            # 5. Only their own task in the workspace.
            page = self.client.get(reverse("crm:tasks"))
            self.assertEqual([task.pk for task in page.context["page"]], [own.pk])
            # 6. The project with their own responsibility in Loyihalarim.
            cards = self.client.get(reverse("crm:projects"))
            self.assertContains(cards, "SSB Group sayti")
            self.assertEqual(cards.context["page"][0].my_role, roles[self.team.index(person)])

        # 7. Reads instructions.
        first, second = tasks[0], tasks[1]
        self.login(self.team[0])
        self.assertContains(self.client.get(first.get_absolute_url()), "Ish 1 bo&#x27;yicha ko&#x27;rsatma")

        # 8-9. Uploads work and submits it.
        self.start(first, self.team[0])
        self.assertEqual(first.status, S.IN_PROGRESS)
        self.submit(first, "Sahifalar tayyor", [SimpleUploadedFile("natija.pdf", b"%PDF-1.4 ish")])
        self.assertEqual(first.status, S.SUBMITTED)
        self.assertTrue(first.attachments.filter(is_deliverable=True, original_name="natija.pdf").exists())
        self.assertTrue(Notification.objects.filter(recipient=self.lead, kind="submitted").exists())

        # 10. Founder accepts.
        self.login(self.founder)
        self.review(first, "approved", "Yaxshi ish")
        self.assertEqual(first.status, S.APPROVED)
        self.assertEqual(first.get_status_display(), "Bajarildi")
        self.assertEqual(first.shown_progress, 100)

        # 13. Progress follows accepted work only.
        self.assertEqual(project.progress(), 20)

        # 11. Another task goes back, and a rejection needs a reason.
        self.start(second, self.team[1])
        self.submit(second)
        self.login(self.founder)
        self.review(second, "changes_requested", "")
        self.assertEqual(second.status, S.SUBMITTED)
        self.review(second, "changes_requested", "Xatolar bor")
        self.assertEqual(second.status, S.CHANGES_REQUESTED)
        self.assertEqual(second.get_status_display(), "Qayta ishlash kerak")

        # 12. Employee sees the reason, corrects and resubmits.
        self.login(self.team[1])
        self.assertContains(self.client.get(second.get_absolute_url()), "Xatolar bor")
        self.submit(second, "Tuzatildi")
        self.assertEqual(second.status, S.SUBMITTED)
        self.login(self.founder)
        self.review(second, "approved")
        self.assertEqual(project.progress(), 40)

        # 14. Everyone heard about what concerned them.
        self.assertEqual(Notification.objects.filter(recipient=self.team[0], kind="reviewed").count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.team[1], kind="reviewed").count(), 2)
        self.login(self.team[1])
        self.assertGreater(self.client.get(reverse("crm:tasks")).context["unread_count"], 0)

        # 15. Nothing is reachable for someone outside the project.
        attachment = first.attachments.get()
        self.login(self.stranger)
        for url in [project.get_absolute_url(), first.get_absolute_url(), reverse("crm:project_cover", args=[project.pk]),
                    reverse("crm:attachment_download", args=[attachment.pk])]:
            self.assertEqual(self.client.get(url).status_code, 403, url)
        self.assertEqual(self.client.post(reverse("crm:project_comment", args=[project.pk]), {"body": "Salom"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("crm:task_comment", args=[first.pk]), {"body": "Salom"}).status_code, 403)
        self.assertNotContains(self.client.get(reverse("crm:projects")), "SSB Group sayti")
        self.assertEqual(len(self.client.get(reverse("crm:tasks")).context["page"]), 0)

        # All status changes were recorded.
        self.assertEqual(list(second.events.exclude(from_status="").order_by("created_at", "pk").values_list("to_status", flat=True)),
                         ["accepted", "in_progress", "submitted", "changes_requested", "submitted", "approved"])


class MultipleAssigneeTests(WorkspaceCase):
    def shared_task(self):
        self.login(self.founder)
        people = self.team[:2]
        return self.post_task("Birgalikdagi ish", self.dev, collaborators=[p.pk for p in people],
                              **{f"responsibility_{people[0].pk}": "Dizayn", f"responsibility_{people[1].pk}": "Matn"})

    def test_founder_gives_one_task_to_several_people_with_their_own_parts(self):
        task = self.shared_task()
        self.assertEqual(Task.objects.filter(title="Birgalikdagi ish").count(), 1)
        self.assertEqual(sorted(task.assignments.values_list("responsibility", flat=True)), ["Dizayn", "Matn"])
        self.assertEqual(Notification.objects.filter(kind="task_assigned", recipient__in=[self.dev, *self.team[:2]]).count(), 3)
        self.login(self.team[0])
        self.assertEqual([t.pk for t in self.client.get(reverse("crm:tasks")).context["page"]], [task.pk])

    def test_outside_people_join_the_team_only_when_founder_assigns_them(self):
        self.shared_task()
        self.assertTrue(self.project.members.filter(pk=self.team[0].pk).exists())
        self.login(self.lead)
        self.client.post(reverse("crm:task_create"), {"project": self.project.pk, "title": "Rad", "assignee": self.stranger.pk, "priority": "low"})
        self.assertFalse(Task.objects.filter(title="Rad").exists())
        self.client.post(reverse("crm:task_create"), {"project": self.project.pk, "title": "Rad", "assignee": self.dev.pk, "collaborators": [self.stranger.pk], "priority": "low"})
        self.assertFalse(Task.objects.filter(title="Rad").exists())

    def test_the_same_person_is_never_assignee_and_co_worker(self):
        self.login(self.founder)
        task = self.post_task("Takror", self.dev, collaborators=[self.dev.pk, self.designer.pk])
        self.assertEqual(list(task.assignments.values_list("user", flat=True)), [self.designer.pk])
        self.assertEqual(TaskAssignment.objects.filter(task=task, user=self.dev).count(), 0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            TaskAssignment.objects.create(task=task, user=self.designer)

    def test_a_shared_task_counts_once_and_each_person_moves_only_their_own_progress(self):
        task = self.shared_task()
        self.start(task, self.dev)
        self.login(self.team[0])
        self.client.post(reverse("crm:task_progress", args=[task.pk]), {"progress": "60"})
        self.login(self.dev)
        self.client.post(reverse("crm:task_progress", args=[task.pk]), {"progress": "40"})
        task.refresh_from_db()
        self.assertEqual(task.progress, 40)
        self.assertEqual(task.assignments.get(user=self.team[0]).progress, 60)
        self.assertEqual(task.assignments.get(user=self.team[1]).progress, 0)
        self.submit(task)
        self.login(self.founder)
        self.review(task, "approved")
        self.assertEqual(self.project.progress(), 100)
        self.assertEqual(Project.objects.with_progress().get(pk=self.project.pk).task_total, 1)
        self.assertEqual(Task.objects.filter(assignee=self.team[0]).count(), 0, "a co-worker is not credited with the task")

    def test_only_the_responsible_person_submits(self):
        task = self.shared_task()
        self.start(task, self.dev)
        self.login(self.team[0])
        self.submit(task)
        self.assertEqual(task.status, S.IN_PROGRESS)
        self.client.post(reverse("crm:task_attach", args=[task.pk]), {"files": [SimpleUploadedFile("qism.txt", b"x")]})
        self.assertTrue(task.attachments.filter(original_name="qism.txt").exists())

    def test_invalid_progress_is_refused(self):
        task = self.shared_task()
        self.start(task, self.dev)
        for value in ("101", "-1", "abc", ""):
            self.client.post(reverse("crm:task_progress", args=[task.pk]), {"progress": value})
            task.refresh_from_db()
            self.assertEqual(task.progress, 0, value)

    def test_progress_needs_to_be_part_of_the_work(self):
        task = self.shared_task()
        self.start(task, self.dev)
        self.login(self.designer)
        self.client.post(reverse("crm:task_progress", args=[task.pk]), {"progress": "50"})
        task.refresh_from_db()
        self.assertEqual(task.progress, 0)


class ReviewSafetyTests(WorkspaceCase):
    def setUp(self):
        self.login(self.founder)
        self.task = self.post_task("Tekshiruv", self.dev)
        self.start(self.task, self.dev)

    def test_employee_cannot_finish_their_own_task(self):
        self.submit(self.task)
        self.review(self.task, "approved")
        self.assertEqual(self.task.status, S.SUBMITTED)
        self.client.post(reverse("crm:task_transition", args=[self.task.pk]), {"to": "approved"})
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, S.SUBMITTED)

    def test_a_second_submit_or_review_changes_nothing(self):
        self.submit(self.task)
        self.submit(self.task, "Yana bir marta")
        self.assertEqual(self.task.events.filter(to_status=S.SUBMITTED).exclude(from_status="").count(), 1)
        self.login(self.founder)
        self.review(self.task, "approved")
        self.review(self.task, "approved")
        self.assertEqual(TaskReview.objects.filter(task=self.task).count(), 1)

    def test_a_stale_page_cannot_review_work_that_was_already_decided(self):
        from apps.crm import services
        self.submit(self.task)
        stale = Task.objects.select_related("project").get(pk=self.task.pk)
        self.login(self.founder)
        self.review(self.task, "approved")
        with self.assertRaises(services.WorkflowError):
            services.review_task(self.founder, stale, "changes_requested", "Eski sahifa")

    def test_task_page_shows_readable_history(self):
        page = self.client.get(self.task.get_absolute_url())
        self.assertContains(page, "Qabul qilindi → Jarayonda")
        self.assertNotContains(page, ">in_progress<")


class ChangeTests(WorkspaceCase):
    def setUp(self):
        self.login(self.founder)
        self.task = self.post_task("O'zgaruvchan", self.dev, deadline="2030-01-10")

    def edit(self, **changes):
        data = {"title": self.task.title, "assignee": self.task.assignee_id or "", "priority": self.task.priority, "deadline": str(self.task.deadline or ""), **changes}
        response = self.client.post(reverse("crm:task_edit", args=[self.task.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.task.refresh_from_db()

    def test_deadline_and_priority_changes_reach_the_employee_and_history(self):
        self.edit(deadline="2030-02-01", priority="critical")
        note = Notification.objects.filter(recipient=self.dev, title__startswith="Vazifa o'zgardi").get()
        self.assertIn("01.02.2030", note.body)
        self.assertIn("Shoshilinch", note.body)
        self.assertTrue(TaskEvent.objects.filter(task=self.task, note__contains="Ustuvorlik").exists())

    def test_unchanged_edit_notifies_nobody(self):
        self.edit()
        self.assertFalse(Notification.objects.filter(recipient=self.dev, title__startswith="Vazifa o'zgardi").exists())

    def test_reassigning_makes_the_new_person_accept_it_themselves(self):
        self.start(self.task, self.dev)
        self.login(self.founder)
        self.edit(assignee=self.designer.pk)
        self.assertEqual(self.task.status, S.ASSIGNED)
        self.assertEqual(self.task.assignee, self.designer)
        self.assertTrue(Notification.objects.filter(recipient=self.dev, title__startswith="Vazifa boshqa xodimga").exists())
        self.assertTrue(Notification.objects.filter(recipient=self.designer, kind="task_assigned").exists())
        self.assertTrue(AuditEvent.objects.filter(action="task.reassigned").exists())

    def test_quick_actions_work_from_the_management_table(self):
        url = reverse("crm:task_quick", args=[self.task.pk])
        self.client.post(url, {"deadline": "2031-03-03", "assignee": self.team[0].pk})
        self.task.refresh_from_db()
        self.assertEqual(str(self.task.deadline), "2031-03-03")
        self.assertEqual(self.task.assignee, self.team[0])
        self.assertTrue(self.project.members.filter(pk=self.team[0].pk).exists())

    def test_quick_action_refuses_bad_input_and_other_people(self):
        url = reverse("crm:task_quick", args=[self.task.pk])
        self.client.post(url, {"deadline": "2031-13-45"})
        self.task.refresh_from_db()
        self.assertEqual(str(self.task.deadline), "2030-01-10")
        self.login(self.dev)
        self.assertEqual(self.client.post(url, {"deadline": "2031-01-01"}).status_code, 403)
        self.login(self.stranger)
        self.assertEqual(self.client.post(url, {"deadline": "2031-01-01"}).status_code, 403)
        self.task.refresh_from_db()
        self.assertEqual(str(self.task.deadline), "2030-01-10")

    def test_project_status_and_schedule_changes_reach_the_team(self):
        self.client.post(reverse("crm:project_transition", args=[self.project.pk]), {"to": "under_review"})
        self.assertTrue(Notification.objects.filter(recipient=self.dev, kind="project_status", title__contains="Tekshiruvda").exists())
        self.client.post(reverse("crm:project_edit", args=[self.project.pk]), {
            "name": self.project.name, "priority": "critical", "deadline": "2030-05-05", "manager": self.lead.pk,
            "members": [self.dev.pk, self.designer.pk], "currency": "USD"})
        self.assertTrue(Notification.objects.filter(recipient=self.dev, title__startswith="Loyiha o'zgardi").exists())


class WorkspacePageTests(WorkspaceCase):
    def setUp(self):
        today = timezone.localdate()
        make = lambda title, status, **extra: Task.objects.create(project=self.project, title=title, assignee=self.dev, status=status, created_by=self.founder, **extra)
        self.new = make("Yangi ish", S.ASSIGNED, priority="critical")
        self.doing = make("Jarayondagi ish", S.IN_PROGRESS, deadline=today - timedelta(days=2))
        self.review = make("Tekshiruvdagi ish", S.SUBMITTED)
        self.fix = make("Tuzatiladigan ish", S.CHANGES_REQUESTED)
        self.done = make("Bitgan ish", S.APPROVED)
        Task.objects.create(project=self.project, title="Boshqa odam ishi", assignee=self.designer, status=S.ASSIGNED)
        self.login(self.dev)
        self.url = reverse("crm:tasks")

    def titles(self, **params):
        return {task.title for task in self.client.get(self.url, params).context["page"]}

    def test_tabs_show_counts_and_the_right_tasks(self):
        tabs = {item["code"]: item["count"] for item in self.client.get(self.url).context["tabs"]}
        self.assertEqual(tabs, {"hammasi": 5, "yangi": 1, "jarayonda": 1, "tekshiruvda": 1, "qayta": 1, "bajarilgan": 1, "kechikkan": 1})
        self.assertEqual(self.titles(bolim="kechikkan"), {"Jarayondagi ish"})
        self.assertEqual(self.titles(bolim="bajarilgan"), {"Bitgan ish"})
        self.assertNotIn("Boshqa odam ishi", self.titles())

    def test_filters_and_sorting(self):
        self.assertEqual(self.titles(q="tuzatiladigan"), {"Tuzatiladigan ish"})
        self.assertEqual(self.titles(ustuvorlik="critical"), {"Yangi ish"})
        self.assertEqual(self.titles(muddat="otgan"), {"Jarayondagi ish"})
        self.assertEqual(self.titles(holat="submitted"), {"Tekshiruvdagi ish"})
        first = self.client.get(self.url, {"tartib": "ustuvorlik"}).context["page"][0]
        self.assertEqual(first.title, "Yangi ish")

    def test_every_view_renders_for_employee_and_founder(self):
        for person in (self.dev, self.founder):
            self.login(person)
            for view in ("kartalar", "jadval", "kanban"):
                for scope in ("meniki", "barchasi", "tekshiruv"):
                    self.assertEqual(self.client.get(self.url, {"ko": view, "korinish": scope}).status_code, 200)

    def test_kanban_columns_offer_only_allowed_moves(self):
        columns = {column["status"]: column["items"] for column in self.client.get(self.url, {"ko": "kanban"}).context["columns"]}
        self.assertEqual(columns["assigned"][0].actions, ["accepted", "in_progress"])
        self.assertEqual(columns["approved"][0].actions, [])
        response = self.client.post(reverse("crm:task_transition", args=[self.done.pk]), {"to": "in_progress"}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 400)

    def test_plain_employee_is_not_offered_company_views(self):
        self.assertNotContains(self.client.get(self.url), "Barcha ruxsatli ishlar")
        self.assertContains(self.client.get(self.url), "Mening vazifalarim")

    def test_project_page_sections_for_a_team_member(self):
        ProjectAssignment.objects.create(project=self.project, user=self.dev, responsibility="Backend")
        page = self.client.get(self.project.get_absolute_url())
        self.assertContains(page, "Mening mas’uliyatim")
        self.assertContains(page, "Backend")
        self.assertEqual(len(page.context["my_done"]), 1)
        self.assertEqual(len(page.context["my_pending"]), 4)
        self.assertNotContains(page, "Byudjet")

    def test_project_list_only_holds_own_projects_for_an_employee(self):
        Project.objects.create(name="Boshqa loyiha", manager=self.lead)
        cards = self.client.get(reverse("crm:projects"))
        self.assertContains(cards, "Test loyiha")
        self.assertNotContains(cards, "Boshqa loyiha")
        self.assertFalse(cards.context["sees_more"])

    def test_project_team_shows_missing_responsibility(self):
        self.assertContains(self.client.get(self.project.get_absolute_url()), "Mas’uliyat belgilanmagan")


class PickerTests(WorkspaceCase):
    def test_task_form_lists_every_employee_with_position_and_workload_for_founder(self):
        Task.objects.create(project=self.project, title="Ochiq", assignee=self.team[0], status=S.ASSIGNED)
        self.login(self.founder)
        page = self.client.get(reverse("crm:task_create"), {"project": self.project.pk})
        self.assertContains(page, 'data-people-picker="assignee"')
        self.assertContains(page, 'data-people-search')
        self.assertContains(page, "1 ta ochiq ish")
        self.assertContains(page, self.stranger.display_name)

    def test_project_lead_only_sees_the_team(self):
        self.login(self.lead)
        page = self.client.get(reverse("crm:task_create"), {"project": self.project.pk})
        self.assertContains(page, self.dev.display_name)
        self.assertNotContains(page, self.stranger.display_name)

    def test_edit_form_keeps_co_workers_and_their_responsibility(self):
        self.login(self.founder)
        task = self.post_task("Tahrir", self.dev, collaborators=[self.designer.pk], **{f"responsibility_{self.designer.pk}": "Dizayn ishi"})
        page = self.client.get(reverse("crm:task_edit", args=[task.pk]))
        self.assertContains(page, 'value="Dizayn ishi"')
        self.client.post(reverse("crm:task_edit", args=[task.pk]), {"title": "Tahrir", "assignee": self.dev.pk, "priority": "high"})
        self.assertEqual(task.assignments.count(), 0)

    def test_team_form_saves_responsibilities_and_removes_old_ones(self):
        self.login(self.founder)
        self.client.post(reverse("crm:project_members", args=[self.project.pk]), {
            "manager": self.lead.pk, "members": [self.dev.pk], f"responsibility_{self.dev.pk}": "Backend"})
        self.assertEqual(self.project.assignments.get(user=self.dev).responsibility, "Backend")
        self.assertFalse(self.project.assignments.filter(user=self.designer).exists())
        self.assertFalse(self.project.members.filter(pk=self.designer.pk).exists())

    def test_quick_member_add_is_idempotent_and_checked(self):
        url = reverse("crm:project_member_add", args=[self.project.pk])
        self.login(self.dev)
        self.assertEqual(self.client.post(url, {"employee": self.stranger.pk}).status_code, 403)
        self.login(self.founder)
        for _ in range(2):
            self.client.post(url, {"employee": self.stranger.pk, "responsibility": "Tahlil"})
        self.assertEqual(ProjectAssignment.objects.filter(project=self.project, user=self.stranger).count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.stranger, kind="project_status").count(), 1)


class ConversationAndFileTests(WorkspaceCase):
    def setUp(self):
        self.login(self.founder)
        self.task = self.post_task("Muhokama", self.dev)

    def test_task_replies_stay_inside_their_own_task(self):
        url = reverse("crm:task_comment", args=[self.task.pk])
        self.client.post(url, {"body": "Savol bor"})
        parent = TaskComment.objects.get(body="Savol bor")
        self.login(self.dev)
        self.client.post(url, {"body": "Javob", "parent": parent.pk})
        self.assertEqual(TaskComment.objects.get(body="Javob").parent, parent)
        other = Task.objects.create(project=self.project, title="Boshqa")
        self.client.post(reverse("crm:task_comment", args=[other.pk]), {"body": "Begona javob", "parent": parent.pk})
        self.assertIsNone(TaskComment.objects.get(body="Begona javob").parent)
        self.assertContains(self.client.get(self.task.get_absolute_url()), "Javob")

    def test_comment_notifies_co_workers(self):
        self.login(self.founder)
        task = self.post_task("Hamkorlik", self.dev, collaborators=[self.designer.pk])
        self.client.post(reverse("crm:task_comment", args=[task.pk]), {"body": "Diqqat"})
        self.assertTrue(Notification.objects.filter(recipient=self.designer, kind="comment").exists())

    def test_project_comments_and_announcements(self):
        url = reverse("crm:project_comment", args=[self.project.pk])
        self.login(self.dev)
        self.client.post(url, {"body": "Oddiy izoh"})
        self.assertTrue(Notification.objects.filter(recipient=self.lead, kind="comment").exists())
        self.client.post(url, {"body": "Soxta e'lon", "is_announcement": "on"})
        self.assertFalse(ProjectComment.objects.filter(body="Soxta e'lon").exists())
        self.login(self.lead)
        self.client.post(url, {"body": "Muhim e'lon", "is_announcement": "on"})
        self.assertTrue(Notification.objects.filter(recipient=self.dev, kind="announcement").exists())
        self.assertContains(self.client.get(self.project.get_absolute_url()), "Muhim e&#x27;lon")

    def test_project_files_are_private_and_previews_are_images_only(self):
        self.login(self.dev)
        upload = reverse("crm:project_file_upload", args=[self.project.pk])
        self.client.post(upload, {"files": [picture("rasm.png"), SimpleUploadedFile("hujjat.txt", b"matn")]})
        image, document = ProjectFile.objects.get(original_name="rasm.png"), ProjectFile.objects.get(original_name="hujjat.txt")
        url = lambda item: reverse("crm:project_file_download", args=[item.pk])
        self.assertIn("inline", self.client.get(url(image), {"korish": 1})["Content-Disposition"])
        self.assertIn("attachment", self.client.get(url(image))["Content-Disposition"])
        self.assertIn("attachment", self.client.get(url(document), {"korish": 1})["Content-Disposition"])
        self.assertRaises(AttributeError, lambda: image.file.url)
        self.login(self.stranger)
        self.assertEqual(self.client.get(url(image)).status_code, 403)
        self.assertEqual(self.client.post(upload, {"files": [picture()]}).status_code, 403)

    def test_dangerous_uploads_are_refused_everywhere(self):
        bad = lambda: SimpleUploadedFile("virus.exe", b"MZ")
        self.client.post(reverse("crm:project_file_upload", args=[self.project.pk]), {"files": [bad()]})
        self.assertFalse(ProjectFile.objects.exists())
        response = self.client.post(reverse("crm:task_create"), {"project": self.project.pk, "title": "Yomon", "priority": "low", "files": [bad()]})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Task.objects.filter(title="Yomon").exists())

    def test_reference_files_on_a_new_task_are_for_the_employee_to_read(self):
        task = self.post_task("Namuna bilan", self.dev, files=[SimpleUploadedFile("namuna.txt", b"namuna")])
        self.assertFalse(Attachment.objects.get(task=task).is_deliverable)
        self.login(self.dev)
        self.assertContains(self.client.get(task.get_absolute_url()), "namuna.txt")

    def test_cover_must_be_an_image(self):
        response = self.client.post(reverse("crm:project_create"), {"name": "Yomon muqova", "priority": "low", "currency": "USD",
                                                                    "cover": SimpleUploadedFile("muqova.txt", b"matn")})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Project.objects.filter(name="Yomon muqova").exists())


class ManagementCentreTests(WorkspaceCase):
    def setUp(self):
        today = timezone.localdate()
        self.url = reverse("crm:work_control")
        self.late = Task.objects.create(project=self.project, title="Kechikkan", assignee=self.dev, status=S.IN_PROGRESS, deadline=today - timedelta(days=1), created_by=self.founder)
        self.waiting = Task.objects.create(project=self.project, title="Kutayotgan", assignee=self.designer, status=S.SUBMITTED, created_by=self.founder)

    def test_founder_sees_overview_with_quick_actions(self):
        self.login(self.founder)
        page = self.client.get(self.url)
        stats = {item["label"]: item["value"] for item in page.context["stats"]}
        self.assertEqual(stats["Tekshiruv kutmoqda"], 1)
        self.assertEqual(stats["Muddati o'tgan"], 1)
        self.assertContains(page, "Vazifa biriktirish")
        self.assertContains(page, "Xodimni loyihaga qo‘shish")
        self.assertContains(page, "Ko‘rib chiqish")

    def test_filters(self):
        self.login(self.founder)
        titles = lambda **params: [t.title for t in self.client.get(self.url, params).context["page"]]
        self.assertEqual(titles(xodim=self.dev.pk), ["Kechikkan"])
        self.assertEqual(titles(holat="submitted"), ["Kutayotgan"])
        self.assertEqual(titles(muddat="otgan"), ["Kechikkan"])
        self.assertEqual(sorted(titles(menejer=self.lead.pk)), ["Kechikkan", "Kutayotgan"])
        self.assertEqual(titles(loyiha=0), sorted(titles(loyiha=0), key=lambda t: t != "Kechikkan"))

    def test_co_worker_filter_does_not_duplicate_rows(self):
        TaskAssignment.objects.create(task=self.late, user=self.designer)
        self.login(self.founder)
        rows = [t.title for t in self.client.get(self.url, {"xodim": self.designer.pk}).context["page"]]
        self.assertEqual(sorted(rows), ["Kechikkan", "Kutayotgan"])

    def test_plain_employee_has_no_access_and_no_menu_item(self):
        self.login(self.dev)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertNotContains(self.client.get(reverse("crm:tasks")), "Boshqaruv markazi")

    def test_project_manager_only_sees_their_own_work(self):
        other = Project.objects.create(name="Begona loyiha", manager=self.ceo, department=self.frontend)
        Task.objects.create(project=other, title="Begona vazifa", status=S.ASSIGNED)
        self.login(self.lead)
        titles = [t.title for t in self.client.get(self.url).context["page"]]
        self.assertIn("Kechikkan", titles)
        self.assertNotIn("Begona vazifa", titles)


class RecordsAndErasureTests(WorkspaceCase):
    def test_tasks_created_before_this_feature_keep_working(self):
        old = Task.objects.create(project=self.project, title="Eski ish", assignee=self.dev, status=S.ASSIGNED)
        self.login(self.dev)
        self.assertContains(self.client.get(old.get_absolute_url()), "Eski ish")
        self.client.post(reverse("crm:task_transition", args=[old.pk]), {"to": "in_progress"})
        old.refresh_from_db()
        self.assertEqual(old.status, S.IN_PROGRESS)

    def test_erasing_an_employee_clears_their_new_records(self):
        self.login(self.founder)
        task = self.post_task("Oxirgi", self.team[0], collaborators=[self.team[1].pk])
        ProjectComment.objects.create(project=self.project, author=self.team[1], body="Mening izohim")
        pk = self.team[1].pk
        self.assertTrue(any("loyiha" in row for row in erase_preview(self.team[1])))
        self.client.post(reverse("crm:employee_erase", args=[pk]), {"confirm_password": PASSWORD})
        self.assertFalse(TaskAssignment.objects.filter(user_id=pk).exists())
        self.assertFalse(ProjectAssignment.objects.filter(user_id=pk).exists())
        self.assertFalse(ProjectComment.objects.filter(author_id=pk).exists())
        self.assertTrue(Task.objects.filter(pk=task.pk).exists())

    def test_erasing_a_project_also_removes_its_files(self):
        self.login(self.founder)
        self.client.post(reverse("crm:project_file_upload", args=[self.project.pk]), {"files": [picture()]})
        item = ProjectFile.objects.get()
        storage, name = item.file.storage, item.file.name
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("crm:project_erase", args=[self.project.pk]), {"confirm_password": PASSWORD})
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())
        self.assertFalse(storage.exists(name))
