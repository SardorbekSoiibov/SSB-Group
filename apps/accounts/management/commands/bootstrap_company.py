"""Create the default security roles, departments and the founder account.

Safe to run repeatedly: existing roles and departments are left untouched.

    python manage.py bootstrap_company --username founder --first-name Ism --last-name Familiya
"""

import getpass
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Department, Role, User

C = {
    "exec": "dashboard.executive", "emp_v": "employees.view", "emp_m": "employees.manage", "roles": "roles.manage",
    "p_all": "projects.view_all", "p_new": "projects.create", "p_edit": "projects.edit", "p_assign": "projects.assign",
    "p_ok": "projects.approve", "p_arch": "projects.archive", "p_budget": "projects.budget", "review": "tasks.review",
    "cl_v": "clients.view", "cl_m": "clients.manage", "inq": "inquiries.manage", "cms": "cms.edit", "pub": "cms.publish",
    "ann": "announcements.manage", "fv": "finance.view", "fm": "finance.manage", "fa": "finance.approve", "fd": "finance.distribute",
    "ar": "archive.manage", "sc": "schedule.manage", "pv": "performance.view", "pm": "performance.manage", "dw": "dashboard.customize", "team": "team.manage", "set": "settings.manage", "audit": "audit.view",
}


def caps(*keys):
    return [C[k] for k in keys]


DEFAULT_ROLES = [
    # Faqat bitta Asoschi bor. Qolgan har bir xodimning huquqlari shaxsan belgilanadi (User.personal_role).
    {"name": "Asoschi", "rank": 0, "dashboard": "founder", "is_owner": True, "capabilities": [],
     "description": "Kompaniya rahbari. Barcha huquqlar."},
]

DEFAULT_DEPARTMENTS = ["Boshqaruv", "Tashqi qism", "Ichki qism", "UI/UX dizayn"]


class Command(BaseCommand):
    help = "Create default roles, departments and the founder account."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--first-name", default="")
        parser.add_argument("--last-name", default="")
        parser.add_argument("--email", default="")
        parser.add_argument("--no-input", action="store_true", help="Read the password from SSB_FOUNDER_PASSWORD.")

    @transaction.atomic
    def handle(self, *args, **opts):
        for spec in DEFAULT_ROLES:
            spec = dict(spec)
            name = spec.pop("name")
            is_owner = spec.pop("is_owner", False)
            role, created = Role.objects.get_or_create(name=name, defaults=spec)
            if is_owner and not role.is_owner:
                role.is_owner = True
                role.save(update_fields=["is_owner"])
            self.stdout.write(f"{'+' if created else '='} rol: {name}")
        for name in DEFAULT_DEPARTMENTS:
            Department.objects.get_or_create(name=name)

        owner_role = Role.objects.get(is_owner=True)
        if User.objects.filter(role=owner_role).exists():
            self.stdout.write(self.style.WARNING("Asoschi hisobi allaqachon mavjud — yangisi yaratilmadi."))
            return
        if User.objects.filter(username=opts["username"]).exists():
            raise CommandError("Bu login band.")

        if opts["no_input"]:
            password = os.environ.get("SSB_FOUNDER_PASSWORD", "")
        else:
            password = getpass.getpass("Asoschi paroli: ")
            if password != getpass.getpass("Parolni takrorlang: "):
                raise CommandError("Parollar mos emas.")
        user = User(
            username=opts["username"], first_name=opts["first_name"], last_name=opts["last_name"], email=opts["email"],
            role=owner_role, job_title="Asoschi", status=User.Status.ACTIVE, is_staff=True, is_superuser=True,
            department=Department.objects.filter(name="Boshqaruv").first(),
        )
        from django.contrib.auth.password_validation import validate_password

        validate_password(password, user)
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Asoschi hisobi yaratildi: {user.username}"))
