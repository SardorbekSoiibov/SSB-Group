"""Jihozlar: Asoschi barcha ofis jihozlarini ro'yxatga oladi, xodimlarga biriktiradi va nazorat qiladi.

Xodim faqat o'ziga biriktirilgan jihozlarni ko'radi: ularni "qabul qildim" deb tasdiqlaydi
(javobgarlikni o'z zimmasiga oladi) va nosozlik bo'lsa xabar beradi.
"""
import mimetypes

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.audit.services import record
from apps.core.storage import private_storage
from apps.notifications.services import Kind, notify

from ..forms import EquipmentAssignForm, EquipmentForm, EquipmentStatusForm
from ..models import Equipment, EquipmentEvent
from .base import deny_unless, paginate

E = Equipment


def _founders():
    return [u for u in User.objects.filter(is_active=True).select_related("role") if u.is_owner]


def _visible(user):
    qs = Equipment.objects.select_related("holder", "holder__department")
    return qs if user.is_owner else qs.filter(holder=user)


def _log(item, kind, actor, person=None, note=""):
    EquipmentEvent.objects.create(equipment=item, kind=kind, actor=actor, person=person, note=note[:500])


def _assign(item, holder, actor, condition=None, note=""):
    """Bitta joyda: eski egasidan qaytarish, yangisiga biriktirish, tarix va bildirishnomalar."""
    previous = item.holder
    if previous == holder and condition in (None, item.condition):
        return False
    if condition:
        item.condition = condition
    if previous and previous != holder:
        _log(item, EquipmentEvent.Kind.RETURNED, actor, previous, note)
        notify([previous], Kind.EQUIPMENT, f"Jihoz sizdan qaytarib olindi: {item.name}",
               body=item.inventory_number, url=item.get_absolute_url(), exclude=actor)
    item.holder = holder
    if holder and holder != previous:
        item.assigned_at = timezone.now()
        item.acknowledged_at = None
        if item.status in (E.Status.AVAILABLE, E.Status.REPAIR):
            item.status = E.Status.IN_USE
        _log(item, EquipmentEvent.Kind.ASSIGNED, actor, holder, note)
        notify([holder], Kind.EQUIPMENT, f"Sizga jihoz biriktirildi: {item.name}",
               body=f"{item.inventory_number} · Butligi va to‘g‘ri ishlatilishiga siz javobgarsiz. Qabul qilganingizni tasdiqlang.",
               url=item.get_absolute_url(), exclude=actor)
    elif not holder:
        item.assigned_at = None
        item.acknowledged_at = None
        if item.status == E.Status.IN_USE:
            item.status = E.Status.AVAILABLE
    item.save()
    return True


@login_required
def equipment_list(request):
    user = request.user
    qs = _visible(user)
    owner = user.is_owner
    q = request.GET.get("q", "").strip()
    status = request.GET.get("holat", "")
    category = request.GET.get("tur", "")
    holder = request.GET.get("xodim", "")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(inventory_number__icontains=q) | Q(serial_number__icontains=q)
                       | Q(holder__first_name__icontains=q) | Q(holder__last_name__icontains=q) | Q(location__icontains=q))
    if status in E.Status.values:
        qs = qs.filter(status=status)
    if category in E.Category.values:
        qs = qs.filter(category=category)
    if owner and holder == "yoq":
        qs = qs.filter(holder__isnull=True)
    elif owner and holder.isdigit():
        qs = qs.filter(holder_id=int(holder))

    form = EquipmentForm()
    if request.method == "POST":
        deny_unless(owner)
        form = EquipmentForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                item = form.save()
                _log(item, EquipmentEvent.Kind.CREATED, user)
                person = form.cleaned_data.get("holder")
                if person:
                    _assign(item, person, user)
                record(user, "equipment.created", item, {"name": item.name, "holder": person.display_name if person else ""}, request)
            messages.success(request, f"«{item.name}» ro‘yxatga olindi ({item.inventory_number})."
                             + (f" {person.display_name} ga biriktirildi va xabar yuborildi." if person else ""))
            return redirect(item.get_absolute_url())
        messages.error(request, "Jihoz saqlanmadi. Belgilangan maydonlarni tekshiring.")

    stats = None
    people = []
    if owner:
        all_items = Equipment.objects.all()
        counts = dict(all_items.values_list("status").annotate(n=Count("pk")))
        stats = {
            "total": sum(counts.values()), "in_use": counts.get(E.Status.IN_USE, 0),
            "available": counts.get(E.Status.AVAILABLE, 0),
            "attention": counts.get(E.Status.REPAIR, 0) + counts.get(E.Status.BROKEN, 0) + counts.get(E.Status.LOST, 0),
            "unacked": all_items.filter(holder__isnull=False, acknowledged_at__isnull=True).count(),
        }
        people = (User.objects.filter(equipment__isnull=False).distinct()
                  .annotate(n=Count("equipment")).order_by("first_name", "last_name"))
    return render(request, "boshqaruv/operations/equipment/list.html", {
        "page": paginate(request, qs.order_by("-updated_at", "-pk"), 30), "form": form, "is_manager": owner,
        "stats": stats, "people": people, "statuses": E.Status.choices, "categories": E.Category.choices,
        "filters": {"q": q, "holat": status, "tur": category, "xodim": holder},
        "open_create": request.method == "POST",
    })


@login_required
def equipment_detail(request, pk):
    item = get_object_or_404(_visible(request.user), pk=pk)
    owner = request.user.is_owner
    edit_form = EquipmentForm(instance=item) if owner else None
    if request.method == "POST":
        deny_unless(owner)
        edit_form = EquipmentForm(request.POST, request.FILES, instance=item)
        old_photo = item.photo.name
        if edit_form.is_valid():
            changed = [edit_form.fields[f].label for f in edit_form.changed_data]
            item = edit_form.save()
            if old_photo and old_photo != item.photo.name:
                transaction.on_commit(lambda: private_storage.delete(old_photo))
            if changed:
                _log(item, EquipmentEvent.Kind.EDITED, request.user, note=", ".join(str(c) for c in changed))
            record(request.user, "equipment.updated", item, {"fields": edit_form.changed_data}, request)
            messages.success(request, "Jihoz ma’lumotlari saqlandi.")
            return redirect(item.get_absolute_url())
        messages.error(request, "Saqlanmadi. Belgilangan maydonlarni tekshiring.")
    return render(request, "boshqaruv/operations/equipment/detail.html", {
        "item": item, "is_manager": owner, "edit_form": edit_form,
        "assign_form": EquipmentAssignForm(initial={"holder": item.holder_id, "condition": item.condition}) if owner else None,
        "status_form": EquipmentStatusForm(initial={"status": item.status}) if owner else None,
        "events": item.events.select_related("actor", "person")[:50],
        "is_holder": item.holder_id == request.user.pk,
        "open_edit": request.method == "POST",
    })


@require_POST
@login_required
def equipment_assign(request, pk):
    deny_unless(request.user.is_owner)
    item = get_object_or_404(Equipment, pk=pk)
    form = EquipmentAssignForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Biriktirib bo‘lmadi: " + " ".join(e for errs in form.errors.values() for e in errs))
        return redirect(item.get_absolute_url())
    holder = form.cleaned_data["holder"]
    if holder and item.status in (E.Status.RETIRED, E.Status.LOST):
        messages.error(request, "Hisobdan chiqarilgan yoki yo‘qolgan jihozni biriktirib bo‘lmaydi. Avval holatini o‘zgartiring.")
        return redirect(item.get_absolute_url())
    with transaction.atomic():
        previous = item.holder
        if _assign(item, holder, request.user, form.cleaned_data["condition"], form.cleaned_data["note"]):
            record(request.user, "equipment.assigned", item,
                   {"from": previous.display_name if previous else "", "to": holder.display_name if holder else ""}, request)
    if holder:
        messages.success(request, f"«{item.name}» {holder.display_name} ga biriktirildi. Xodimga bildirishnoma yuborildi.")
    else:
        messages.success(request, f"«{item.name}» omborga qaytarildi.")
    return redirect(item.get_absolute_url())


@require_POST
@login_required
def equipment_status(request, pk):
    deny_unless(request.user.is_owner)
    item = get_object_or_404(Equipment, pk=pk)
    form = EquipmentStatusForm(request.POST)
    if form.is_valid() and form.cleaned_data["status"] != item.status:
        old = item.get_status_display()
        with transaction.atomic():
            item.status = form.cleaned_data["status"]
            if item.status in (E.Status.RETIRED, E.Status.LOST) and item.holder:
                _assign(item, None, request.user, note="Holat: " + item.get_status_display())
                item.status = form.cleaned_data["status"]
            item.save()
            _log(item, EquipmentEvent.Kind.STATUS, request.user, note=f"{old} → {item.get_status_display()}. {form.cleaned_data['note']}".strip(". "))
            record(request.user, "equipment.status", item, {"status": item.status}, request)
            if item.holder:
                notify([item.holder], Kind.EQUIPMENT, f"Jihoz holati: {item.name} — {item.get_status_display()}",
                       body=form.cleaned_data["note"], url=item.get_absolute_url(), exclude=request.user)
        messages.success(request, f"Holat o‘zgardi: {item.get_status_display()}.")
    return redirect(item.get_absolute_url())


@require_POST
@login_required
def equipment_acknowledge(request, pk):
    item = get_object_or_404(Equipment, pk=pk, holder=request.user)
    if not item.acknowledged_at:
        with transaction.atomic():
            item.acknowledged_at = timezone.now()
            item.save(update_fields=["acknowledged_at", "updated_at"])
            _log(item, EquipmentEvent.Kind.ACKNOWLEDGED, request.user, request.user,
                 "Jihozni qabul qildim, butligi va to‘g‘ri ishlatilishiga javobgarman.")
            notify(_founders(), Kind.EQUIPMENT, f"{request.user.display_name} jihozni qabul qildi: {item.name}",
                   body=item.inventory_number, url=item.get_absolute_url(), exclude=request.user)
        messages.success(request, "Rahmat! Jihozni qabul qilganingiz qayd etildi.")
    return redirect(item.get_absolute_url())


@require_POST
@login_required
def equipment_issue(request, pk):
    item = get_object_or_404(_visible(request.user), pk=pk)
    deny_unless(item.holder_id == request.user.pk or request.user.is_owner)
    text = request.POST.get("note", "").strip()[:500]
    if not text:
        messages.error(request, "Muammoni qisqacha yozing.")
        return redirect(item.get_absolute_url())
    with transaction.atomic():
        _log(item, EquipmentEvent.Kind.ISSUE, request.user, request.user, text)
        notify(_founders(), Kind.EQUIPMENT, f"Jihozda muammo: {item.name}",
               body=f"{request.user.display_name}: {text[:180]}", url=item.get_absolute_url(), exclude=request.user)
    messages.success(request, "Muammo Asoschiga yuborildi.")
    return redirect(item.get_absolute_url())


@require_POST
@login_required
def equipment_delete(request, pk):
    deny_unless(request.user.is_owner)
    from apps.core.secure_delete import confirm_delete_password

    item = get_object_or_404(Equipment, pk=pk)
    if not confirm_delete_password(request):
        return redirect(item.get_absolute_url())
    record(request.user, "equipment.deleted", item, {"name": item.name, "inventory": item.inventory_number}, request)
    name = item.name
    item.delete()
    messages.success(request, f"«{name}» va uning tarixi o‘chirildi.")
    return redirect("crm:equipment")


@login_required
def equipment_photo(request, pk):
    item = get_object_or_404(_visible(request.user), pk=pk)
    if not item.photo:
        raise Http404
    resp = FileResponse(item.photo.open("rb"), content_type=mimetypes.guess_type(item.photo.name)[0] or "image/jpeg")
    resp["Cache-Control"] = "private, max-age=604800"
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


def holder_equipment(user):
    """Profil va xodim sahifasi uchun: shu xodimga biriktirilgan jihozlar."""
    return list(Equipment.objects.filter(holder=user).order_by("acknowledged_at", "name"))
