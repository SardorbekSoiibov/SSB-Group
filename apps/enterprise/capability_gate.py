"""Central check: an employee only reaches the cabinet functions the founder granted.

Views keep their own object-level checks; this gate only decides whether a whole function
is available. The founder (owner) always passes. Pages not listed here (home, notifications,
profile, password, Windows app, search) are always available to signed-in staff.
"""
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect

PROJECT_CAPS = ("projects.own", "projects.view_all", "projects.create", "projects.edit", "projects.assign", "projects.approve")

# Tasks were removed: every old task address leads to the projects list.
TASK_VIEWS = {
    "crm:tasks", "crm:task_create", "crm:task_detail", "crm:task_edit", "crm:task_transition", "crm:task_submit",
    "crm:task_review", "crm:task_comment", "crm:task_attach", "crm:task_progress", "crm:task_quick",
    "crm:attachment_download", "crm:work_control", "crm:project_task_board", "enterprise:api_tasks",
}

RULES = {
    # loyihalar
    **{name: PROJECT_CAPS for name in (
        "crm:projects", "crm:project_detail", "crm:project_comment", "crm:project_file_upload", "crm:project_file_download",
        "crm:project_transition", "crm:milestone_add", "crm:milestone_toggle", "crm:project_cover", "crm:project_edit",
        "crm:project_members", "crm:project_member_add", "enterprise:api_projects")},
    **{name: ("projects.views", "projects.view_all") for name in ("crm:project_board", "crm:calendar", "crm:workload")},
    # ish jadvali
    **{name: ("schedule.view", "schedule.manage") for name in (
        "enterprise:schedule", "enterprise:cancel_shift", "enterprise:schedule_ai", "enterprise:schedule_ai_apply",
        "enterprise:api_schedule")},
    # baholash va reyting
    **{name: ("performance.self", "performance.view", "performance.manage") for name in (
        "enterprise:performance", "enterprise:rating", "enterprise:performance_history", "enterprise:evaluation_detail",
        "enterprise:weekly_publish", "enterprise:weekly_reward", "enterprise:review_approve")},
    # shaxsiy hisob
    "enterprise:balance": ("finance.balance", "finance.view"),
    # e'lonlar
    "crm:announcements": ("announcements.view", "announcements.manage"),
    "crm:announcement_image": ("announcements.view", "announcements.manage"),
    "crm:announcement_delete": ("announcements.view", "announcements.manage"),
    # arxiv
    **{name: ("archive.use", "archive.manage") for name in (
        "enterprise:archives", "enterprise:archive_code", "enterprise:archive_unlock", "enterprise:archive_lock",
        "enterprise:archive_download", "enterprise:archive_delete")},
}
NAMESPACE_RULES = {"chat": ("chat.use",)}


def required_caps(view_name, namespace):
    if view_name in RULES:
        return RULES[view_name]
    return NAMESPACE_RULES.get(namespace)


def _on_project_team(user, view_name, view_kwargs):
    """Loyihaga tayinlangan xodim (mas'ul yoki a'zo) o'z loyihasini "Loyihalar" funksiyasi ochilmagan bo'lsa ham ko'radi."""
    from django.db.models import Q
    from apps.crm.models import Project, ProjectFile
    pk = view_kwargs.get("pk")
    if not pk:
        return False
    if view_name == "crm:project_file_download":
        pk = ProjectFile.objects.filter(pk=pk).values_list("project_id", flat=True).first()
        if not pk:
            return False
    return Project.objects.filter(pk=pk).filter(Q(manager=user) | Q(members=user)).exists()


class CapabilityGateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = getattr(request, "resolver_match", None)
        user = getattr(request, "user", None)
        if not match or not user or not user.is_authenticated:
            return None
        name = match.view_name
        if name in TASK_VIEWS:
            if "/api/" in request.path:
                return JsonResponse({"error": "Vazifalar bo'limi olib tashlangan."}, status=404)
            return redirect("crm:projects")
        if user.is_owner:
            return None
        caps = required_caps(name, match.namespace)
        if name == "enterprise:schedule" and caps and not any(user.has_cap(cap) for cap in caps):
            from .models import WorkShift
            if WorkShift.objects.filter(employee=user).exists():
                return None  # smenasi bor xodim o'z jadvalini doim ko'radi (faqat o'zinikini — view shunday filtrlaydi)
        if caps and caps == PROJECT_CAPS and name != "crm:projects" and _on_project_team(user, name, view_kwargs):
            return None  # loyihaga tayinlangan xodim (mas'ul yoki a'zo) o'z loyihasini doim ko'radi
        if caps and not any(user.has_cap(cap) for cap in caps):
            if "/api/" in request.path:
                return JsonResponse({"error": "Bu funksiya sizga ochilmagan."}, status=403)
            raise PermissionDenied("Bu funksiya sizga ochilmagan. Asoschiga murojaat qiling.")
        return None
