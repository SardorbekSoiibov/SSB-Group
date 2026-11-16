"""Business workflows: task lifecycle, project lifecycle, inquiry conversion and portfolio hand-off.

Views stay thin and call these; every function enforces its own authorization.
"""

from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.audit.services import record
from apps.core.models import WorkspaceSettings
from apps.notifications.services import Kind, notify

from . import policies
from .models import (
    Attachment, Client, Inquiry, Project, ProjectApproval, ProjectAssignment, ProjectComment, ProjectFile, Task, TaskAssignment,
    TaskEvent, TaskReview,
)

S = Task.Status
P = Project.Status


class WorkflowError(Exception):
    """A rejected transition; the message is shown to the user."""


# ---------------------------------------------------------------- tasks

# (from, to) -> who may perform it via transition_task()
TASK_TRANSITIONS = {
    (S.ASSIGNED, S.ACCEPTED): "assignee",
    (S.ACCEPTED, S.IN_PROGRESS): "assignee",
    (S.ASSIGNED, S.IN_PROGRESS): "assignee",
    (S.CHANGES_REQUESTED, S.IN_PROGRESS): "assignee",
    (S.IN_PROGRESS, S.BLOCKED): "assignee",
    (S.BLOCKED, S.IN_PROGRESS): "assignee",
    (S.NEW, S.CANCELLED): "manager",
    (S.ASSIGNED, S.CANCELLED): "manager",
    (S.ACCEPTED, S.CANCELLED): "manager",
    (S.IN_PROGRESS, S.CANCELLED): "manager",
    (S.BLOCKED, S.CANCELLED): "manager",
    (S.CHANGES_REQUESTED, S.CANCELLED): "manager",
    (S.CANCELLED, S.ASSIGNED): "manager",
    (S.CANCELLED, S.NEW): "manager",
}


# What a button says: the status label names a state, not the thing the person does.
TASK_ACTION_LABELS = {
    S.ACCEPTED: "Vazifani qabul qilish", S.IN_PROGRESS: "Ishni boshlash", S.BLOCKED: "To'siq bor",
    S.CANCELLED: "Bekor qilish", S.ASSIGNED: "Qayta ochish", S.NEW: "Qayta ochish",
}
REASSIGN_RESETS = (S.NEW, S.ACCEPTED, S.IN_PROGRESS, S.BLOCKED)
UNASSIGN_RESETS = (S.ASSIGNED, S.ACCEPTED, S.IN_PROGRESS, S.BLOCKED, S.CHANGES_REQUESTED)


def allowed_task_actions(user, task):
    """Transitions the user may trigger on this task right now (used to render buttons)."""
    actions = []
    for (frm, to), who in TASK_TRANSITIONS.items():
        if frm != task.status:
            continue
        if to == S.NEW and task.assignee_id or to == S.ASSIGNED and not task.assignee_id:
            continue
        if who == "assignee" and policies.can_work_on_task(user, task):
            actions.append(to)
        elif who == "manager" and policies.can_edit_task(user, task):
            actions.append(to)
    return actions


def _log_task(task, actor, frm, to, note=""):
    TaskEvent.objects.create(task=task, actor=actor, from_status=frm, to_status=to, note=note)


def _task_reviewers(task):
    from apps.accounts.models import User

    people = [p for p in (task.project.manager, task.created_by) if p is not None and p.pk != task.assignee_id]
    return people or list(User.objects.filter(role__is_owner=True, status=User.Status.ACTIVE).exclude(pk=task.assignee_id))


def _task_workers(task):
    return [task.assignee, *[item.user for item in task.assignments.select_related("user")]]


def _locked_status(task):
    """Two clicks or two tabs must not submit or review the same work twice."""
    return Task.objects.select_for_update().filter(pk=task.pk).values_list("status", flat=True).get()


def _attach(task, actor, files, deliverable=False):
    for f in files:
        Attachment.objects.create(task=task, uploaded_by=actor, file=f, original_name=f.name[:255], size=f.size, is_deliverable=deliverable)


def _join_team(project, people, actor):
    """Assigning someone outside the team brings them in, so they also see the project in their workspace."""
    team = {person.pk for person in project.team()}
    joined = [person for person in people if person is not None and person.pk not in team]
    if joined:
        project.members.add(*joined)
        ProjectAssignment.objects.bulk_create([ProjectAssignment(project=project, user=person) for person in joined], ignore_conflicts=True)
        notify(joined, Kind.PROJECT_STATUS, f"Siz loyihaga qo'shildingiz: {project.name}", url=project.get_absolute_url(), exclude=actor)


def _url(task):
    return reverse("crm:task_detail", args=[task.pk])


@transaction.atomic
def create_task(actor, task, request=None, collaborators=(), responsibilities=None, files=()):
    if not policies.can_assign(actor, task.project):
        raise WorkflowError("Bu loyihaga vazifa qo'sha olmaysiz.")
    task.created_by = actor
    task.status = S.ASSIGNED if task.assignee_id else S.NEW
    task.assigned_at = timezone.now() if task.assignee_id else None
    task.save()
    _log_task(task, actor, "", task.status, "Vazifa yaratildi")
    record(actor, "task.created", task, {"project": str(task.project), "assignee": str(task.assignee or "")}, request)
    _join_team(task.project, [task.assignee, *collaborators], actor)
    _attach(task, actor, files)
    set_task_collaborators(actor, task, collaborators, responsibilities or {})
    if task.assignee:
        _notify_assigned(task, actor)
    return task


def set_task_collaborators(actor, task, people, responsibilities):
    """Each co-worker keeps their own responsibility and progress; the task itself stays one record."""
    wanted = {person.pk: person for person in people if person.pk != task.assignee_id}
    current = {item.user_id: item for item in task.assignments.all()}
    removed = [pk for pk in current if pk not in wanted]
    if removed:
        task.assignments.filter(user__in=removed).delete()
    added = []
    for pk, person in wanted.items():
        text = responsibilities.get(pk, "")
        if pk not in current:
            TaskAssignment.objects.create(task=task, user=person, responsibility=text)
            added.append(person)
        elif text != current[pk].responsibility:
            TaskAssignment.objects.filter(pk=current[pk].pk).update(responsibility=text)
    if added or removed:
        _log_task(task, actor, "", task.status, f"Hamkor ijrochilar yangilandi: {len(wanted)} nafar")
    notify(added, Kind.TASK_ASSIGNED, f"Yangi vazifa: {task.title}", body=task.project.name, url=_url(task), exclude=actor)


def _apply_assignee_change(actor, task, previous_id, request=None):
    """The new person starts from a clean «Yangi»: nobody inherits an acceptance they never gave."""
    if task.assignee_id == previous_id:
        return
    if not task.assignee_id:
        if task.status in UNASSIGN_RESETS:
            task.status = S.NEW
        task.assigned_at = None
    else:
        if task.status in REASSIGN_RESETS:
            task.status = S.ASSIGNED
        task.assigned_at = timezone.now()
    task.save(update_fields=["status", "assigned_at", "updated_at"])
    TaskAssignment.objects.filter(task=task, user=task.assignee_id).delete()
    _log_task(task, actor, "", task.status, f"Ijrochi: {task.assignee or 'biriktirilmagan'}")
    record(actor, "task.reassigned", task, {"assignee": [previous_id, task.assignee_id]}, request)
    if previous_id:
        from apps.accounts.models import User

        notify(User.objects.filter(pk=previous_id), Kind.TASK_ASSIGNED, f"Vazifa boshqa xodimga o'tkazildi: {task.title}", url=_url(task), exclude=actor)
    if task.assignee:
        _join_team(task.project, [task.assignee], actor)
        _notify_assigned(task, actor)


def _notify_schedule_change(actor, task, old_deadline, old_priority):
    notes = []
    if task.deadline != old_deadline:
        notes.append("Muddat: " + (f"{task.deadline:%d.%m.%Y}" if task.deadline else "olib tashlandi"))
    if task.priority != old_priority:
        notes.append(f"Ustuvorlik: {task.get_priority_display()}")
    if notes:
        text = " · ".join(notes)
        _log_task(task, actor, "", task.status, text)
        notify(_task_workers(task), Kind.TASK_ASSIGNED, f"Vazifa o'zgardi: {task.title}", body=text, url=_url(task), exclude=actor)


def _notify_assigned(task, actor):
    notify(
        [task.assignee], Kind.TASK_ASSIGNED, f"Yangi vazifa: {task.title}",
        body=f"{task.project.name} · muddat: {task.deadline:%d.%m.%Y}" if task.deadline else task.project.name,
        url=_url(task), exclude=actor,
    )


@transaction.atomic
def update_task(actor, task, form, request=None, responsibilities=None):
    """Save an edit form; handles re-assignment side effects."""
    from apps.audit.services import form_changes

    if not policies.can_edit_task(actor, task):
        raise WorkflowError("Bu vazifani tahrirlash huquqingiz yo'q.")
    changes = form_changes(form)
    changes.pop("files", None)
    previous_assignee = form.initial.get("assignee")
    old_deadline, old_priority = form.initial.get("deadline"), form.initial.get("priority")
    task = form.save(commit=False)
    task.save()
    form.save_m2m()
    if changes:
        record(actor, "task.updated", task, changes, request)
    collaborators = form.cleaned_data.get("collaborators", [])
    _apply_assignee_change(actor, task, previous_assignee, request)
    _join_team(task.project, collaborators, actor)
    set_task_collaborators(actor, task, collaborators, responsibilities or {})
    _attach(task, actor, form.cleaned_data.get("files", []))
    _notify_schedule_change(actor, task, old_deadline, old_priority)
    return task


@transaction.atomic
def quick_update_task(actor, task, deadline=None, assignee=None, request=None):
    """Deadline and reassignment from the management table, without opening the task."""
    if not policies.can_edit_task(actor, task):
        raise WorkflowError("Bu vazifani o'zgartirish huquqingiz yo'q.")
    if not task.is_open:
        raise WorkflowError("Yopilgan vazifani o'zgartirib bo'lmaydi.")
    old_deadline, old_priority, previous = task.deadline, task.priority, task.assignee_id
    if deadline is not None:
        try:
            task.deadline = parse_date(deadline) if deadline else None
        except ValueError:
            task.deadline = old_deadline
            raise WorkflowError("Muddat noto'g'ri kiritildi.")
        if deadline and task.deadline is None:
            task.deadline = old_deadline
            raise WorkflowError("Muddat noto'g'ri kiritildi.")
        if task.deadline and task.start_date and task.deadline < task.start_date:
            task.deadline = old_deadline
            raise WorkflowError("Muddat boshlanish sanasidan oldin bo'lishi mumkin emas.")
    if assignee is not None and assignee.pk != previous:
        if task.status == S.SUBMITTED:
            raise WorkflowError("Tekshiruvdagi ishni avval ko'rib chiqing.")
        if not policies.can_assign_anyone(actor) and assignee not in task.project.team():
            raise WorkflowError("Ijrochi loyiha jamoasida bo'lishi kerak.")
        task.assignee = assignee
    task.save(update_fields=["assignee", "deadline", "updated_at"])
    _apply_assignee_change(actor, task, previous, request)
    _notify_schedule_change(actor, task, old_deadline, old_priority)
    return task


@transaction.atomic
def update_task_progress(actor, task, value, request=None):
    """Own progress only: the assignee moves the task, a co-worker moves their own row."""
    if not policies.can_contribute_to_task(actor, task):
        raise WorkflowError("Faqat vazifa ijrochilari bajarilishni yangilay oladi.")
    if task.status not in (S.ACCEPTED, S.IN_PROGRESS, S.BLOCKED, S.CHANGES_REQUESTED):
        raise WorkflowError("Bajarilishni faqat ish davomida yangilash mumkin.")
    if not isinstance(value, int) or not 0 <= value <= 100:
        raise WorkflowError("Bajarilish 0 dan 100 gacha bo'lishi kerak.")
    if task.assignee_id == actor.pk:
        task.progress = value
        task.save(update_fields=["progress", "updated_at"])
    else:
        task.assignments.filter(user=actor).update(progress=value)
    _log_task(task, actor, "", task.status, f"Bajarilish: {value}%")
    record(actor, "task.progress", task, {"progress": value}, request)


@transaction.atomic
def transition_task(actor, task, to, note="", request=None):
    if to not in allowed_task_actions(actor, task):
        raise WorkflowError("Bu holatga o'tkazish mumkin emas yoki huquqingiz yo'q.")
    if to == S.IN_PROGRESS and task.status in (S.ASSIGNED, S.ACCEPTED):
        pending = list(task.unfinished_dependencies())
        if pending:
            raise WorkflowError("Avval bog'liq vazifalar yakunlanishi kerak: " + ", ".join(t.title for t in pending))
    frm = task.status
    task.status = to
    task.save(update_fields=["status", "updated_at"])
    _log_task(task, actor, frm, to, note)
    record(actor, "task.status", task, {"status": [frm, to]}, request)
    if to == S.ACCEPTED:
        notify(_task_reviewers(task), Kind.PROJECT_STATUS, f"Vazifa qabul qilindi: {task.title}", body=actor.display_name, url=_url(task), exclude=actor)
    if to == S.BLOCKED:
        notify(_task_reviewers(task), Kind.PROJECT_STATUS, f"To'siq: {task.title}", body=note, url=_url(task), exclude=actor)
    if to == S.CANCELLED:
        notify(_task_workers(task), Kind.PROJECT_STATUS, f"Vazifa bekor qilindi: {task.title}", url=_url(task), exclude=actor)
    return task


@transaction.atomic
def submit_task(actor, task, note, files, request=None):
    if not policies.can_work_on_task(actor, task):
        raise WorkflowError("Faqat ijrochi ishni topshira oladi.")
    task.status = _locked_status(task)
    if task.status not in (S.IN_PROGRESS, S.CHANGES_REQUESTED):
        raise WorkflowError("Ishni faqat «Bajarilmoqda» holatidan topshirish mumkin.")
    if not note.strip() and not files:
        raise WorkflowError("Topshirishda izoh yoki natija faylini qo'shing.")
    _attach(task, actor, files, deliverable=True)
    frm = task.status
    task.status = S.SUBMITTED
    task.submitted_at = timezone.now()
    task.save(update_fields=["status", "submitted_at", "updated_at"])
    _log_task(task, actor, frm, S.SUBMITTED, note)
    record(actor, "task.status", task, {"status": [frm, S.SUBMITTED]}, request)
    notify(
        _task_reviewers(task), Kind.SUBMITTED, f"Tekshiruvga topshirildi: {task.title}",
        body=f"{actor.display_name}: {note[:180]}", url=_url(task),
        dedupe_key=f"submitted:{task.pk}:{int(task.submitted_at.timestamp())}", exclude=actor,
    )
    return task


@transaction.atomic
def review_task(actor, task, decision, comment, request=None):
    if not policies.can_review_task(actor, task):
        raise WorkflowError("Bu ishni ko'rib chiqish huquqingiz yo'q.")
    task.status = _locked_status(task)
    if task.status != S.SUBMITTED:
        raise WorkflowError("Faqat topshirilgan ishni ko'rib chiqish mumkin.")
    if decision == TaskReview.Decision.CHANGES and not comment.strip():
        raise WorkflowError("Tuzatish so'raganda nimani o'zgartirish kerakligini yozing.")
    TaskReview.objects.create(task=task, reviewer=actor, decision=decision, comment=comment)
    frm = task.status
    task.status = S.APPROVED if decision == TaskReview.Decision.APPROVED else S.CHANGES_REQUESTED
    task.approved_at = timezone.now() if task.status == S.APPROVED else None
    if task.status == S.APPROVED:
        task.progress = 100
    task.save(update_fields=["status", "approved_at", "progress", "updated_at"])
    _log_task(task, actor, frm, task.status, comment)
    record(actor, "task.review", task, {"decision": decision, "comment": comment[:300]}, request)
    notify(
        _task_workers(task), Kind.REVIEWED,
        f"{'Qabul qilindi' if task.status == S.APPROVED else 'Qayta ishlash kerak'}: {task.title}",
        body=comment[:200], url=_url(task), exclude=actor,
    )
    project = task.project
    if task.status == S.APPROVED and project.status == P.IN_PROGRESS and project.progress() == 100 and project.manager:
        notify(
            [project.manager], Kind.APPROVAL, f"Barcha vazifalar qabul qilindi: {project.name}",
            body="Loyihani tekshiruvga o'tkazishingiz mumkin.", url=project.get_absolute_url(),
            dedupe_key=f"project-ready:{project.pk}",
        )
    return task


# ---------------------------------------------------------------- projects

PROJECT_TRANSITIONS = {
    (P.NEW, P.PLANNING): "editor",
    (P.PLANNING, P.AWAITING_APPROVAL): "editor",
    (P.PLANNING, P.IN_PROGRESS): "editor",  # only when start approval is not required
    (P.AWAITING_APPROVAL, P.IN_PROGRESS): "approver",
    (P.AWAITING_APPROVAL, P.PLANNING): "approver",
    (P.IN_PROGRESS, P.ON_HOLD): "editor",
    (P.ON_HOLD, P.IN_PROGRESS): "editor",
    (P.IN_PROGRESS, P.UNDER_REVIEW): "editor",
    (P.UNDER_REVIEW, P.IN_PROGRESS): "editor",
    (P.UNDER_REVIEW, P.COMPLETED): "approver",
    (P.PLANNING, P.ARCHIVED): "archiver",
    (P.ON_HOLD, P.ARCHIVED): "archiver",
    (P.COMPLETED, P.ARCHIVED): "archiver",
    (P.ARCHIVED, P.ON_HOLD): "archiver",
}
for _status in [P.NEW,P.PLANNING,P.AWAITING_APPROVAL,P.IN_PROGRESS,P.ON_HOLD,P.UNDER_REVIEW]:
    PROJECT_TRANSITIONS[(_status,P.CANCELLED)]='archiver'
PROJECT_TRANSITIONS[(P.CANCELLED,P.ON_HOLD)]='archiver'


def allowed_project_actions(user, project):
    need_approval = WorkspaceSettings.load().require_project_start_approval
    actions = []
    for (frm, to), who in PROJECT_TRANSITIONS.items():
        if frm != project.status:
            continue
        if (frm, to) == (P.PLANNING, P.IN_PROGRESS) and need_approval:
            continue
        if (frm, to) == (P.PLANNING, P.AWAITING_APPROVAL) and not need_approval:
            continue
        ok = {
            "editor": policies.can_edit_project,
            "approver": policies.can_approve_project,
            "archiver": policies.can_archive_project,
        }[who](user, project)
        if ok:
            actions.append(to)
    return actions


def sync_team(actor, project, before, responsibilities, request=None):
    """Keeps one responsibility row per team member and tells newcomers what they are there to do."""
    team = project.team()
    ids = [person.pk for person in team]
    project.assignments.exclude(user__in=ids).delete()
    existing = {item.user_id: item for item in project.assignments.all()}
    for person in team:
        text = responsibilities.get(person.pk)
        row = existing.get(person.pk)
        if row is None:
            ProjectAssignment.objects.create(project=project, user=person, responsibility=text or "")
        elif text is not None and text != row.responsibility:
            ProjectAssignment.objects.filter(pk=row.pk).update(responsibility=text)
    for person in team:
        if person.pk not in before:
            notify([person], Kind.PROJECT_STATUS, f"Siz loyihaga qo'shildingiz: {project.name}",
                   body=responsibilities.get(person.pk, ""), url=project.get_absolute_url(), exclude=actor)


@transaction.atomic
def add_project_member(actor, project, person, responsibility="", request=None):
    if not policies.can_assign(actor, project):
        raise WorkflowError("Bu loyiha jamoasini o'zgartira olmaysiz.")
    if project.is_closed:
        raise WorkflowError("Yopilgan loyihaga xodim qo'shib bo'lmaydi.")
    before = {member.pk for member in project.team()}
    project.members.add(person)
    sync_team(actor, project, before, {person.pk: responsibility.strip()[:200]}, request)
    record(actor, "project.members", project, {"added": str(person)}, request)


def notify_project_schedule(actor, project, old_deadline, old_priority):
    notes = []
    if project.deadline != old_deadline:
        notes.append("Muddat: " + (f"{project.deadline:%d.%m.%Y}" if project.deadline else "olib tashlandi"))
    if project.priority != old_priority:
        notes.append(f"Ustuvorlik: {project.get_priority_display()}")
    if notes:
        notify(project.team(), Kind.PROJECT_STATUS, f"Loyiha o'zgardi: {project.name}", body=" · ".join(notes),
               url=project.get_absolute_url(), exclude=actor)


@transaction.atomic
def add_project_comment(actor, project, body, parent=None, announcement=False):
    if announcement and not policies.can_edit_project(actor, project):
        raise WorkflowError("Loyiha e'lonini faqat rahbar yoza oladi.")
    comment = ProjectComment.objects.create(project=project, author=actor, parent=parent, body=body, is_announcement=announcement)
    url = project.get_absolute_url() + "#faoliyat"
    if announcement:
        notify(project.team(), Kind.ANNOUNCEMENT, f"Loyiha e'loni: {project.name}", body=body[:200], url=url, exclude=actor)
    else:
        people = project.team() + [parent.author] if parent else project.team()
        notify(people, Kind.COMMENT, f"Yangi izoh: {project.name}", body=body[:200], url=url, exclude=actor)
    return comment


@transaction.atomic
def add_project_files(actor, project, files, request=None):
    if not policies.can_share_on_project(actor, project):
        raise WorkflowError("Bu loyihaga fayl yuklay olmaysiz.")
    for f in files:
        ProjectFile.objects.create(project=project, uploaded_by=actor, file=f, original_name=f.name[:255], size=f.size)
    if files:
        record(actor, "project.file", project, {"files": [f.name[:120] for f in files]}, request)


def completion_blockers(project):
    # Vazifalar bo'limi olib tashlangan: loyihani faqat yakunlanmagan bosqichlar to'xtatadi
    # (eski vazifalar endi ko'rinmaydi va yopib bo'lmaydi, shuning uchun ular to'siq emas).
    blockers = []
    open_ms = project.milestones.filter(is_done=False).count()
    if open_ms:
        blockers.append(f"{open_ms} ta bosqich yakunlanmagan")
    return blockers


# Holat o'tishlari uchun tushunarli nomlar va natijasi (loyiha sahifasidagi "Keyingi qadam" kartasi).
_ACTION_TEXT = {
    (P.NEW, P.PLANNING): ("Rejalashtirishni boshlash", "Jamoa va bosqichlarni belgilash bosqichiga o‘tadi."),
    (P.PLANNING, P.AWAITING_APPROVAL): ("Asoschi tasdig‘iga yuborish", "Asoschiga xabar boradi; tasdiqlangach ish boshlanadi."),
    (P.PLANNING, P.IN_PROGRESS): ("Ishni boshlash", "Jamoaga xabar boradi va ish rasman boshlanadi."),
    (P.AWAITING_APPROVAL, P.IN_PROGRESS): ("Tasdiqlash va ishni boshlash", "Loyiha ishga tushadi, jamoaga xabar boradi."),
    (P.AWAITING_APPROVAL, P.PLANNING): ("Rejaga qaytarish", "Loyiha qayta rejalashtirish uchun qaytariladi."),
    (P.IN_PROGRESS, P.UNDER_REVIEW): ("Tekshiruvga topshirish", "Natija Asoschi tekshiruviga yuboriladi."),
    (P.IN_PROGRESS, P.ON_HOLD): ("Vaqtincha to‘xtatish", "Ish to‘xtatiladi; istalgan payt davom ettirish mumkin."),
    (P.ON_HOLD, P.IN_PROGRESS): ("Ishni davom ettirish", "Loyiha yana «Jarayonda» holatiga qaytadi."),
    (P.UNDER_REVIEW, P.COMPLETED): ("Qabul qilish va yakunlash", "Loyiha yakunlanadi; kelishuv bo‘yicha xodimlar ulushi avtomatik hisoblanadi."),
    (P.UNDER_REVIEW, P.IN_PROGRESS): ("Qayta ishlashga qaytarish", "Jamoa kamchiliklarni tuzatish uchun ishni davom ettiradi."),
    (P.COMPLETED, P.ARCHIVED): ("Arxivga o‘tkazish", "Loyiha faol ro‘yxatlardan chiqadi, tarix saqlanadi."),
    (P.PLANNING, P.ARCHIVED): ("Arxivga o‘tkazish", "Loyiha faol ro‘yxatlardan chiqadi, tarix saqlanadi."),
    (P.ON_HOLD, P.ARCHIVED): ("Arxivga o‘tkazish", "Loyiha faol ro‘yxatlardan chiqadi, tarix saqlanadi."),
    (P.ARCHIVED, P.ON_HOLD): ("Arxivdan qaytarish", "Loyiha «To‘xtatilgan» holatiga qaytadi."),
    (P.CANCELLED, P.ON_HOLD): ("Qayta tiklash", "Loyiha «To‘xtatilgan» holatiga qaytadi."),
}
_PRIMARY = {P.NEW: P.PLANNING, P.PLANNING: (P.AWAITING_APPROVAL, P.IN_PROGRESS), P.AWAITING_APPROVAL: P.IN_PROGRESS,
            P.IN_PROGRESS: P.UNDER_REVIEW, P.ON_HOLD: P.IN_PROGRESS, P.UNDER_REVIEW: P.COMPLETED}
_NOW_TEXT = {
    P.NEW: "Loyiha yaratildi. Rejalashtirishni boshlang: jamoa, bosqichlar va muddatni belgilang.",
    P.PLANNING: "Rejalashtirilmoqda. Jamoa va bosqichlar tayyor bo‘lgach, ishni boshlang.",
    P.AWAITING_APPROVAL: "Asoschi tasdig‘ini kutmoqda. Tasdiqlangach ish boshlanadi.",
    P.IN_PROGRESS: "Jamoa ishlamoqda. Bosqichlarni bajarilgan deb belgilab boring; hammasi tayyor bo‘lgach tekshiruvga topshiring.",
    P.ON_HOLD: "Ish vaqtincha to‘xtatilgan.",
    P.UNDER_REVIEW: "Natija tekshirilmoqda. Qabul qilinsa loyiha yakunlanadi va xodimlar ulushi hisoblanadi.",
    P.COMPLETED: "Loyiha yakunlangan. Xodimlar ulushi hisoblangan.",
    P.ARCHIVED: "Loyiha arxivda. Barcha tarix saqlangan.",
    P.CANCELLED: "Loyiha bekor qilingan. Moliyaviy tarix saqlangan.",
}


def project_control(user, project):
    """Loyiha sahifasi uchun: holat yo'li, hozirgi holat izohi, asosiy va qo'shimcha amallar."""
    need_approval = WorkspaceSettings.load().require_project_start_approval
    path = [P.NEW, P.PLANNING] + ([P.AWAITING_APPROVAL] if need_approval else []) + [P.IN_PROGRESS, P.UNDER_REVIEW, P.COMPLETED]
    position = {P.ON_HOLD: P.IN_PROGRESS, P.ARCHIVED: P.COMPLETED}.get(project.status, project.status)
    index = path.index(position) if position in path else -1
    steps = [{"label": P(s).label, "state": "done" if i < index or project.status in (P.COMPLETED, P.ARCHIVED) and i == index
              else ("current" if i == index else "todo")} for i, s in enumerate(path)]
    allowed = allowed_project_actions(user, project)
    primary_targets = _PRIMARY.get(project.status, ())
    primary_targets = primary_targets if isinstance(primary_targets, tuple) else (primary_targets,)
    blockers = completion_blockers(project) if project.status in (P.IN_PROGRESS, P.UNDER_REVIEW) else []
    actions = []
    for to in allowed:
        label, effect = _ACTION_TEXT.get((project.status, to), (P(to).label, ""))
        if to == P.CANCELLED:
            label, effect = "Loyihani bekor qilish", "Sababini yozish majburiy. Moliyaviy tarix o‘chirilmaydi."
        actions.append({"to": to, "label": label, "effect": effect, "primary": to in primary_targets,
                        "danger": to == P.CANCELLED, "needs_comment": to == P.CANCELLED,
                        "blocked": blockers if to == P.COMPLETED else []})
    actions.sort(key=lambda a: (not a["primary"], a["danger"]))
    return {"steps": steps, "paused": project.status == P.ON_HOLD, "cancelled": project.status == P.CANCELLED,
            "now": _NOW_TEXT.get(project.status, ""), "actions": actions, "blockers": blockers}


@transaction.atomic
def transition_project(actor, project, to, comment="", request=None):
    if to not in allowed_project_actions(actor, project):
        raise WorkflowError("Bu holatga o'tkazish mumkin emas yoki huquqingiz yo'q.")
    if to==P.CANCELLED and len(comment.strip())<5:
        raise WorkflowError('Loyihani bekor qilish sababini kiriting. Moliyaviy tarix va vazifalar o‘chirilmaydi.')
    if to == P.COMPLETED:
        blockers = completion_blockers(project)
        if blockers:
            raise WorkflowError("Loyihani yakunlab bo'lmaydi: " + "; ".join(blockers) + ".")
    frm = project.status
    project.status = to
    project.completed_at = timezone.now() if to == P.COMPLETED else (project.completed_at if to == P.ARCHIVED else None)
    project.save(update_fields=["status", "completed_at", "updated_at"])
    if (frm, to) == (P.AWAITING_APPROVAL, P.IN_PROGRESS):
        ProjectApproval.objects.create(project=project, kind=ProjectApproval.Kind.START, actor=actor, comment=comment)
    if to == P.COMPLETED:
        ProjectApproval.objects.create(project=project, kind=ProjectApproval.Kind.COMPLETION, actor=actor, comment=comment)
        # Approved completion books each member's agreed share as payable. Idempotent per agreement version.
        from apps.enterprise.finance import accrue_project_completion
        accrue_project_completion(actor, project)
    record(actor, "project.status", project, {"status": [frm, to], "comment": comment[:300]}, request)
    title = f"{project.name}: {Project.Status(to).label}"
    notify(project.team(), Kind.PROJECT_STATUS, title, body=comment[:200], url=project.get_absolute_url(), exclude=actor)
    if to == P.AWAITING_APPROVAL:
        from apps.accounts.models import User

        approvers = [u for u in User.objects.filter(status=User.Status.ACTIVE).select_related("role")
                     if policies.can_approve_project(u, project)]
        notify(approvers, Kind.APPROVAL, f"Tasdiq kutilmoqda: {project.name}", url=project.get_absolute_url(), exclude=actor)
    return project


@transaction.atomic
def approve_for_portfolio(actor, project, request=None):
    """Explicit approval for public presentation: creates a linked *draft* portfolio entry."""
    from apps.website.models import PortfolioProject

    if not (actor.has_cap("cms.publish") and policies.can_view_project(actor, project)):
        raise WorkflowError("Portfolioga chiqarish uchun nashr huquqi kerak.")
    if project.status not in (P.COMPLETED, P.ARCHIVED):
        raise WorkflowError("Faqat yakunlangan loyihani portfolioga tayyorlash mumkin.")
    if hasattr(project, "portfolio_entry"):
        return project.portfolio_entry
    entry = PortfolioProject.objects.create(
        title=project.name,
        summary=(project.description or project.name)[:240],
        description=project.description,
        client_name=project.client.company or project.client.name if project.client else "",
        completed_on=project.completed_at.date() if project.completed_at else None,
        source_project=project,
    )
    ProjectApproval.objects.create(project=project, kind=ProjectApproval.Kind.PUBLICATION, actor=actor)
    record(actor, "project.to_portfolio", project, {"portfolio_id": entry.pk}, request)
    return entry


# ---------------------------------------------------------------- inquiries

def notify_new_inquiry(inquiry):
    from apps.accounts.models import User

    managers = [u for u in User.objects.filter(status=User.Status.ACTIVE).select_related("role") if u.has_cap("inquiries.manage")]
    notify(
        managers, Kind.INQUIRY, f"Yangi murojaat: {inquiry.name}",
        body=inquiry.description[:200], url=inquiry.get_absolute_url(), dedupe_key=f"inquiry:{inquiry.pk}",
    )


@transaction.atomic
def assign_inquiry(actor, inquiry, assignee):
    if assignee and assignee.pk != actor.pk:
        notify([assignee], Kind.INQUIRY, f"Sizga murojaat biriktirildi: {inquiry.name}", url=inquiry.get_absolute_url())


@transaction.atomic
def convert_inquiry(actor, inquiry, request=None):
    if not policies.can_convert_inquiry(actor, inquiry):
        raise WorkflowError("Murojaatni loyihaga aylantirish huquqingiz yo'q.")
    if hasattr(inquiry, "project"):
        raise WorkflowError("Bu murojaat allaqachon loyihaga aylantirilgan.")
    if inquiry.stage == Inquiry.Stage.REJECTED:
        raise WorkflowError("Rad etilgan murojaatni loyihaga aylantirib bo'lmaydi.")
    client = inquiry.client
    if client is None:
        contact = inquiry.contact
        client = Client.objects.create(
            name=inquiry.name,
            email=contact if "@" in contact else "",
            phone=contact if inquiry.preferred_method == Inquiry.ContactMethod.PHONE else "",
            telegram=contact if inquiry.preferred_method == Inquiry.ContactMethod.TELEGRAM else "",
            account_manager=inquiry.assigned_to or actor,
        )
        inquiry.client = client
    service = f" ({inquiry.service.title})" if inquiry.service else ""
    project = Project.objects.create(
        name=f"{client}{service}"[:160],
        description=inquiry.description,
        client=client,
        inquiry=inquiry,
        manager=inquiry.assigned_to or actor,
        created_by=actor,
    )
    inquiry.stage = Inquiry.Stage.CONVERTED
    inquiry.save(update_fields=["client", "stage", "updated_at"])
    record(actor, "inquiry.converted", inquiry, {"project": project.code, "client": str(client)}, request)
    record(actor, "project.created", project, {"from_inquiry": inquiry.pk}, request)
    if project.manager:
        notify([project.manager], Kind.PROJECT_STATUS, f"Yangi loyiha: {project.name}", url=project.get_absolute_url(), exclude=actor)
    return project
