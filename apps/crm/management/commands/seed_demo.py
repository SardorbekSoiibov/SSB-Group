"""Local demo data for trying the platform. Refuses to run unless DEBUG=True.

Creates sample employees (password: demo-parol-2026), a client, an inquiry, projects with tasks in
different states, and two sample portfolio entries with generated cover images.
Delete the database (or these records) before going live.
"""

import random
from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from apps.accounts.models import Department, Role, User
from apps.crm import services
from apps.crm.models import Client, Inquiry, Milestone, Project, Task, TaskReview
from apps.website.models import PortfolioCategory, PortfolioProject, PublicationStatus, Service, TeamMember, Technology

PASSWORD = "demo-parol-2026"

PEOPLE = [
    ("dilnoza", "Dilnoza", "Karimova", "Hammuassis", "Hammuassis", "Boshqaruv"),
    ("jasur", "Jasur", "Toshmatov", "CEO", "CEO", "Boshqaruv"),
    ("aziza", "Aziza", "Rahimova", "Direktor", "Operatsion direktor", "Boshqaruv"),
    ("bekzod", "Bekzod", "Aliyev", "Team Lead", "Backend team lead", "Backend"),
    ("madina", "Madina", "Yusupova", "Xodim", "Frontend dasturchi", "Frontend"),
    ("sardor", "Sardor", "Qodirov", "Xodim", "Backend dasturchi", "Backend"),
    ("nilufar", "Nilufar", "Ismoilova", "Xodim", "UI/UX dizayner", "UI/UX dizayn"),
]


def cover(seed, w=1600, h=1000):
    """Abstract product-mockup cover in the brand palette: gradient, dot grid, app window."""
    rnd = random.Random(seed)
    top, bottom = (23, 58, 51), (13, 36, 31)
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        d.line((0, y, w, y), fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    for gx in range(40, w, 48):
        for gy in range(40, h, 48):
            d.ellipse((gx - 2, gy - 2, gx + 2, gy + 2), fill=(52, 92, 82))
    # App window
    x0, y0, x1, y1 = w * 0.14, h * 0.18, w * 0.86, h * 0.92
    d.rounded_rectangle((x0, y0, x1, y1), radius=30, fill="#f6f6f4")
    d.rounded_rectangle((x0, y0, x1, y0 + 64), radius=30, fill="#e7e8e3")
    d.rectangle((x0, y0 + 34, x1, y0 + 64), fill="#e7e8e3")
    for i, c in enumerate(["#d9dbd5", "#d9dbd5", "#d9dbd5"]):
        d.ellipse((x0 + 30 + i * 30, y0 + 24, x0 + 46 + i * 30, y0 + 40), fill=c)
    # Sidebar
    sx = x0 + w * 0.16
    d.rectangle((x0, y0 + 64, sx, y1 - 30), fill="#eeefea")
    for i in range(5):
        yy = y0 + 110 + i * 54
        d.rounded_rectangle((x0 + 28, yy, sx - 28, yy + 20), radius=10, fill="#2f6d5f" if i == 0 else "#d9dbd5")
    # Stat cards
    cw = (x1 - sx - 40 * 4) / 3
    for i in range(3):
        cx = sx + 40 + i * (cw + 40)
        d.rounded_rectangle((cx, y0 + 104, cx + cw, y0 + 230), radius=18, fill="#ffffff", outline="#e3e4df", width=2)
        d.rounded_rectangle((cx + 24, y0 + 130, cx + 24 + cw * 0.35, y0 + 146), radius=8, fill="#d9dbd5")
        d.rounded_rectangle((cx + 24, y0 + 166, cx + 24 + cw * (0.45 + rnd.random() * 0.3), y0 + 200), radius=10, fill="#173a33")
    # Bar chart
    bx0, by1 = sx + 40, y1 - 70
    bars = 14
    bw = (x1 - 40 - bx0) / bars
    for i in range(bars):
        bh = (by1 - (y0 + 270)) * (0.25 + rnd.random() * 0.75)
        d.rounded_rectangle((bx0 + i * bw + 8, by1 - bh, bx0 + (i + 1) * bw - 8, by1), radius=10,
                            fill="#3d8377" if i % 4 == 1 else "#2f6d5f" if i % 3 == 0 else "#a9cfc5")
    buf = BytesIO()
    img.save(buf, "JPEG", quality=88)
    return ContentFile(buf.getvalue(), name=f"demo-{seed}.jpg")


class Command(BaseCommand):
    help = "Create demo data (DEBUG only)."

    @transaction.atomic
    def handle(self, *args, **opts):
        if not settings.DEBUG:
            raise CommandError("seed_demo faqat DJANGO_DEBUG=True bo'lganda ishlaydi.")
        if User.objects.filter(username="madina").exists():
            self.stdout.write(self.style.WARNING("Demo ma'lumotlar allaqachon bor."))
            return
        founder = User.objects.filter(role__is_owner=True).first()
        if not founder:
            raise CommandError("Avval bootstrap_company buyrug'ini ishga tushiring.")

        today = timezone.localdate()
        people = {}
        for username, first, last, role, title, dept in PEOPLE:
            u = User(username=username, first_name=first, last_name=last, role=Role.objects.get(name=role), job_title=title,
                     department=Department.objects.get(name=dept), status=User.Status.ACTIVE, joined_on=today - timedelta(days=200))
            u.set_password(PASSWORD)
            u.save()
            people[username] = u
        for name in ("madina", "sardor", "nilufar"):
            people[name].manager = people["bekzod"]
            people[name].skills = {"madina": ["JavaScript", "Tailwind CSS"], "sardor": ["Python", "Django"], "nilufar": ["Figma"]}[name]
            people[name].save()

        client = Client.objects.create(name="Akmal Nazarov", company="Shifo Med klinikasi", phone="+998 90 000 00 00",
                                       account_manager=people["aziza"])
        svc = Service.objects.filter(slug__isnull=False).first()
        Inquiry.objects.create(name="Lola Saidova", contact="@lola_s", preferred_method="telegram", service=svc,
                               description="Restoran uchun buyurtma qabul qiladigan Telegram bot va admin panel kerak. Ikki filial bor.",
                               budget="1k_5k")
        Inquiry.objects.create(name="Timur Ergashev", contact="timur@example.com", preferred_method="email",
                               description="Logistika kompaniyamiz uchun yuk tashish buyurtmalarini kuzatadigan CRM kerak.",
                               stage=Inquiry.Stage.DISCUSSION, assigned_to=people["aziza"], budget="5k_15k")

        crm = Project.objects.create(
            name="Klinika uchun CRM", description="Bemorlar yozuvi, shifokorlar jadvali va to'lovlar hisobi.", client=client,
            manager=people["bekzod"], department=Department.objects.get(name="Backend"), start_date=today - timedelta(days=30),
            deadline=today + timedelta(days=25), priority="high", status=Project.Status.IN_PROGRESS, budget=12000,
            created_by=founder)
        crm.members.set([people["madina"], people["sardor"], people["nilufar"]])
        Milestone.objects.create(project=crm, title="Dizayn tasdiqlandi", due_date=today - timedelta(days=12), is_done=True)
        Milestone.objects.create(project=crm, title="Beta versiya", due_date=today + timedelta(days=10))

        site = Project.objects.create(
            name="SSB Group korporativ sayti", description="Yangi sayt va 3D hero.", manager=people["madina"],
            department=Department.objects.get(name="Frontend"), start_date=today - timedelta(days=10),
            deadline=today + timedelta(days=5), priority="medium", status=Project.Status.UNDER_REVIEW, created_by=founder)
        site.members.set([people["nilufar"]])
        Project.objects.create(name="Logistika CRM (taklif bosqichi)", manager=people["aziza"], status=Project.Status.AWAITING_APPROVAL,
                               deadline=today + timedelta(days=60), created_by=people["aziza"])

        def task(project, title, who, status, days, prio="medium", creator=None):
            t = Task(project=project, title=title, assignee=who, deadline=today + timedelta(days=days), priority=prio,
                     acceptance_criteria="Kod ko'rib chiqilgan va testlar o'tadi.")
            services.create_task(creator or project.manager, t)
            if status != Task.Status.ASSIGNED:
                t.status = status
                if status == Task.Status.SUBMITTED:
                    t.submitted_at = timezone.now()
                if status == Task.Status.APPROVED:
                    t.approved_at = timezone.now() - timedelta(days=random.randint(1, 40))
                    TaskReview.objects.create(task=t, reviewer=project.manager, decision="approved")
                t.save()
            return t

        task(crm, "Bemorlar ro'yxati sahifasi", people["madina"], Task.Status.IN_PROGRESS, 4, "high")
        task(crm, "Shifokorlar jadvali API", people["sardor"], Task.Status.SUBMITTED, 2, "high")
        task(crm, "To'lovlar moduli", people["sardor"], Task.Status.ASSIGNED, -2, "critical")
        task(crm, "Qabul oynasi maketi", people["nilufar"], Task.Status.APPROVED, -8)
        task(crm, "Rollar va huquqlar", people["sardor"], Task.Status.APPROVED, -15)
        task(crm, "SMS eslatmalar integratsiyasi", people["madina"], Task.Status.BLOCKED, 8)
        task(site, "Portfolio sahifasi", people["madina"], Task.Status.APPROVED, -3)
        task(site, "Jamoa fotosuratlari", people["nilufar"], Task.Status.APPROVED, -1)

        cat_web, _ = PortfolioCategory.objects.get_or_create(name="Veb-saytlar")
        cat_crm, _ = PortfolioCategory.objects.get_or_create(name="CRM tizimlari")
        for i, (title, cat, summary, techs) in enumerate([
            ("Namuna: klinika boshqaruv tizimi", cat_crm, "Namuna loyiha. Bemorlar yozuvi, jadval va to'lovlarni bitta tizimga birlashtirish.", ["Django", "PostgreSQL"]),
            ("Namuna: restoran sayti va bot", cat_web, "Namuna loyiha. Menyu sayti va Telegram orqali buyurtma qabul qilish.", ["Telegram Bot API", "Tailwind CSS"]),
        ]):
            p = PortfolioProject(title=title, category=cat, summary=summary, description=summary, featured=True, order=i,
                                 completed_on=today - timedelta(days=30 * (i + 1)))
            p.cover.save(f"demo-{i}.jpg", cover(i), save=False)
            p.set_status(PublicationStatus.PUBLISHED)
            p.save()
            p.technologies.set(Technology.objects.filter(name__in=techs))

        for i, key in enumerate(["bekzod", "madina", "nilufar", "sardor"]):
            u = people[key]
            m = TeamMember(user=u, name=u.display_name, public_title=u.job_title, skills=", ".join(u.skills), order=i,
                           bio="Namuna profil — haqiqiy ma'lumot bilan almashtiring.")
            m.set_status(PublicationStatus.PUBLISHED)
            m.save()

        self.stdout.write(self.style.SUCCESS(f"Demo ma'lumotlar yaratildi. Barcha demo xodimlar paroli: {PASSWORD}"))
