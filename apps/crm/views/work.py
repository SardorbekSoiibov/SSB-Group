"""Projects, tasks, boards, calendar and workload."""

import calendar
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import Department, User
from apps.audit.models import AuditEvent
from apps.audit.services import form_changes, record
from apps.notifications.services import Kind, notify

from .. import policies, services
from ..forms import (
    AttachmentForm, CommentForm, MembersForm, MilestoneForm, ProjectCommentForm, ProjectForm, ReviewForm, SubmitForm, TaskForm,
    active_users, posted_responsibilities,
)
from ..models import (
    PRIORITY_WEIGHT, Attachment, Milestone, Priority, Project, ProjectAssignment, ProjectComment, ProjectFile, Task, TaskComment,
)
from .base import back, deny_unless, int_param, paginate, require_cap

P = Project.Status
S = Task.Status


def int_post(request, name):
    """Integer POST parameter or None (bad input is treated as missing)."""
    try:
        return int(request.POST.get(name, ""))
    except ValueError:
        return None

# ------------------------------------------------------------------ projects


def _project_filters(request, qs):
    g = request.GET
    q = g.get("q", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(client__company__icontains=q) | Q(client__name__icontains=q))
    if g.get("holat"):
        qs = qs.filter(status=g["holat"])
    elif not g.get("arxiv"):
        qs = qs.exclude(status=P.ARCHIVED)
    if g.get("ustuvorlik"):
        qs = qs.filter(priority=g["ustuvorlik"])
    if int_param(request, "bolim"):
        qs = qs.filter(department=int_param(request, "bolim"))
    if int_param(request, "menejer"):
        qs = qs.filter(manager=int_param(request, "menejer"))
    if g.get("muddati_otgan"):
        qs = qs.filter(deadline__lt=timezone.localdate()).exclude(status__in=[P.COMPLETED, P.ARCHIVED])
    if g.get("korinish") == "meniki":
        qs = qs.filter(pk__in=Project.objects.filter(Q(members=request.user) | Q(manager=request.user)).values("pk"))
    return qs


def _filter_context():
    return {
        "statuses": P.choices,
        "priorities": Priority.choices,
        "departments": Department.objects.all(),
        "managers": User.objects.filter(managed_projects__isnull=False).distinct(),
    }


SORTS = {"muddat": "deadline", "-muddat": "-deadline", "nomi": "name", "yangi": "-created_at", "holat": "status"}


@login_required
def project_list(request):
    qs = _project_filters(request, policies.visible_projects(request.user))
    sort = request.GET.get("tartib", "muddat")
    qs = qs.select_related("client", "manager", "department").prefetch_related("members__role").with_progress()
    page = paginate(request, qs.order_by(SORTS.get(sort, "deadline"), "pk"))
    mine = dict(ProjectAssignment.objects.filter(user=request.user, project__in=[p.pk for p in page]).values_list("project", "responsibility"))
    for project in page:
        project.people = project.team()
        project.my_role = "Mas’ul xodim" if project.manager_id == request.user.pk else mine.get(project.pk, "")
        project.is_mine = any(person.pk == request.user.pk for person in project.people)
    return render(request, "boshqaruv/operations/projects/list.html", {
        "page": page, "sort": sort, **_filter_context(),
        "can_create": request.user.has_cap("projects.create"),
        "scope": request.GET.get("korinish", ""),
        "sees_more": policies.visible_projects(request.user).exclude(
            pk__in=Project.objects.filter(Q(members=request.user) | Q(manager=request.user)).values("pk")).exists(),
    })


BOARD_COLUMNS = [P.NEW, P.PLANNING, P.AWAITING_APPROVAL, P.IN_PROGRESS, P.ON_HOLD, P.UNDER_REVIEW, P.COMPLETED]


@login_required
def project_board(request):
    qs = _project_filters(request, policies.visible_projects(request.user)).select_related("manager", "client").with_progress()
    by_status = {s: [] for s in BOARD_COLUMNS}
    for p in qs:
        if p.status in by_status:
            p.actions = services.allowed_project_actions(request.user, p)
            by_status[p.status].append(p)
    descriptions = {
        P.NEW: "Loyiha yaratildi, hali rejalashtirilmagan.",
        P.PLANNING: "Talablar, jamoa va ish rejasi tayyorlanmoqda.",
        P.AWAITING_APPROVAL: "Ishni boshlash uchun rahbar tasdig‘i kerak.",
        P.IN_PROGRESS: "Jamoa loyiha ustida ishlayapti.",
        P.ON_HOLD: "Ish vaqtincha to‘xtatilgan.",
        P.UNDER_REVIEW: "Natija tekshirilmoqda, yakuniy tasdiq kutilmoqda.",
        P.COMPLETED: "Loyiha ishlari yakunlangan.",
    }
    columns = [{"status": s, "label": P(s).label, "items": by_status[s], "description": descriptions[s]} for s in BOARD_COLUMNS]
    return render(request, "boshqaruv/operations/projects/board.html", {
        "columns": columns, "board_total": sum(len(items) for items in by_status.values()),
        "can_create": request.user.has_cap("projects.create"), **_filter_context(),
    })


@login_required
def project_calendar(request):
    try:
        year, month = (int(x) for x in request.GET.get("oy", "").split("-"))
        first = date(year, month, 1)
    except ValueError:
        first = timezone.localdate().replace(day=1)
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    projects = policies.visible_projects(request.user)
    tasks = policies.visible_tasks(request.user).filter(deadline__range=(first, last)).exclude(status=S.CANCELLED)
    if request.GET.get("meniki"):
        tasks = tasks.filter(assignee=request.user)
    events = {}
    for t in tasks.select_related("project", "assignee"):
        events.setdefault(t.deadline, []).append({"kind": "task", "obj": t})
    for p in projects.filter(deadline__range=(first, last)).exclude(status=P.ARCHIVED):
        events.setdefault(p.deadline, []).append({"kind": "project", "obj": p})
    weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(first.year, first.month):
        weeks.append([{"date": d, "in_month": d.month == first.month, "events": events.get(d, [])} for d in week])
    prev_month = (first - timedelta(days=1)).replace(day=1)
    next_month = last + timedelta(days=1)
    return render(request, "boshqaruv/operations/projects/calendar.html", {
        "weeks": weeks, "month": first, "prev": prev_month, "next": next_month, "today": timezone.localdate(),
    })


@login_required
def workload(request):
    today = timezone.localdate()
    tasks = policies.visible_tasks(request.user).filter(status__in=Task.OPEN)
    if int_param(request, "bolim"):
        tasks = tasks.filter(project__department=int_param(request, "bolim"))
    open_ids = tasks.values("pk")
    people = (
        User.objects.filter(status=User.Status.ACTIVE)
        .annotate(
            open_count=Count("tasks", filter=Q(tasks__in=open_ids), distinct=True),
            in_progress=Count("tasks", filter=Q(tasks__in=open_ids, tasks__status=S.IN_PROGRESS), distinct=True),
            review=Count("tasks", filter=Q(tasks__in=open_ids, tasks__status=S.SUBMITTED), distinct=True),
            blocked=Count("tasks", filter=Q(tasks__in=open_ids, tasks__status=S.BLOCKED), distinct=True),
            overdue=Count("tasks", filter=Q(tasks__in=open_ids, tasks__deadline__lt=today), distinct=True),
            urgent=Count("tasks", filter=Q(tasks__in=open_ids, tasks__priority__in=["high", "critical"]), distinct=True),
            due_week=Count("tasks", filter=Q(tasks__in=open_ids, tasks__deadline__range=(today, today + timedelta(days=7))), distinct=True),
        )
        .filter(open_count__gt=0)
        .select_related("department")
        .order_by("-open_count")
    )
    if not (request.user.has_cap("employees.view") or request.user.has_cap("projects.view_all")):
        people = people.filter(pk=request.user.pk)
    rows = list(people)
    peak = max([r.open_count for r in rows] or [1])
    unassigned = tasks.filter(assignee__isnull=True).select_related("project")[:20]
    return render(request, "boshqaruv/operations/projects/workload.html", {
        "rows": rows, "peak": peak, "unassigned": unassigned, "departments": Department.objects.all(),
        "can_create_task": policies.assignable_projects(request.user).exists(),
    })


@require_cap("projects.create")
def project_create(request):
    form = ProjectForm(
        request.POST or None, request.FILES or None, actor=request.user,
        can_assign=request.user.has_cap("projects.assign"), show_budget=policies.can_see_budget(request.user),
        initial={"manager": request.user, "department": request.user.department_id},
    )
    if request.method == "POST" and form.is_valid():
        project = form.save(commit=False)
        project.created_by = request.user
        project.status = P.NEW
        if not request.user.has_cap("projects.assign"):
            project.manager = request.user
        project.save()
        form.save_m2m()
        changes = form_changes(form)
        changes.pop("files", None)
        record(request.user, "project.created", project, changes, request)
        services.sync_team(request.user, project, set(), posted_responsibilities(request.POST), request)
        services.add_project_files(request.user, project, form.cleaned_data["files"], request)
        messages.success(request, f"{project.code} loyihasi yaratildi.")
        return redirect(project)
    return render(request, "boshqaruv/operations/projects/form.html", {"form": form})


def _project_activity(project, limit=25):
    """One readable timeline: comments, files, delivered work and every recorded change."""
    feed = []
    for item in AuditEvent.objects.filter(
        Q(target_type="crm.project", target_id=str(project.pk))
        | Q(target_type="crm.task", target_id__in=[str(i) for i in project.tasks.values_list("pk", flat=True)])
    ).select_related("actor")[:limit]:
        feed.append({"when": item.created_at, "actor": item.actor, "kind": "change", "action": item.action, "detail": item.target_repr})
    for item in ProjectFile.objects.filter(project=project).select_related("uploaded_by")[:limit]:
        feed.append({"when": item.created_at, "actor": item.uploaded_by, "kind": "file", "file": item})
    feed.sort(key=lambda row: row["when"], reverse=True)
    return feed[:limit]


def _get_project(request, pk):
    project = get_object_or_404(Project.objects.select_related("client", "manager", "department", "inquiry"), pk=pk)
    deny_unless(policies.can_view_project(request.user, project))
    return project


@login_required
def project_detail(request, pk):
    project = _get_project(request, pk)
    user = request.user
    tasks = project.tasks.filter(parent__isnull=True).select_related("assignee").prefetch_related("subtasks").order_by(
        "status", "deadline")
    status_filter = request.GET.get("vazifa_holati")
    if status_filter:
        tasks = tasks.filter(status=status_filter)
    deliverables = Attachment.objects.filter(task__project=project, is_deliverable=True).select_related("task", "uploaded_by")[:10]
    can_edit = policies.can_edit_project(user, project)
    can_edit_details = user.has_cap("projects.edit") and can_edit
    from apps.enterprise.erasure import project_erase_preview
    today = timezone.localdate()
    mine = list(policies.my_tasks(user).filter(project=project).exclude(status=S.CANCELLED).select_related("project").order_by("deadline", "pk"))
    responsibilities = dict(project.assignments.values_list("user_id", "responsibility"))
    done_by, total_by = {}, {}
    for assignee, status in project.tasks.exclude(status=S.CANCELLED).filter(parent__isnull=True).values_list("assignee", "status"):
        total_by[assignee] = total_by.get(assignee, 0) + 1
        done_by[assignee] = done_by.get(assignee, 0) + (status == S.APPROVED)
    team = project.team()
    for person in team:
        person.project_role = responsibilities.get(person.pk, "")
        person.is_project_manager = person.pk == project.manager_id
        person.tasks_total, person.tasks_done = total_by.get(person.pk, 0), done_by.get(person.pk, 0)
    can_assign = policies.can_assign(user, project)
    milestones = list(project.milestones.all())
    finance_block = _project_finance(user, project)
    # Tayyorlik ro'yxati: ish boshlanishidan oldin nima to'ldirilgani ko'rinib turadi.
    checklist = [
        {"ok": len(team) > 1 or bool(project.members.exists()), "text": f"Jamoa: {len(team)} nafar", "hint": "Jamoaga xodim qo‘shing"},
        {"ok": bool(milestones), "text": f"Bosqichlar: {len(milestones)} ta", "hint": "Ishni bosqichlarga bo‘ling"},
        {"ok": bool(project.deadline), "text": "Muddat belgilangan" if project.deadline else "Muddat belgilanmagan", "hint": "Tahrirlash orqali muddat qo‘ying"},
    ]
    if finance_block is not None:
        checklist.append({"ok": bool(finance_block["agreement"]), "text": "Moliyaviy kelishuv bor" if finance_block["agreement"] else "Moliyaviy kelishuv yo‘q",
                          "hint": "Ulushlarni belgilash uchun kelishuv kiriting"})
    return render(request, "boshqaruv/operations/projects/detail.html", {
        "control": services.project_control(user, project),
        "days_left": (project.deadline - today).days if project.deadline else None,
        # Yopilgan (yakunlangan/arxiv/bekor) loyihada bosqichlar o'zgartirilmaydi.
        "steps_editable": can_edit and not project.is_closed,
        "checklist": checklist,
        "fin": finance_block,
        "done_count": sum(1 for m in milestones if m.is_done),
        "my_tasks": mine,
        "my_pending": [t for t in mine if t.is_open],
        "my_done": [t for t in mine if t.status == S.APPROVED],
        "my_upcoming": [t for t in mine if t.is_open and t.deadline and today <= t.deadline <= today + timedelta(days=7)],
        "my_role": "Mas’ul xodim" if project.manager_id == user.pk else responsibilities.get(user.pk, ""),
        "on_team": any(person.pk == user.pk for person in team),
        "comments": project.comments.filter(parent__isnull=True).select_related("author__role").prefetch_related("replies__author"),
        "comment_form": ProjectCommentForm(),
        "project_files": project.files.select_related("uploaded_by"),
        "file_form": AttachmentForm(),
        "can_share": policies.can_share_on_project(user, project),
        "can_erase": user.is_owner,
        "erase_items": project_erase_preview(project) if user.is_owner else [],
        "project": project,
        "tasks": tasks,
        "task_statuses": S.choices,
        "status_filter": status_filter,
        "milestones": milestones,
        "team": team,
        "approvals": project.approvals.select_related("actor"),
        "activity": _project_activity(project),
        "deliverables": deliverables,
        "progress": project.progress(),
        "actions": [(a, P(a).label) for a in services.allowed_project_actions(user, project)],
        "blockers": services.completion_blockers(project) if project.status == P.UNDER_REVIEW else [],
        "can_edit": can_edit,
        "can_edit_details": can_edit_details,
        "can_assign": can_assign,
        "can_budget": policies.can_see_budget(user, project),
        "can_portfolio": user.has_cap("cms.publish") and project.status in (P.COMPLETED, P.ARCHIVED),
        "portfolio_entry": getattr(project, "portfolio_entry", None),
        "milestone_form": MilestoneForm(),
        "members_form": MembersForm(instance=project) if can_assign else None,
    })


def _project_finance(user, project):
    """Loyiha moliyasi (faqat moliyani ko'ra oladiganlarga): kelishuv, tushum, foyda va har bir a'zoning ulushi."""
    if not (user.is_owner or user.has_cap("finance.view")):
        return None
    from apps.enterprise import finance
    from apps.enterprise.models import AgreementSnapshot
    agreement = AgreementSnapshot.objects.filter(project=project).first()
    if not agreement:
        return {"agreement": None, "can_distribute": user.has_cap("finance.distribute"), "can_manage": user.has_cap("finance.manage")}
    totals = finance.profitability(project)
    rows = {row["employee"].pk: row for row in finance.project_accounts(agreement.currency) if row["project"] and row["project"].pk == project.pk}
    people = {u.pk: u for u in User.objects.filter(pk__in=[int(s["employee"]) for s in agreement.shares])}
    shares = []
    for employee_id, percent, target in finance.share_targets(agreement):
        row = rows.get(employee_id, {})
        shares.append({"person": people.get(employee_id), "percent": finance.percent_text(percent), "target": target,
                       "earned": row.get("earned", 0), "paid": row.get("paid", 0), "remaining": row.get("remaining", 0)})
    received = totals["client_receipts"]
    # Mijoz shartnomani to'liq to'laganda kompaniyaga qoladigan foyda (ulushlar yakunda to'liq summadan hisoblanadi).
    from decimal import Decimal
    expected_profit = (agreement.amount * agreement.company_percent / 100 - totals["expenses"]).quantize(Decimal("0.01"))
    return {"agreement": agreement, "totals": totals, "shares": shares, "currency": agreement.currency,
            "expected_profit": expected_profit,
            "company_percent": finance.percent_text(agreement.company_percent),
            "received_pct": min(100, round(received * 100 / agreement.amount)) if agreement.amount else 0,
            "can_distribute": user.has_cap("finance.distribute"), "can_manage": user.has_cap("finance.manage"),
            "can_pay": user.is_owner}


@login_required
def project_edit(request, pk):
    project = _get_project(request, pk)
    # Nomi, muddati va jamoasini faqat Asoschi (yoki unga ruxsat berilgan xodim) o'zgartiradi.
    deny_unless(request.user.has_cap("projects.edit") and policies.can_edit_project(request.user, project))
    before = {u.pk for u in project.team()}
    old_cover, old_deadline, old_priority = project.cover.name, project.deadline, project.priority
    form = ProjectForm(
        request.POST or None, request.FILES or None, instance=project, actor=request.user,
        can_assign=policies.can_assign(request.user, project), show_budget=policies.can_see_budget(request.user, project),
    )
    if request.method == "POST" and form.is_valid():
        changes = form_changes(form)
        changes.pop("files", None)
        form.save()
        if changes:
            record(request.user, "project.updated", project, changes, request)
        services.sync_team(request.user, project, before, posted_responsibilities(request.POST), request)
        services.notify_project_schedule(request.user, project, old_deadline, old_priority)
        services.add_project_files(request.user, project, form.cleaned_data["files"], request)
        if old_cover and old_cover != project.cover.name:
            from apps.enterprise.erasure import delete_files_after_commit
            delete_files_after_commit([(project.cover.storage, old_cover)])
        messages.success(request, "Loyiha saqlandi.")
        return redirect(project)
    return render(request, "boshqaruv/operations/projects/form.html", {"form": form, "project": project})


@require_POST
@login_required
def project_transition(request, pk):
    project = _get_project(request, pk)
    try:
        services.transition_project(request.user, project, request.POST.get("to", ""), request.POST.get("comment", ""), request)
    except services.WorkflowError as e:
        if request.headers.get("Accept") == "application/json":
            return JsonResponse({"ok": False, "error": str(e)}, status=400)
        messages.error(request, str(e))
        return back(request, project.get_absolute_url())
    if request.headers.get("Accept") == "application/json":
        return JsonResponse({"ok": True})
    messages.success(request, f"Loyiha holati: {project.get_status_display()}.")
    return back(request, project.get_absolute_url())


@require_POST
@login_required
def project_erase(request, pk):
    """Founder only, after the password step: the project and everything tied to it leave the database."""
    from apps.core.secure_delete import confirm_delete_password
    from apps.enterprise.erasure import erase_project

    project = _get_project(request, pk)
    deny_unless(request.user.is_owner)
    if not confirm_delete_password(request):
        return redirect(project)
    summary = erase_project(request.user, project, request)
    messages.success(request, f"«{summary['name']}» loyihasi bazadan o‘chirildi.")
    return redirect("crm:projects")


@require_POST
@login_required
def project_members(request, pk):
    project = _get_project(request, pk)
    deny_unless(policies.can_assign(request.user, project))
    before = {u.pk for u in project.team()}
    form = MembersForm(request.POST, instance=project)
    if form.is_valid():
        changes = form_changes(form)
        form.save()
        record(request.user, "project.members", project, changes, request)
        services.sync_team(request.user, project, before, posted_responsibilities(request.POST), request)
        messages.success(request, "Jamoa yangilandi.")
    else:
        messages.error(request, "Jamoani saqlab bo'lmadi.")
    return redirect(project)


@require_POST
@login_required
def project_member_add(request, pk):
    project = _get_project(request, pk)
    deny_unless(policies.can_assign(request.user, project))
    person = active_users().filter(pk=int_post(request, "employee") or 0).first()
    if person is None:
        messages.error(request, "Xodimni tanlang.")
        return back(request, project.get_absolute_url())
    try:
        services.add_project_member(request.user, project, person, request.POST.get("responsibility", ""), request)
    except services.WorkflowError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, f"{person.display_name} loyihaga qo'shildi.")
    return back(request, project.get_absolute_url())


def _private_file(field_file, name, inline):
    try:
        handle = field_file.open("rb")
    except FileNotFoundError:
        raise Http404
    response = FileResponse(handle, as_attachment=not inline, filename=name)
    response["Cache-Control"] = "private, max-age=3600"
    return response


@login_required
def project_cover(request, pk):
    project = _get_project(request, pk)
    if not project.cover:
        raise Http404
    return _private_file(project.cover, project.cover.name.rsplit("/", 1)[-1], inline=True)


@require_POST
@login_required
def project_comment(request, pk):
    project = _get_project(request, pk)
    form = ProjectCommentForm(request.POST)
    url = project.get_absolute_url() + "#faoliyat"
    if not form.is_valid():
        messages.error(request, "Izoh bo'sh bo'lishi mumkin emas.")
        return redirect(url)
    parent = ProjectComment.objects.filter(pk=int_post(request, "parent") or 0, project=project).first()
    try:
        services.add_project_comment(request.user, project, form.cleaned_data["body"], parent, form.cleaned_data["is_announcement"])
    except services.WorkflowError as e:
        messages.error(request, str(e))
    return redirect(url)


@require_POST
@login_required
def project_file_upload(request, pk):
    project = _get_project(request, pk)
    deny_unless(policies.can_share_on_project(request.user, project))
    form = AttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        services.add_project_files(request.user, project, form.cleaned_data["files"], request)
        messages.success(request, "Fayl qo'shildi.")
    else:
        for errs in form.errors.values():
            for e in errs:
                messages.error(request, e)
    return redirect(project.get_absolute_url() + "#fayllar")


@login_required
def project_file_download(request, pk):
    item = get_object_or_404(ProjectFile.objects.select_related("project"), pk=pk)
    deny_unless(policies.can_view_project(request.user, item.project))
    return _private_file(item.file, item.original_name, inline=bool(request.GET.get("korish")) and item.is_image)


@require_POST
@login_required
def milestone_add(request, pk):
    project = _get_project(request, pk)
    deny_unless(policies.can_edit_project(request.user, project))
    form = MilestoneForm(request.POST)
    wants_json = request.headers.get("Accept") == "application/json"
    if form.is_valid():
        m = form.save(commit=False)
        m.project = project
        m.order = project.milestones.count()
        m.save()
        record(request.user, "project.updated", project, {"milestone_added": m.title}, request)
        if wants_json:
            return JsonResponse({"ok": True, "id": m.pk, "title": m.title, "progress": project.progress(),
                                 "toggle_url": reverse("crm:milestone_toggle", args=[project.pk, m.pk])})
    else:
        if wants_json:
            return JsonResponse({"ok": False, "error": "Bosqich nomini kiriting."}, status=400)
        messages.error(request, "Bosqich nomini kiriting.")
    return redirect(project.get_absolute_url() + "#bosqichlar")


@require_POST
@login_required
def milestone_toggle(request, pk, mid):
    project = _get_project(request, pk)
    deny_unless(policies.can_edit_project(request.user, project))
    m = get_object_or_404(Milestone, pk=mid, project=project)
    if request.POST.get("delete"):
        from apps.core.secure_delete import confirm_delete_password
        if not confirm_delete_password(request):
            return redirect(project.get_absolute_url() + "#bosqichlar")
        record(request.user, "project.updated", project, {"milestone_removed": m.title}, request)
        m.delete()
    else:
        m.is_done = not m.is_done
        m.save(update_fields=["is_done"])
        record(request.user, "project.updated", project, {"milestone": [m.title, "bajarildi" if m.is_done else "qayta ochildi"]}, request)
        if request.headers.get("Accept") == "application/json":
            done = project.milestones.filter(is_done=True).count()
            return JsonResponse({"ok": True, "done": m.is_done, "progress": project.progress(),
                                 "done_count": done, "total": project.milestones.count()})
    return redirect(project.get_absolute_url() + "#bosqichlar")


@require_POST
@login_required
def project_to_portfolio(request, pk):
    project = _get_project(request, pk)
    try:
        entry = services.approve_for_portfolio(request.user, project, request)
    except services.WorkflowError as e:
        messages.error(request, str(e))
        return redirect(project)
    messages.success(request, "Portfolio uchun qoralama tayyor. Ma'lumotlarni to'ldirib, nashr qiling.")
    return redirect("crm:cms_edit", kind="portfolio", pk=entry.pk)


@login_required
def project_task_board(request, pk):
    project = _get_project(request, pk)
    columns = [S.NEW, S.ASSIGNED, S.ACCEPTED, S.IN_PROGRESS, S.BLOCKED, S.SUBMITTED, S.CHANGES_REQUESTED, S.APPROVED]
    tasks = project.tasks.exclude(status=S.CANCELLED).select_related("assignee")
    by = {c: [] for c in columns}
    for t in tasks:
        t.actions = services.allowed_task_actions(request.user, t)
        by.setdefault(t.status, []).append(t)
    return render(request, "boshqaruv/operations/projects/task_board.html", {
        "project": project,
        "columns": [{"status": c, "label": S(c).label, "items": by[c]} for c in columns],
        "can_assign": policies.can_assign(request.user, project),
    })


# ------------------------------------------------------------------ tasks


TASK_TABS = [
    ("hammasi", "Hammasi"), ("yangi", "Yangi"), ("jarayonda", "Jarayonda"), ("tekshiruvda", "Tekshiruvda"),
    ("qayta", "Qayta ishlash"), ("bajarilgan", "Bajarilgan"), ("kechikkan", "Muddati o'tgan"),
]
TASK_VIEWS = [("kartalar", "Kartalar", "overview"), ("jadval", "Jadval", "task"), ("kanban", "Kanban", "kanban")]
KANBAN_COLUMNS = [S.ASSIGNED, S.ACCEPTED, S.IN_PROGRESS, S.SUBMITTED, S.CHANGES_REQUESTED, S.APPROVED]
KANBAN_LIMIT = 200
DEADLINE_FILTERS = [("bugun", "Bugun"), ("hafta", "7 kun ichida"), ("otgan", "Muddati o'tgan"), ("yoq", "Muddatsiz")]
TASK_SORTS = [("muddat", "Muddat"), ("yangi", "Yangi"), ("ustuvorlik", "Ustuvorlik"), ("holat", "Holat")]


def _tab_rules(today):
    return {
        "hammasi": ~Q(status=S.CANCELLED),
        "yangi": Q(status__in=[S.NEW, S.ASSIGNED]),
        "jarayonda": Q(status__in=[S.ACCEPTED, S.IN_PROGRESS, S.BLOCKED]),
        "tekshiruvda": Q(status=S.SUBMITTED),
        "qayta": Q(status=S.CHANGES_REQUESTED),
        "bajarilgan": Q(status=S.APPROVED),
        "kechikkan": Q(status__in=Task.OPEN, deadline__lt=today),
    }


def _deadline_filter(qs, value, today):
    rules = {
        "bugun": Q(deadline=today), "hafta": Q(deadline__range=(today, today + timedelta(days=7))),
        "otgan": Q(deadline__lt=today, status__in=Task.OPEN), "yoq": Q(deadline__isnull=True),
    }
    return qs.filter(rules[value]) if value in rules else qs


def _sorted_tasks(qs, sort):
    if sort == "ustuvorlik":
        weight = Case(*[When(priority=code, then=Value(-score)) for code, score in PRIORITY_WEIGHT.items()], output_field=IntegerField())
        return qs.annotate(priority_rank=weight).order_by("priority_rank", "deadline", "pk")
    order = {"muddat": ["deadline"], "-muddat": ["-deadline"], "yangi": ["-created_at"], "holat": ["status", "deadline"]}
    return qs.order_by(*order.get(sort, ["deadline"]), "pk")


@login_required
def task_list(request):
    user = request.user
    scope = request.GET.get("korinish", "meniki")
    today = timezone.localdate()
    if scope == "tekshiruv":
        qs = policies.visible_tasks(user).filter(status=S.SUBMITTED)
        qs = qs.filter(pk__in=[t.pk for t in qs.select_related("project") if policies.can_review_task(user, t)])
    elif scope == "barchasi":
        qs = policies.visible_tasks(user)
    elif scope == "men_yaratgan":
        qs = Task.objects.filter(created_by=user)
    else:
        scope = "meniki"
        qs = policies.my_tasks(user)
    g = request.GET
    rules = _tab_rules(today)
    counts = qs.aggregate(**{code: Count("pk", filter=rule) for code, rule in rules.items()})
    tab = g.get("bolim") if g.get("bolim") in rules else "hammasi"
    if g.get("holat"):
        qs = qs.filter(status=g["holat"])
    else:
        qs = qs.filter(rules[tab])
    if g.get("ustuvorlik"):
        qs = qs.filter(priority=g["ustuvorlik"])
    if int_param(request, "loyiha"):
        qs = qs.filter(project=int_param(request, "loyiha"))
    if g.get("muddati_otgan"):
        qs = qs.filter(deadline__lt=today, status__in=Task.OPEN)
    qs = _deadline_filter(qs, g.get("muddat"), today)
    if g.get("q"):
        qs = qs.filter(Q(title__icontains=g["q"]) | Q(description__icontains=g["q"]) | Q(project__name__icontains=g["q"]))
    sort = g.get("tartib", "muddat")
    qs = _sorted_tasks(qs.select_related("project", "assignee"), sort)
    view = g.get("ko") if g.get("ko") in {code for code, _, _ in TASK_VIEWS} else "kartalar"
    params = g.copy()
    params.pop("page", None)
    context = {
        "scope": scope, "tab": tab, "view": view, "sort": sort,
        "tabs": [{"code": code, "label": label, "count": counts[code]} for code, label in TASK_TABS],
        "views": TASK_VIEWS, "sorts": TASK_SORTS, "deadlines": DEADLINE_FILTERS,
        "can_create_task": policies.assignable_projects(user).exists(),
        "can_review_any": user.has_cap("tasks.review") or user.managed_projects.exists(),
        "statuses": S.choices,
        "priorities": Priority.choices,
        "projects": policies.visible_projects(user).exclude(status=P.ARCHIVED),
        "today": today,
    }
    if view == "kanban":
        tasks = list(qs[:KANBAN_LIMIT])
        by = {column: [] for column in KANBAN_COLUMNS}
        for task in tasks:
            task.actions = services.allowed_task_actions(user, task)
            column = {S.NEW: S.ASSIGNED, S.BLOCKED: S.IN_PROGRESS}.get(task.status, task.status)
            if column in by:
                by[column].append(task)
        context["columns"] = [{"status": c, "label": S(c).label, "items": by[c]} for c in KANBAN_COLUMNS]
        context["total"] = len(tasks)
    else:
        context["page"] = paginate(request, qs, 30)
        context["total"] = context["page"].paginator.count
    return render(request, "boshqaruv/operations/tasks/list.html", context)


@login_required
def task_create(request):
    projects = policies.assignable_projects(request.user)
    deny_unless(projects.exists())
    initial = {k: request.GET[k] for k in ("project", "parent") if request.GET.get(k)}
    form = TaskForm(request.POST or None, request.FILES or None, projects=projects, actor=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        task = form.save(commit=False)
        try:
            services.create_task(request.user, task, request, form.cleaned_data["collaborators"],
                                 posted_responsibilities(request.POST), form.cleaned_data["files"])
        except services.WorkflowError as e:
            messages.error(request, str(e))
        else:
            form.save_m2m()
            messages.success(request, "Vazifa yaratildi.")
            return redirect(task)
    return render(request, "boshqaruv/operations/tasks/form.html", {"form": form})


def _get_task(request, pk):
    task = get_object_or_404(Task.objects.select_related("project", "assignee", "created_by", "parent", "milestone"), pk=pk)
    deny_unless(policies.can_view_task(request.user, task))
    return task


@login_required
def task_detail(request, pk):
    task = _get_task(request, pk)
    user = request.user
    can_work = policies.can_work_on_task(user, task)
    can_review = policies.can_review_task(user, task) and task.status == S.SUBMITTED
    assignments = list(task.assignments.select_related("user__role"))
    mine = next((item for item in assignments if item.user_id == user.pk), None)
    attachments = list(task.attachments.select_related("uploaded_by"))
    submission = task.events.filter(to_status=S.SUBMITTED, from_status__gt="").select_related("actor").first()
    return render(request, "boshqaruv/operations/tasks/detail.html", {
        "task": task,
        "assignments": assignments,
        "my_assignment": mine,
        "my_progress": mine.progress if mine else task.shown_progress,
        "can_update_progress": (can_work or mine is not None) and task.status in (S.ACCEPTED, S.IN_PROGRESS, S.BLOCKED, S.CHANGES_REQUESTED),
        "can_upload": can_work or mine is not None or policies.can_edit_task(user, task),
        "reference_files": [item for item in attachments if not item.is_deliverable],
        "result_files": [item for item in attachments if item.is_deliverable],
        "submission": submission,
        "subtasks": task.subtasks.select_related("assignee"),
        "dependencies": task.depends_on.all(),
        "comments": task.comments.filter(parent__isnull=True).select_related("author").prefetch_related("replies__author"),
        "reviews": task.reviews.select_related("reviewer"),
        "events": task.events.select_related("actor")[:30],
        "actions": [(a, services.TASK_ACTION_LABELS.get(a, S(a).label)) for a in services.allowed_task_actions(user, task)],
        "can_edit": policies.can_edit_task(user, task),
        "can_work": can_work,
        "can_submit": can_work and task.status in (S.IN_PROGRESS, S.CHANGES_REQUESTED),
        "can_review": can_review,
        "can_add_subtask": policies.can_assign(user, task.project) and task.parent_id is None,
        "comment_form": CommentForm(),
        "attachment_form": AttachmentForm(),
        "submit_form": SubmitForm(),
        "review_form": ReviewForm(),
    })


@login_required
def task_edit(request, pk):
    task = _get_task(request, pk)
    deny_unless(policies.can_edit_task(request.user, task))
    form = TaskForm(request.POST or None, request.FILES or None, instance=task, projects=Project.objects.filter(pk=task.project_id), actor=request.user)
    if request.method == "POST" and form.is_valid():
        services.update_task(request.user, task, form, request, posted_responsibilities(request.POST))
        messages.success(request, "Vazifa saqlandi.")
        return redirect(task)
    return render(request, "boshqaruv/operations/tasks/form.html", {"form": form, "task": task})


@require_POST
@login_required
def task_transition(request, pk):
    task = _get_task(request, pk)
    wants_json = request.headers.get("Accept") == "application/json"
    try:
        services.transition_task(request.user, task, request.POST.get("to", ""), request.POST.get("note", ""), request)
    except services.WorkflowError as e:
        if wants_json:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)
        messages.error(request, str(e))
        return back(request, task.get_absolute_url())
    if wants_json:
        return JsonResponse({"ok": True})
    messages.success(request, f"Holat: {task.get_status_display()}.")
    return back(request, task.get_absolute_url())


@require_POST
@login_required
def task_submit(request, pk):
    task = _get_task(request, pk)
    form = SubmitForm(request.POST, request.FILES)
    if not form.is_valid():
        for errs in form.errors.values():
            for e in errs:
                messages.error(request, e)
        return redirect(task)
    try:
        services.submit_task(request.user, task, form.cleaned_data["note"], form.cleaned_data["files"], request)
    except services.WorkflowError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "Ish tekshiruvga topshirildi.")
    return redirect(task)


@require_POST
@login_required
def task_review(request, pk):
    task = _get_task(request, pk)
    form = ReviewForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Qarorni tanlang.")
        return redirect(task)
    try:
        services.review_task(request.user, task, form.cleaned_data["decision"], form.cleaned_data["comment"], request)
    except services.WorkflowError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "Qaror saqlandi.")
    return redirect(task)


@require_POST
@login_required
def task_comment(request, pk):
    task = _get_task(request, pk)
    form = CommentForm(request.POST)
    if form.is_valid():
        parent = TaskComment.objects.filter(pk=int_post(request, "parent") or 0, task=task).first()
        c = TaskComment.objects.create(task=task, author=request.user, parent=parent, **form.cleaned_data)
        people = {task.assignee, task.created_by, task.project.manager} | {item.user for item in task.assignments.select_related("user")}
        people |= {cm.author for cm in task.comments.select_related("author")}
        mentioned = [u for u in task.project.team() if f"@{u.username}" in c.body]
        title = ("Aniqlik so'rovi" if c.is_clarification else "Yangi izoh") + f": {task.title}"
        notify(people | set(mentioned), Kind.COMMENT, title, body=c.body[:200],
               url=task.get_absolute_url() + "#izohlar", exclude=request.user)
    else:
        messages.error(request, "Izoh bo'sh bo'lishi mumkin emas.")
    return redirect(task.get_absolute_url() + "#izohlar")


@require_POST
@login_required
def task_attach(request, pk):
    task = _get_task(request, pk)
    deny_unless(policies.can_contribute_to_task(request.user, task) or policies.can_edit_task(request.user, task))
    form = AttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        for f in form.cleaned_data["files"]:
            Attachment.objects.create(task=task, uploaded_by=request.user, file=f, original_name=f.name[:255], size=f.size)
        messages.success(request, "Fayl qo'shildi.")
    else:
        for errs in form.errors.values():
            for e in errs:
                messages.error(request, e)
    return redirect(task.get_absolute_url() + "#fayllar")


@require_POST
@login_required
def task_progress(request, pk):
    task = _get_task(request, pk)
    try:
        services.update_task_progress(request.user, task, int_post(request, "progress"), request)
    except services.WorkflowError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "Bajarilish yangilandi.")
    return redirect(task)


@require_POST
@login_required
def task_quick(request, pk):
    task = _get_task(request, pk)
    deny_unless(policies.can_edit_task(request.user, task))
    assignee = None
    if request.POST.get("assignee"):
        assignee = active_users().filter(pk=int_post(request, "assignee") or 0).first()
        if assignee is None:
            messages.error(request, "Xodim topilmadi.")
            return back(request, task.get_absolute_url())
    try:
        services.quick_update_task(request.user, task, request.POST.get("deadline"), assignee, request)
    except services.WorkflowError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "Vazifa yangilandi.")
    return back(request, task.get_absolute_url())


@login_required
def attachment_download(request, pk):
    att = get_object_or_404(Attachment.objects.select_related("task__project"), pk=pk)
    deny_unless(policies.can_view_task(request.user, att.task))
    return _private_file(att.file, att.original_name, inline=bool(request.GET.get("korish")) and att.is_image)


# ------------------------------------------------------------------ management overview


@login_required
def work_control(request):
    """Everything a manager needs to steer the work, limited to what this person may see."""
    user = request.user
    deny_unless(user.has_cap("projects.assign") or user.has_cap("tasks.review") or user.managed_projects.exists())
    today = timezone.localdate()
    scope = policies.visible_tasks(user)
    projects = policies.visible_projects(user)
    active_projects = projects.exclude(status__in=[P.COMPLETED, P.ARCHIVED, P.CANCELLED])
    g = request.GET
    qs = scope.exclude(status=S.CANCELLED)
    if int_param(request, "xodim"):
        qs = qs.filter(Q(assignee=int_param(request, "xodim")) | Q(assignments__user=int_param(request, "xodim"))).distinct()
    if int_param(request, "loyiha"):
        qs = qs.filter(project=int_param(request, "loyiha"))
    if int_param(request, "menejer"):
        qs = qs.filter(project__manager=int_param(request, "menejer"))
    if g.get("holat"):
        qs = qs.filter(status=g["holat"])
    else:
        qs = qs.filter(status__in=Task.OPEN)
    if g.get("ustuvorlik"):
        qs = qs.filter(priority=g["ustuvorlik"])
    qs = _deadline_filter(qs, g.get("muddat"), today)
    page = paginate(request, _sorted_tasks(qs.select_related("project__manager", "assignee__role"), g.get("tartib", "muddat")), 25)
    for task in page:
        task.can_quick = policies.can_edit_task(user, task)
    open_tasks = scope.filter(status__in=Task.OPEN)
    people = active_users().filter(pk__in=scope.exclude(assignee=None).values("assignee")).annotate(
        open_count=Count("tasks", filter=Q(tasks__in=open_tasks.values("pk")), distinct=True),
        overdue_count=Count("tasks", filter=Q(tasks__in=open_tasks.filter(deadline__lt=today).values("pk")), distinct=True),
        review_count=Count("tasks", filter=Q(tasks__in=open_tasks.filter(status=S.SUBMITTED).values("pk")), distinct=True),
    ).order_by("-open_count", "first_name")
    return render(request, "boshqaruv/operations/tasks/control.html", {
        "page": page,
        "stats": [
            {"label": "Faol loyihalar", "value": active_projects.count(), "url": reverse("crm:projects")},
            {"label": "Ochiq vazifalar", "value": open_tasks.count(), "url": "?"},
            {"label": "Tekshiruv kutmoqda", "value": open_tasks.filter(status=S.SUBMITTED).count(), "url": "?holat=submitted"},
            {"label": "Muddati o'tgan", "value": open_tasks.filter(deadline__lt=today).count(), "url": "?muddat=otgan"},
            {"label": "Biriktirilmagan", "value": open_tasks.filter(assignee__isnull=True).count(), "url": "?holat=new"},
        ],
        "workload": people,
        "project_rows": active_projects.select_related("manager").with_progress().order_by("deadline", "pk")[:12],
        "employees": active_users().order_by("first_name", "username") if policies.can_assign_anyone(user) else people,
        "project_options": active_projects.order_by("name"),
        "managers": active_users().filter(pk__in=projects.exclude(manager=None).values("manager")),
        "statuses": S.choices, "priorities": Priority.choices, "deadlines": DEADLINE_FILTERS, "sorts": TASK_SORTS,
        "can_create_project": user.has_cap("projects.create"),
        "can_create_task": policies.assignable_projects(user).exists(),
        "next_url": request.get_full_path(),
    })
