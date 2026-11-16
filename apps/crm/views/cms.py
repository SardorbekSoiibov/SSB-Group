"""Website content management inside the CRM."""

from functools import wraps

from django.contrib import messages
from django.db.models import ProtectedError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.audit.services import form_changes, record
from apps.website.forms import (
    CategoryForm, HighlightForm, PortfolioForm, PortfolioImageForm, ServiceForm, SiteSettingsForm, TeamMemberForm,
    TechnologyForm, TestimonialForm,
)
from apps.website.models import (
    Highlight, PortfolioCategory, PortfolioImage, PortfolioProject, PublicationStatus, Service, SiteSettings,
    TeamMember, Technology, Testimonial,
)

from .base import require_cap

KINDS = {
    "services": {"model": Service, "form": ServiceForm, "title": "Xizmatlar", "new": "Yangi xizmat", "public": True},
    "portfolio": {"model": PortfolioProject, "form": PortfolioForm, "title": "Portfolio", "new": "Yangi loyiha", "public": True},
    "team": {"model": TeamMember, "form": TeamMemberForm, "title": "Jamoa profillari", "new": "Yangi profil", "public": False},
    "testimonials": {"model": Testimonial, "form": TestimonialForm, "title": "Mijozlar fikrlari", "new": "Yangi fikr", "public": False},
    "highlights": {"model": Highlight, "form": HighlightForm, "title": "Sahifa bloklari", "new": "Yangi blok", "public": False},
    "categories": {"model": PortfolioCategory, "form": CategoryForm, "title": "Portfolio kategoriyalari", "new": "Yangi kategoriya", "public": False},
    "technologies": {"model": Technology, "form": TechnologyForm, "title": "Texnologiyalar", "new": "Yangi texnologiya", "public": False},
}


def _kind(kind):
    if kind not in KINDS:
        raise Http404
    spec = KINDS[kind]
    spec["publishable"] = hasattr(spec["model"], "status")
    return spec


def _team_manager(request, kind):
    return kind == "team" and (request.user.has_cap("team.manage") or request.user.has_cap("employees.manage"))


def require_content(capability):
    """Employee managers can manage public team profiles, without broader CMS access."""
    def decorator(view):
        @wraps(view)
        def wrapped(request, kind, *args, **kwargs):
            capability_for_kind = capability
            if kind == "team" and request.user.is_authenticated:
                if request.user.has_cap("team.manage"):
                    capability_for_kind = "team.manage"
                elif request.user.has_cap("employees.manage"):
                    capability_for_kind = "employees.manage"
            return require_cap(capability_for_kind)(view)(request, kind, *args, **kwargs)
        return wrapped
    return decorator


@require_cap("cms.edit")
def cms_index(request):
    sections = []
    for key, spec in KINDS.items():
        model = spec["model"]
        row = {"key": key, "title": spec["title"], "total": model.objects.count()}
        if hasattr(model, "status"):
            row["published"] = model.objects.filter(status=PublicationStatus.PUBLISHED).count()
            row["drafts"] = model.objects.filter(status=PublicationStatus.DRAFT).count()
        sections.append(row)
    drafts = list(PortfolioProject.objects.filter(status=PublicationStatus.DRAFT).order_by("-updated_at")[:5])
    return render(request, "boshqaruv/operations/cms/index.html", {"sections": sections, "drafts": drafts})


@require_cap("cms.edit")
def cms_site(request):
    site = SiteSettings.load()
    form = SiteSettingsForm(request.POST or None, request.FILES or None, instance=site)
    if request.method == "POST":
        if not request.user.has_cap("cms.publish"):
            messages.error(request, "Sayt sozlamalari darhol ommaga ko'rinadi, shuning uchun nashr huquqi kerak.")
        elif form.is_valid():
            changes = form_changes(form)
            form.save()
            record(request.user, "cms.saved", site, changes, request)
            messages.success(request, "Sayt sozlamalari saqlandi va saytda ko'rinadi.")
            return redirect("crm:cms_site")
    return render(request, "boshqaruv/operations/cms/site.html", {"form": form})


@require_content("cms.edit")
def cms_list(request, kind):
    spec = _kind(kind)
    qs = spec["model"].objects.all()
    status = request.GET.get("holat")
    if spec["publishable"] and status in PublicationStatus.values:
        qs = qs.filter(status=status)
    if kind == "highlights" and request.GET.get("turi"):
        qs = qs.filter(kind=request.GET["turi"])
    return render(request, "boshqaruv/operations/cms/list.html", {
        "kind": kind, "spec": spec, "items": qs, "status": status,
        "statuses": PublicationStatus.choices, "highlight_kinds": Highlight.Kind.choices,
        "can_publish": request.user.has_cap("cms.publish") or _team_manager(request, kind),
    })


@require_content("cms.edit")
def cms_edit(request, kind, pk=None):
    spec = _kind(kind)
    obj = get_object_or_404(spec["model"], pk=pk) if pk else None
    if obj is not None and spec["publishable"] and obj.is_published and not (request.user.has_cap("cms.publish") or _team_manager(request, kind)):
        messages.error(request, "Nashr qilingan kontentni o'zgartirish uchun nashr huquqi kerak.")
        return redirect("crm:cms_list", kind=kind)
    form = spec["form"](request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        changes = form_changes(form)
        obj = form.save()
        record(request.user, "cms.saved", obj, changes, request)
        messages.success(request, "Saqlandi." + (" Ommaga ko'rinishi uchun nashr qiling." if spec["publishable"] and not obj.is_published else ""))
        return redirect("crm:cms_edit", kind=kind, pk=obj.pk)
    images, image_form = None, None
    if kind == "portfolio" and obj:
        images = obj.images.all()
        image_form = PortfolioImageForm()
    return render(request, "boshqaruv/operations/cms/form.html", {
        "kind": kind, "spec": spec, "obj": obj, "form": form,
        "can_publish": request.user.has_cap("cms.publish") or _team_manager(request, kind),
        "images": images, "image_form": image_form,
        "portfolio_sections": [
            {"title": "Asosiy ma’lumotlar", "hint": "Loyiha nomi va kartochkada ko‘rinadigan qisqa tavsif.", "fields": [form[k] for k in ['title', 'category', 'summary']]},
            {"title": "Loyiha haqida", "hint": "Qanday vazifa bajarildi, yechim va natija nimadan iborat?", "fields": [form[k] for k in ['description', 'case_study', 'services', 'technologies']]},
            {"title": "Mijoz va natija", "hint": "Mijoz nomini faqat ruxsat bo‘lsa ochiq ko‘rsating.", "fields": [form[k] for k in ['client_name', 'show_client', 'project_state', 'completed_on', 'live_url']]},
            {"title": "Saytda ko‘rinishi", "hint": "Bosh sahifa, tartib va qidiruv tizimlari uchun tavsif.", "fields": [form[k] for k in ['featured', 'order', 'seo_description']]},
        ] if kind == 'portfolio' else [],
        "preview_url": (obj.get_absolute_url() + "?preview=1") if obj and spec["public"] else None,
    })


@require_POST
@require_content("cms.publish")
def cms_status(request, kind, pk):
    spec = _kind(kind)
    obj = get_object_or_404(spec["model"], pk=pk)
    action = request.POST.get("action")
    if action == "delete" and not spec["publishable"]:
        from apps.core.secure_delete import confirm_delete_password
        if not confirm_delete_password(request):
            return redirect("crm:cms_list", kind=kind)
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, "Bu yozuv boshqa kontentda ishlatilmoqda.")
            return redirect("crm:cms_list", kind=kind)
        record(request.user, "cms.publish", None, {"deleted": str(obj), "kind": kind}, request)
        messages.success(request, "O'chirildi.")
        return redirect("crm:cms_list", kind=kind)
    targets = {"publish": PublicationStatus.PUBLISHED, "unpublish": PublicationStatus.DRAFT, "archive": PublicationStatus.ARCHIVED}
    if not spec["publishable"] or action not in targets:
        raise Http404
    old = obj.status
    obj.set_status(targets[action])
    obj.save()
    record(request.user, "cms.publish", obj, {"status": [old, obj.status]}, request)
    labels = {"publish": "Nashr qilindi", "unpublish": "Nashrdan olindi", "archive": "Arxivlandi"}
    messages.success(request, f"{labels[action]}: {obj}.")
    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        next_url = reverse("crm:cms_list", args=[kind])
    return redirect(next_url)


@require_POST
@require_cap("cms.edit")
def cms_image_add(request, pk):
    project = get_object_or_404(PortfolioProject, pk=pk)
    form = PortfolioImageForm(request.POST, request.FILES)
    if project.is_published and not request.user.has_cap("cms.publish"):
        messages.error(request, "Nashr qilingan loyihani o'zgartirish uchun nashr huquqi kerak.")
    elif form.is_valid():
        img = form.save(commit=False)
        img.project = project
        img.save()
        record(request.user, "cms.saved", project, {"image_added": img.image.name}, request)
        messages.success(request, "Rasm qo'shildi.")
    else:
        for e in form.errors.get("image", []):
            messages.error(request, e)
    return redirect(reverse("crm:cms_edit", args=["portfolio", pk]) + "#galereya")


@require_POST
@require_cap("cms.edit")
def cms_image_delete(request, pk, image_pk):
    project = get_object_or_404(PortfolioProject, pk=pk)
    img = get_object_or_404(PortfolioImage, pk=image_pk, project=project)
    from apps.core.secure_delete import confirm_delete_password
    if project.is_published and not request.user.has_cap("cms.publish"):
        messages.error(request, "Nashr qilingan loyihani o'zgartirish uchun nashr huquqi kerak.")
    elif confirm_delete_password(request):
        img.image.delete(save=False)
        img.delete()
        record(request.user, "cms.saved", project, {"image_removed": image_pk}, request)
    return redirect(reverse("crm:cms_edit", args=["portfolio", pk]) + "#galereya")
