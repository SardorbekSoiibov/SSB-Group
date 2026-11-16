"""Profile, employees, roles and departments."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.decorators.http import require_POST

from apps.accounts import policies as people
from apps.accounts.forms import DepartmentForm, EmployeeForm, ProfileForm, ProfilePhotoForm, RoleForm
from apps.accounts.models import Department, Role, User
from apps.audit.models import AuditEvent
from apps.audit.services import form_changes, record

from .. import badges
from ..policies import visible_projects
from ..models import Project, Task, TaskEvent
from .base import back, deny_unless, int_param, paginate, require_cap
from .equipment import holder_equipment


@login_required
def profile(request):
    user = request.user
    form = ProfileForm(request.POST or None, request.FILES or None, instance=user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profil saqlandi.")
        return redirect("crm:profile")
    done = Project.objects.filter(
        pk__in=Project.objects.filter(Q(members=user) | Q(manager=user)).values("pk"), status=Project.Status.COMPLETED,
    ).order_by("-completed_at")[:15]
    return render(request, "boshqaruv/operations/profile.html", {"form": form, "completed_projects": done,
                                                                 "my_equipment": holder_equipment(user)})


@login_required
@require_POST
def profile_photo(request):
    """Replaces or removes the signed-in person's own photo, then discards the old file."""
    from apps.enterprise.erasure import delete_files_after_commit

    user = request.user
    old = user.photo.name
    storage = user.photo.storage
    if request.POST.get("action") == "remove":
        user.photo = ""
        user.save(update_fields=["photo"])
        messages.success(request, "Profil rasmi o‘chirildi.")
    else:
        form = ProfilePhotoForm(request.POST, request.FILES, instance=user)
        if not form.is_valid():
            messages.error(request, form.errors["photo"][0])
            return redirect("crm:profile")
        form.save()
        messages.success(request, "Profil rasmi yangilandi.")
    if old and old != user.photo.name:
        delete_files_after_commit([(storage, old)])
    return redirect("crm:profile")


# ------------------------------------------------------------------ employees

@require_cap("employees.view", "employees.manage", any_of=True)
def employee_list(request):
    closed = [Project.Status.COMPLETED, Project.Status.ARCHIVED, Project.Status.CANCELLED]
    qs = people.visible_employees(request.user).annotate(
        active_projects=Count("projects", filter=~Q(projects__status__in=closed), distinct=True)
        + Count("managed_projects", filter=~Q(managed_projects__status__in=closed), distinct=True)
    )
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(username__icontains=q)
                       | Q(job_title__icontains=q) | Q(skills__contains=[q]))
    for param, field in (("bolim", "department"),):
        if int_param(request, param):
            qs = qs.filter(**{field: int_param(request, param)})
    if request.GET.get("holat"):
        qs = qs.filter(status=request.GET["holat"])
    if not request.GET.get("holat"):
        qs = qs.exclude(status=User.Status.DEACTIVATED)

    # Sahifa tepasidagi qisqa ko'rsatkichlar va holat bo'yicha tablar (filtrsiz umumiy jamoa).
    S = User.Status
    counts = people.visible_employees(request.user).aggregate(
        **{code: Count("pk", filter=Q(status=code)) for code in S.values}
    )
    current = request.GET.get("holat", "")
    keep = request.GET.copy()
    keep.pop("page", None)
    tabs = []
    for code, label in [("", "Barchasi"), (S.ACTIVE, "Faol"), (S.INVITED, "Taklif qilingan"),
                        (S.SUSPENDED, "To‘xtatilgan"), (S.DEACTIVATED, "Ishdan ketgan")]:
        params = keep.copy()
        params.pop("holat", None)
        if code:
            params["holat"] = code
        count = counts[code] if code else counts[S.ACTIVE] + counts[S.INVITED] + counts[S.SUSPENDED]
        tabs.append({"label": label, "count": count, "active": current == code,
                     "url": "?" + params.urlencode() if params else request.path})
    departments = Department.objects.all()
    return render(request, "boshqaruv/operations/employees/list.html", {
        "page": paginate(request, qs.select_related("department", "role").order_by("first_name", "last_name")),
        "departments": departments,
        "statuses": User.Status.choices,
        "status_tabs": tabs,
        "team_stats": {"team": tabs[0]["count"], "active": counts[S.ACTIVE], "invited": counts[S.INVITED],
                       "departments": departments.count()},
        "filtered": bool(request.GET.get("q") or request.GET.get("bolim")),
        "can_manage": request.user.has_cap("employees.manage"),
    })


def _invite_link(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return request.build_absolute_uri(reverse("accounts:set_password", args=[uid, token]))


@require_cap("employees.manage")
def employee_create(request):
    form = EmployeeForm(request.POST or None, request.FILES or None, actor=request.user)
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.status = User.Status.INVITED
        user.set_unusable_password()
        user.save()
        form.save_m2m()
        form.apply_capabilities(user)
        record(request.user, "user.created", user, {**form_changes(form), "capabilities": sorted(form.cleaned_data.get("capabilities") or [])}, request)
        request.session["invite_link"] = {"user": user.pk, "link": _invite_link(request, user)}
        messages.success(request, f"{user.display_name} qo'shildi. Taklif havolasini xodimga yuboring.")
        return redirect("crm:employee_detail", user.pk)
    return render(request, "boshqaruv/operations/employees/form.html", {"form": form})


@require_cap("employees.view", "employees.manage", any_of=True)
def employee_detail(request, pk):
    employee = get_object_or_404(people.visible_employees(request.user), pk=pk)
    invite = request.session.pop("invite_link", None)
    reset = request.session.pop("reset_link", None)
    visible =visible_projects(request.user).values("pk")
    tasks = Task.objects.filter(assignee=employee, project__in=visible).select_related("project")
    projects = Project.objects.filter(
        pk__in=Project.objects.filter(Q(members=employee) | Q(manager=employee)).values("pk")
    ).filter(pk__in=visible).with_progress()
    can_manage = people.can_manage_user(request.user, employee)
    history = []
    if request.user.has_cap("audit.view"):
        history = AuditEvent.objects.filter(target_type="accounts.user", target_id=str(employee.pk)).select_related("actor")[:15]
    balances=[]
    if request.user.has_cap('finance.view'):
        from apps.enterprise.finance import employee_balance
        for currency in employee.ledger_entries.values_list('currency',flat=True).distinct():
            balances.append(employee_balance(employee,currency))
    can_erase = request.user.is_owner and employee.pk != request.user.pk and not employee.is_owner
    erase_items = ""
    if can_erase:
        from apps.enterprise.erasure import erase_preview
        erase_items = "|".join(erase_preview(employee))
    return render(request, "boshqaruv/operations/employees/detail.html", {
        "employee": employee,
        "employee_balances":balances,
        "invite": invite if invite and invite["user"] == employee.pk else None,
        "reset_link": reset["link"] if reset and reset["user"] == employee.pk else None,
        "can_reset_password": request.user.is_owner and employee.pk != request.user.pk and not employee.is_owner
                              and employee.status != User.Status.INVITED,
        "open_tasks": tasks.filter(status__in=Task.OPEN).order_by("deadline"),
        "done_tasks": tasks.filter(status=Task.Status.APPROVED).order_by("-approved_at")[:10],
        "projects": projects.exclude(status=Project.Status.ARCHIVED),
        "activity": TaskEvent.objects.filter(actor=employee, task__project__in=visible).select_related("task")[:10],
        "history": history,
        "can_manage": can_manage,
        "can_view_contract": can_manage or request.user.is_owner or request.user.pk == employee.pk,
        "can_erase": can_erase,
        "erase_items": erase_items,
        "statuses": [s for s in User.Status.choices if s[0] != User.Status.INVITED],
        "reports": employee.reports.filter(status=User.Status.ACTIVE),
        "granted": _granted_groups(employee),
        "function_count": 0 if employee.is_owner or not employee.role_id else len(employee.role.capabilities),
        "active_count": projects.exclude(status__in=[Project.Status.COMPLETED, Project.Status.ARCHIVED, Project.Status.CANCELLED]).count(),
        "done_count": projects.filter(status=Project.Status.COMPLETED).count(),
        "open_task_count": tasks.filter(status__in=Task.OPEN).count(),
        # Jihozlarni faqat Asoschi (hammasini) yoki xodimning o'zi ko'radi.
        "employee_equipment": holder_equipment(employee) if (request.user.is_owner or request.user.pk == employee.pk) else None,
        **_badge_context(request, employee),
    })


def _badge_context(request, employee):
    from django.utils.safestring import mark_safe

    from apps.core.models import WorkspaceSettings

    from urllib.parse import urlparse

    from .. import brand

    url = badges.verify_url(request, employee)
    size, two_lines = badges.name_layout(employee.display_name)
    return {
        "badge_id": badges.badge_id(employee),
        "badge_host": urlparse(url).hostname or request.get_host(),
        "badge_logo": mark_safe(brand.svg(cut="#123063")),
        "badge_mark": mark_safe(brand.svg(mark_only=True)),
        "badge_status_color": badges.status_color(employee),
        "badge_name_class": ("is-long" if size < 3.7 else "") + (" is-two" if two_lines else ""),
        "badge_url": url,
        "badge_qr": mark_safe(badges.qr_svg(url)),  # o'zimiz yasagan SVG, foydalanuvchi matni yo'q
        "badge_company": WorkspaceSettings.load().company_name or "SSB Group",
        "badge_partners": badges.badge_partners(),
    }


@login_required
def employee_badge_pdf(request, pk):
    """Chop etishga tayyor bedjik (A4, haqiqiy o'lcham). Xodim sahifasini ko'ra oladiganlar uchun."""
    from django.http import HttpResponse

    from apps.core.models import WorkspaceSettings

    employee = get_object_or_404(people.visible_employees(request.user), pk=pk)
    ws = WorkspaceSettings.load()
    pdf = badges.badge_pdf(employee, badges.verify_url(request, employee),
                           company=ws.company_name or "SSB Group", accent=ws.accent_color or "#007aff",
                           partners=badges.badge_partners())
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="bedjik-{badges.badge_id(employee)}.pdf"'
    resp["Cache-Control"] = "private, no-store"
    return resp


def badge_verify(request, token):
    """Ochiq sahifa: QR skanerlanganda xodim ekanligini tasdiqlaydi. Faqat ommaviy ma'lumot (ism, lavozim, bo'lim)."""
    from apps.core.models import WorkspaceSettings

    person = badges.user_from_token(token)
    valid = bool(person and person.status == User.Status.ACTIVE)
    resp = render(request, "website/badge_verify.html", {
        "person": person, "valid": valid, "token": token,
        "badge_id": badges.badge_id(person) if person else "",
        "company": WorkspaceSettings.load().company_name or "SSB Group",
        "checked_at": timezone.localtime(),
    }, status=200 if person else 404)
    resp["Cache-Control"] = "no-store"
    resp["X-Robots-Tag"] = "noindex, nofollow"
    return resp


def badge_photo(request, token):
    """Tasdiqlash sahifasidagi rasm — faqat to'g'ri imzoli token va faol xodim uchun."""
    person = badges.user_from_token(token)
    if not person or person.status != User.Status.ACTIVE or not person.photo:
        raise Http404
    resp = FileResponse(person.photo.open("rb"))
    resp["Cache-Control"] = "private, max-age=600"
    resp["X-Robots-Tag"] = "noindex"
    return resp


def _granted_groups(employee):
    """The functions this employee can use, grouped like the form, for the profile page."""
    from apps.accounts.models import CAPABILITY_GROUPS, Capability

    if employee.is_owner:
        return [("Asoschi", ["Barcha funksiyalar"])]
    labels = dict(Capability.choices)
    caps = set(employee.role.capabilities) if employee.role_id else set()
    return [(title, [labels[c] for c in items if c in caps]) for title, items in CAPABILITY_GROUPS if caps & set(items)]


@require_cap("employees.manage")
def employee_edit(request, pk):
    employee = get_object_or_404(people.visible_employees(request.user), pk=pk)
    deny_unless(people.can_manage_user(request.user, employee))
    form = EmployeeForm(request.POST or None, request.FILES or None, instance=employee, actor=request.user)
    if request.method == "POST" and form.is_valid():
        changes = form_changes(form)
        before_caps = sorted(employee.role.capabilities) if employee.role_id else []
        form.save()
        form.apply_capabilities(employee)
        employee.refresh_from_db()
        after_caps = sorted(employee.role.capabilities) if employee.role_id else []
        if after_caps != before_caps:
            changes["capabilities"] = [before_caps, after_caps]
        if changes:
            record(request.user, "user.updated", employee, changes, request)
        messages.success(request, "Xodim ma'lumotlari saqlandi.")
        return redirect("crm:employee_detail", employee.pk)
    return render(request, "boshqaruv/operations/employees/form.html", {"form": form, "employee": employee})


@require_POST
@login_required
def employee_verify(request, pk):
    """Founder only, including their own account: a badge people grant themselves would mean nothing."""
    deny_unless(request.user.is_owner)
    employee = get_object_or_404(User, pk=pk)
    employee.is_verified = not employee.is_verified
    employee.save(update_fields=["is_verified"])
    record(request.user, "user.verified", employee, {"verified": employee.is_verified}, request)
    messages.success(request, "Tasdiq belgisi yoqildi." if employee.is_verified else "Tasdiq belgisi o'chirildi.")
    return back(request, reverse("crm:employee_detail", args=[pk]))


@require_POST
@login_required
def employee_erase(request, pk):
    """Second step of removing an employee from the whole database. Founder only."""
    from apps.core.secure_delete import confirm_delete_password
    from apps.enterprise.erasure import erase_employee

    deny_unless(request.user.is_owner)
    employee = get_object_or_404(User, pk=pk)
    deny_unless(employee.pk != request.user.pk and not employee.is_owner)
    if not confirm_delete_password(request):
        return redirect("crm:employee_detail", pk)
    name = employee.display_name
    erase_employee(request.user, employee, request)
    messages.success(request, f"{name} va barcha ma'lumotlari bazadan o'chirildi.")
    return redirect("crm:employees")


@require_POST
@require_cap("employees.manage")
def employee_status(request, pk):
    employee = get_object_or_404(people.visible_employees(request.user), pk=pk)
    deny_unless(people.can_manage_user(request.user, employee))
    status = request.POST.get("status")
    if status not in (User.Status.ACTIVE, User.Status.SUSPENDED, User.Status.DEACTIVATED):
        raise Http404
    old = employee.status
    if employee.status == User.Status.INVITED and status == User.Status.ACTIVE:
        messages.error(request, "Taklif qilingan xodim parol o'rnatgach avtomatik faollashadi.")
        return redirect("crm:employee_detail", pk)
    employee.status = status
    employee.save(update_fields=["status", "is_active"])
    if status != User.Status.ACTIVE:
        _end_sessions(employee)
    record(request.user, "user.status", employee, {"status": [old, status]}, request)
    messages.success(request, f"Hisob holati: {employee.get_status_display()}.")
    return redirect("crm:employee_detail", pk)


def _end_sessions(user):
    from django.contrib.sessions.models import Session

    for s in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        if s.get_decoded().get("_auth_user_id") == str(user.pk):
            s.delete()


@require_POST
@require_cap("employees.manage")
def employee_invite(request, pk):
    employee = get_object_or_404(people.visible_employees(request.user), pk=pk)
    deny_unless(people.can_manage_user(request.user, employee) and employee.status == User.Status.INVITED)
    request.session["invite_link"] = {"user": employee.pk, "link": _invite_link(request, employee)}
    record(request.user, "user.invite_link", employee, request=request)
    return redirect("crm:employee_detail", pk)


@require_POST
@login_required
def employee_password(request, pk):
    """Founder only: a forgotten password is recovered either with a one-time link (the employee picks the
    new password) or by the Founder setting a new one. Every open session of the employee is closed."""
    from apps.accounts.forms import SetPasswordForm

    deny_unless(request.user.is_owner)
    employee = get_object_or_404(User, pk=pk)
    deny_unless(employee.pk != request.user.pk and not employee.is_owner and employee.status != User.Status.INVITED)
    action = request.POST.get("action")
    if action == "link":
        request.session["reset_link"] = {"user": employee.pk, "link": _invite_link(request, employee)}
        record(request.user, "user.reset_link", employee, request=request)
        messages.success(request, "Bir martalik tiklash havolasi tayyor. Uni faqat shu xodimga yuboring.")
    elif action == "set":
        form = SetPasswordForm(employee, request.POST)
        if not form.is_valid():
            for errors in form.errors.values():
                for error in errors:
                    messages.error(request, error)
            return redirect(f"{reverse('crm:employee_detail', args=[pk])}#parol")
        form.save()
        _end_sessions(employee)
        record(request.user, "user.password_reset", employee, request=request)
        messages.success(request, f"{employee.display_name} uchun yangi parol o'rnatildi. Eski seanslar yopildi.")
    else:
        raise Http404
    return redirect(f"{reverse('crm:employee_detail', args=[pk])}#parol")


@login_required
def employee_contract(request, pk):
    """Mehnat shartnomasi: faqat xodimning o'zi, Asoschi va shu xodimni boshqaradigan rahbar yuklab oladi."""
    employee = get_object_or_404(User, pk=pk)
    allowed = request.user.pk == employee.pk or request.user.is_owner or (
        request.user.has_cap("employees.manage")
        and people.visible_employees(request.user).filter(pk=pk).exists()
        and people.can_manage_user(request.user, employee)
    )
    deny_unless(allowed)
    if not employee.contract:
        raise Http404
    record(request.user, "user.contract_downloaded", employee, request=request)
    number = "".join(ch for ch in employee.contract_number if ch.isalnum() or ch in "-_") or str(employee.pk)
    resp = FileResponse(employee.contract.open("rb"), as_attachment=True,
                        filename=f"mehnat-shartnomasi-{number}.{employee.contract_extension.lower()}")
    resp["Cache-Control"] = "private, no-store"
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


@login_required
def employee_photo(request, pk):
    """Private profile photos: visible to logged-in staff who may see the employee."""
    employee = get_object_or_404(User, pk=pk)
    if not employee.photo:
        raise Http404
    resp = FileResponse(employee.photo.open("rb"))
    resp["Cache-Control"] = "private, max-age=3600"
    return resp


# ------------------------------------------------------------------ roles & departments

@require_cap("roles.manage")
def role_list(request):
    """Company structure as a diagram: the founder on top, departments below, employees inside."""
    from django.db.models import Prefetch

    alive = User.objects.exclude(status=User.Status.DEACTIVATED).select_related("role").order_by("first_name", "last_name")
    people_list = list(alive)
    founders = [u for u in people_list if u.is_owner]
    for person in people_list:
        person.function_count = 0 if person.is_owner or not person.role_id else len(person.role.capabilities)
    by_dept = {}
    for person in people_list:
        if not person.is_owner:
            by_dept.setdefault(person.department_id, []).append(person)
    departments = list(Department.objects.select_related("head"))
    for dept in departments:
        dept.people = by_dept.get(dept.pk, [])
    return render(request, "boshqaruv/operations/roles/list.html", {
        "founders": founders,
        "departments": departments,
        "unassigned": by_dept.get(None, []),
        "people_total": len(people_list),
    })


@require_cap("roles.manage")
def role_edit(request, pk=None):
    role = get_object_or_404(Role, pk=pk) if pk else None
    if role:
        deny_unless(people.can_edit_role(request.user, role))
    form = RoleForm(request.POST or None, instance=role, actor=request.user)
    if request.method == "POST" and form.is_valid():
        changes = form_changes(form)
        role = form.save()
        record(request.user, "role.updated" if pk else "role.created", role, changes, request)
        messages.success(request, "Rol saqlandi.")
        return redirect("crm:roles")
    return render(request, "boshqaruv/operations/roles/form.html", {"form": form, "role": role})


@require_cap("roles.manage")
def department_edit(request, pk=None):
    dept = get_object_or_404(Department, pk=pk) if pk else None
    form = DepartmentForm(request.POST or None, instance=dept)
    if request.method == "POST" and form.is_valid():
        changes = form_changes(form)
        dept = form.save()
        record(request.user, "department.saved", dept, changes, request)
        messages.success(request, "Bo'lim saqlandi.")
        return redirect("crm:roles")
    members = list(dept.members.exclude(status=User.Status.DEACTIVATED).select_related("role")) if dept else []
    return render(request, "boshqaruv/operations/roles/department_form.html", {
        "form": form, "department": dept, "members": members,
    })


@require_POST
@require_cap('roles.manage')
def role_status(request, pk):
    role = get_object_or_404(Role, pk=pk)
    deny_unless(people.can_edit_role(request.user, role) and role.pk != request.user.role_id)
    old = role.is_active
    role.is_active = not old
    role.save(update_fields=['is_active'])
    if not role.is_active:
        for employee in role.users.all():
            _end_sessions(employee)
    record(request.user, 'role.status', role, {'is_active': [old, role.is_active]}, request)
    messages.success(request, 'Rol faollashtirildi.' if role.is_active else 'Rol to‘xtatildi. Biriktirilgan hisoblar tizimdan chiqarildi.')
    return redirect('crm:roles')
