"""Authorization rules for people and roles. Every view calls these; templates only mirror them."""

from django.db.models import Q

from .models import Role, User


def visible_employees(actor):
    qs = User.objects.select_related("role", "department", "manager")
    if actor.has_cap("employees.view") or actor.has_cap("employees.manage"):
        if actor.company_scope:
            return qs
        return qs.filter(Q(department=actor.department_id) | Q(pk=actor.pk)) if actor.department_id else qs.filter(pk=actor.pk)
    return qs.filter(pk=actor.pk)


def can_manage_user(actor, target):
    """Edit profile/security fields of target. Nobody manages themselves or a peer/senior."""
    if actor.pk == target.pk:
        return False
    if actor.is_owner:
        return not target.is_owner
    if not actor.has_cap("employees.manage"):
        return False
    if target.rank <= actor.rank:
        return False
    if not actor.company_scope and target.department_id != actor.department_id:
        return False
    return True


def assignable_roles(actor):
    """Roles the actor may give to someone: strictly junior and no broader than the actor's own powers."""
    roles = Role.objects.filter(is_owner=False, is_active=True)
    if actor.is_owner:
        return roles
    mine = actor.caps()
    allowed = [r.pk for r in roles if r.rank > actor.rank and set(r.capabilities) <= mine]
    return roles.filter(pk__in=allowed)


def can_edit_role(actor, role):
    if role.is_owner:
        return False
    if actor.is_owner:
        return True
    if not actor.has_cap("roles.manage"):
        return False
    return role.rank > actor.rank and set(role.capabilities) <= actor.caps()


def grantable_capabilities(actor):
    return actor.caps()
