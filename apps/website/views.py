import logging

from django.conf import settings
from django.db.models import Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from apps.core import ratelimit
from apps.crm.services import notify_new_inquiry

from .cache import public_page
from .forms import InquiryForm
from .models import (
    Highlight, PortfolioCategory, PortfolioImage, PortfolioProject, PublicationStatus, Service, TeamMember, Technology,
    Testimonial,
)

log = logging.getLogger(__name__)


def _highlights(kind):
    return Highlight.objects.published().filter(kind=kind)


def _can_preview(request):
    return request.GET.get("preview") == "1" and request.user.is_authenticated and request.user.has_cap("cms.edit")


@public_page
def home(request):
    portfolio = PortfolioProject.objects.published().select_related("category").prefetch_related("technologies")
    return render(request, "website/home.html", {
        "services": Service.objects.published().prefetch_related("technologies"),
        "featured": list(portfolio.filter(featured=True)[:4]) or list(portfolio[:4]),
        "reasons": _highlights(Highlight.Kind.REASON),
        "process": _highlights(Highlight.Kind.PROCESS),
        "team": TeamMember.objects.published(),
        "testimonials": Testimonial.objects.published().select_related("project")[:3],
        "form": InquiryForm(),
        "technologies": Technology.objects.filter(
            Q(services__status=PublicationStatus.PUBLISHED) | Q(portfolio__status=PublicationStatus.PUBLISHED)
        ).distinct(),
    })


@public_page
def about(request):
    return render(request, "website/about.html", {
        "values": _highlights(Highlight.Kind.VALUE),
        "milestones": _highlights(Highlight.Kind.MILESTONE),
        "expertise": _highlights(Highlight.Kind.EXPERTISE),
        "team_count": TeamMember.objects.published().count(),
    })


@public_page
def services(request):
    items = Service.objects.published().prefetch_related("technologies")
    return render(request, "website/services.html", {"services": items})


@public_page
def service_detail(request, slug):
    qs = Service.objects.all() if _can_preview(request) else Service.objects.published()
    service = get_object_or_404(qs.prefetch_related("technologies"), slug=slug)
    related = service.portfolio.published().select_related("category")[:3]
    return render(request, "website/service_detail.html", {
        "service": service, "related": related, "preview": not service.is_published,
        "process": _highlights(Highlight.Kind.PROCESS),
    })


@public_page
def portfolio(request):
    projects = PortfolioProject.objects.published().select_related("category").prefetch_related("technologies")
    categories = PortfolioCategory.objects.filter(projects__status="published").distinct()
    active = request.GET.get("kategoriya", "")
    query = request.GET.get("q", "").strip()[:80]
    if active:
        projects = projects.filter(category__slug=active)
    if query:
        projects = projects.filter(
            Q(title__icontains=query) | Q(summary__icontains=query) | Q(technologies__name__icontains=query)
        ).distinct()
    template = "website/_portfolio_grid.html" if request.headers.get("HX-Request") else "website/portfolio.html"
    return render(request, template, {"projects": projects, "categories": categories, "active": active, "query": query})


@public_page
def project_detail(request, slug):
    qs = PortfolioProject.objects.all() if _can_preview(request) else PortfolioProject.objects.published()
    project = get_object_or_404(
        qs.select_related("category").prefetch_related("technologies", "services", Prefetch("images", PortfolioImage.objects.all())),
        slug=slug,
    )
    related = PortfolioProject.objects.published().exclude(pk=project.pk)
    if project.category_id:
        related = related.filter(category=project.category_id)
    return render(request, "website/project_detail.html", {
        "project": project,
        "related": related.select_related("category")[:3],
        "testimonial": project.testimonials.published().first(),
        "preview": not project.is_published,
    })


@public_page
def team(request):
    return render(request, "website/team.html", {"team": TeamMember.objects.published()})


def contact(request):
    initial = {}
    if request.GET.get("xizmat"):
        svc = Service.objects.published().filter(slug=request.GET["xizmat"]).first()
        initial["service"] = svc.pk if svc else None
    form = InquiryForm(request.POST or None, initial=initial)
    if request.method == "POST":
        ip = ratelimit.client_ip(request)
        if ratelimit.is_limited("inquiry", ip, settings.INQUIRY_RATE_LIMIT):
            form.add_error(None, "So'rovlar soni chegaradan oshdi. Birozdan keyin qayta urinib ko'ring yoki telefon orqali bog'laning.")
        elif form.is_spam():
            log.info("inquiry rejected as spam ip=%s", ip)
            return redirect("website:contact_done")
        elif form.is_valid():
            ratelimit.hit("inquiry", ip, settings.INQUIRY_RATE_LIMIT)
            inquiry = form.save()
            notify_new_inquiry(inquiry)
            log.info("inquiry created id=%s", inquiry.pk)
            return redirect("website:contact_done")
    return render(request, "website/contact.html", {"form": form})


def contact_done(request):
    return render(request, "website/contact_done.html")


@public_page
def privacy(request):
    return render(request, "website/privacy.html")


@require_GET
def robots_txt(request):
    lines = [
        "User-agent: *",
        "Disallow: /management/",
        "Disallow: /django-admin/",
        "Disallow: /xodim/",
        f"Sitemap: {settings.SITE_URL}/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


def not_found(request, exception=None):
    return render(request, "website/404.html", status=404)


def server_error(request):
    return render(request, "website/500.html", status=500)
