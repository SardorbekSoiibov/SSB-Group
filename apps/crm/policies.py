"""Object-level authorization for projects, tasks, clients and inquiries."""

from django.db.models import Q

from .models import Client, Inquiry, Project, Task, TaskAssignment


def visible_projects(user):
    """Subquery-based (no joins on the outer query) so callers can safely aggregate."""
    qs = Project.objects.all()
    if user.has_cap("projects.view_all") and user.company_scope:
        return qs
    rule = Q(members=user) | Q(manager=user)
    if user.has_cap("projects.view_all") and user.department_id:
        rule |= Q(department=user.department_id)
    return qs.filter(pk__in=Project.objects.filter(rule).values("pk"))


def can_view_project(user, project):
    return visible_projects(user).filter(pk=project.pk).exists()


def is_project_lead(user, project):
    return project.manager_id == user.pk


def can_edit_project(user, project):
    if is_project_lead(user, project):
        return True
    return user.has_cap("projects.edit") and can_view_project(user, project)


def can_assign(user, project):
    """Only people the founder allowed to assign staff may change a project's team (not the assigned worker)."""
    return user.has_cap("projects.assign") and can_view_project(user, project)


def can_assign_anyone(user):
    """Company-wide assigners may pick any employee; choosing someone puts them on the project team."""
    return user.is_owner or (user.has_cap("projects.assign") and user.company_scope)


def can_share_on_project(user, project):
    return project.manager_id == user.pk or project.members.filter(pk=user.pk).exists() or can_edit_project(user, project)


def assignable_projects(user):
    projects = visible_projects(user).exclude(status__in=[Project.Status.COMPLETED, Project.Status.ARCHIVED, Project.Status.CANCELLED])
    return projects if user.has_cap("projects.assign") else projects.filter(manager=user)


def can_approve_project(user, project):
    return user.has_cap("projects.approve") and can_view_project(user, project)


def can_archive_project(user, project):
    return user.has_cap("projects.archive") and can_view_project(user, project)


def can_see_budget(user, project=None):
    return user.has_cap("projects.budget")


def _shared_task_ids(user):
    return TaskAssignment.objects.filter(user=user).values("task")


def my_tasks(user):
    """Tasks this person answers for or works on. No joins, so callers can safely aggregate."""
    return Task.objects.filter(Q(assignee=user) | Q(pk__in=_shared_task_ids(user)))


def visible_tasks(user):
    return Task.objects.filter(
        Q(project__in=visible_projects(user).values("pk")) | Q(assignee=user) | Q(pk__in=_shared_task_ids(user)))


def is_task_collaborator(user, task):
    return task.assignments.filter(user=user).exists()


def can_contribute_to_task(user, task):
    """Everyone doing the work: they may update their own progress and add files. Only the assignee submits."""
    return task.assignee_id == user.pk or is_task_collaborator(user, task)


def can_view_task(user, task):
    return can_contribute_to_task(user, task) or can_view_project(user, task.project)


def can_edit_task(user, task):
    return task.created_by_id == user.pk or can_assign(user, task.project)


def can_work_on_task(user, task):
    return task.assignee_id == user.pk


def can_review_task(user, task):
    """Reviewers never review their own work (the owner is the only exception)."""
    if task.assignee_id == user.pk and not user.is_owner:
        return False
    if is_project_lead(user, task.project) or task.created_by_id == user.pk:
        return True
    return user.has_cap("tasks.review") and can_view_project(user, task.project)


def visible_clients(user):
    if user.has_cap("clients.view") or user.has_cap("clients.manage"):
        return Client.objects.all()
    return Client.objects.filter(account_manager=user)


def can_manage_client(user, client):
    return user.has_cap("clients.manage") or client.account_manager_id == user.pk


def visible_inquiries(user):
    if user.has_cap("inquiries.manage"):
        return Inquiry.objects.all()
    return Inquiry.objects.filter(assigned_to=user)


def can_manage_inquiry(user, inquiry):
    return user.has_cap("inquiries.manage") or inquiry.assigned_to_id == user.pk


def can_convert_inquiry(user, inquiry):
    return user.has_cap("inquiries.manage") and user.has_cap("projects.create")
