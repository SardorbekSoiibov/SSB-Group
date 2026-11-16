"""Hamkorlar: faqat Asoschi qo'shadi, shartnomani yuklaydi va boshqaradi. Logolar barcha xodimlar bedjigida chiqadi."""

import mimetypes

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.audit.services import record
from apps.core.storage import private_storage

from .. import badges
from ..forms import PartnerForm
from ..models import Partner
from .base import deny_unless


def _drop_replaced(old_names, item):
    """Almashtirilgan eski logo/shartnoma fayllari tranzaksiya tugagach o'chiriladi."""
    stale = [name for name, field in old_names if name and name != getattr(item, field).name]
    if stale:
        transaction.on_commit(lambda: [private_storage.delete(n) for n in stale])


def _auto_id(pk):
    return f"p{pk or 'new'}_%s"


@login_required
def partner_list(request):
    deny_unless(request.user.is_owner)
    form = None
    edit_pk = None
    if request.method == "POST":
        pk = request.POST.get("partner")
        instance = get_object_or_404(Partner, pk=pk) if pk else None
        old = [(instance.logo.name, "logo"), (instance.contract.name, "contract")] if instance else []
        form = PartnerForm(request.POST, request.FILES, instance=instance, auto_id=_auto_id(pk))
        if form.is_valid():
            item = form.save(commit=False)
            if not instance:
                item.created_by = request.user
                item.order = (Partner.objects.order_by("-order").values_list("order", flat=True).first() or 0) + 1
            item.save()
            _drop_replaced(old, item)
            record(request.user, "partner.updated" if instance else "partner.created", item, {"name": item.name}, request)
            messages.success(request, f"«{item.name}» hamkori saqlandi." + (" Logosi endi barcha xodimlar bedjigida chiqadi." if item.show_on_badge else ""))
            return redirect("crm:partners")
        edit_pk = instance.pk if instance else "new"
        messages.error(request, "Hamkor saqlanmadi. Belgilangan maydonlarni tekshiring.")
    from .people import _badge_context

    partners = list(Partner.objects.all())
    rows = [(p, form if edit_pk == p.pk else PartnerForm(instance=p, auto_id=_auto_id(p.pk)), edit_pk == p.pk)
            for p in partners]
    return render(request, "boshqaruv/operations/partners.html", {
        "rows": rows, "partners": partners, "open_new": edit_pk == "new",
        "new_form": form if edit_pk == "new" else PartnerForm(auto_id=_auto_id(None)),
        "badge_count": sum(1 for p in partners if p.show_on_badge),
        "max_badge_partners": badges.MAX_BADGE_PARTNERS,
        **_badge_context(request, request.user),
    })


@require_POST
@login_required
def partner_toggle(request, pk):
    deny_unless(request.user.is_owner)
    item = get_object_or_404(Partner, pk=pk)
    item.show_on_badge = not item.show_on_badge
    item.save(update_fields=["show_on_badge", "updated_at"])
    record(request.user, "partner.updated", item, {"show_on_badge": item.show_on_badge}, request)
    messages.success(request, f"«{item.name}» logosi bedjikda " + ("ko‘rsatiladi." if item.show_on_badge else "endi ko‘rsatilmaydi."))
    return redirect("crm:partners")


@require_POST
@login_required
def partner_move(request, pk):
    deny_unless(request.user.is_owner)
    items = list(Partner.objects.all())
    index = next((i for i, p in enumerate(items) if p.pk == pk), None)
    if index is not None:
        step = -1 if request.POST.get("dir") == "up" else 1
        target = index + step
        if 0 <= target < len(items):
            items[index], items[target] = items[target], items[index]
            for order, p in enumerate(items, 1):
                if p.order != order:
                    Partner.objects.filter(pk=p.pk).update(order=order)
    return redirect("crm:partners")


@require_POST
@login_required
def partner_delete(request, pk):
    deny_unless(request.user.is_owner)
    from apps.core.secure_delete import confirm_delete_password

    item = get_object_or_404(Partner, pk=pk)
    if confirm_delete_password(request):
        record(request.user, "partner.deleted", item, {"name": item.name}, request)
        name = item.name
        item.delete()
        messages.success(request, f"«{name}» hamkori, logosi va shartnomasi o‘chirildi.")
    return redirect("crm:partners")


@login_required
def partner_logo(request, pk):
    """Logo bedjikda ko'rinadi, shuning uchun tizimga kirgan har bir xodimga ochiq."""
    item = get_object_or_404(Partner, pk=pk)
    if request.GET.get("badge"):  # bedjik uchun oq silueti
        try:
            resp = HttpResponse(badges.badge_logo_png(item), content_type="image/png")
        except Exception:  # noqa: BLE001 — qayta ishlab bo'lmasa, asl logo beriladi
            resp = FileResponse(item.logo.open("rb"), content_type=mimetypes.guess_type(item.logo.name)[0] or "image/png")
    else:
        resp = FileResponse(item.logo.open("rb"), content_type=mimetypes.guess_type(item.logo.name)[0] or "image/png")
    resp["Cache-Control"] = "private, max-age=604800"
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


@login_required
def partner_contract(request, pk):
    """Shartnoma — faqat Asoschiga."""
    deny_unless(request.user.is_owner)
    item = get_object_or_404(Partner, pk=pk)
    ext = item.contract_ext.lower()
    filename = item.contract_name or f"shartnoma-{item.pk}.{ext}"
    inline = ext in ("pdf", "png", "jpg", "jpeg", "webp")
    resp = FileResponse(item.contract.open("rb"), as_attachment=not inline, filename=filename,
                        content_type=mimetypes.guess_type(filename)[0] or "application/octet-stream")
    resp["Cache-Control"] = "private, no-store"
    resp["X-Content-Type-Options"] = "nosniff"
    record(request.user, "partner.contract_opened", item, {"name": item.name}, request)
    return resp
