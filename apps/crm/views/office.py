"""Clients, inquiries, announcements, notifications, settings and audit log."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.audit.services import ACTION_LABELS, form_changes, record
from apps.core.models import WorkspaceSettings, accent_validator
from apps.notifications.models import Notification
from apps.notifications.services import Kind, clear_notifications, notify

from .. import policies, services
from apps.core.dates import parse_filter_date as _parse_date
from ..forms import AnnouncementForm, ClientForm, InquiryNoteForm, InquiryUpdateForm, WorkspaceSettingsForm
from ..models import Announcement, AnnouncementImage, Client, Inquiry, InquiryNote
from .base import back, deny_unless, int_param, paginate, require_cap

# ------------------------------------------------------------------ clients


@login_required
def client_list(request):
    deny_unless(request.user.has_cap("clients.view") or request.user.has_cap("clients.manage")
                or Client.objects.filter(account_manager=request.user).exists())
    qs = policies.visible_clients(request.user).select_related("account_manager").annotate(
        project_count=Count("projects", distinct=True), inquiry_count=Count("inquiries", distinct=True))
    # annotate() Meta.ordering'ni bekor qiladi — saralashni explicit qilib beramiz,
    # aks holda paginatsiya betlar takrorlanmaydigan tartibda chiqadi.
    qs = qs.order_by("company", "name", "pk")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(company__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q))
    return render(request, "boshqaruv/operations/clients/list.html", {
        "page": paginate(request, qs), "can_manage": request.user.has_cap("clients.manage"),
    })


@require_cap("clients.manage")
def client_create(request):
    form = ClientForm(request.POST or None, initial={"account_manager": request.user})
    if request.method == "POST" and form.is_valid():
        client = form.save()
        record(request.user, "client.saved", client, form_changes(form), request)
        messages.success(request, "Mijoz qo'shildi.")
        return redirect(client)
    return render(request, "boshqaruv/operations/simple_form.html", {"form": form, "title": "Yangi mijoz", "back_url": reverse("crm:clients")})


@login_required
def client_detail(request, pk):
    client = get_object_or_404(policies.visible_clients(request.user), pk=pk)
    projects = policies.visible_projects(request.user).filter(client=client).with_progress()
    return render(request, "boshqaruv/operations/clients/detail.html", {
        "client": client,
        "projects": projects,
        "inquiries": policies.visible_inquiries(request.user).filter(client=client),
        "can_manage": policies.can_manage_client(request.user, client),
    })


@login_required
def client_edit(request, pk):
    client = get_object_or_404(policies.visible_clients(request.user), pk=pk)
    deny_unless(policies.can_manage_client(request.user, client))
    form = ClientForm(request.POST or None, instance=client)
    if request.method == "POST" and form.is_valid():
        changes = form_changes(form)
        form.save()
        record(request.user, "client.saved", client, changes, request)
        messages.success(request, "Mijoz saqlandi.")
        return redirect(client)
    return render(request, "boshqaruv/operations/simple_form.html", {"form": form, "title": str(client), "back_url": client.get_absolute_url()})


# ------------------------------------------------------------------ inquiries


@login_required
def inquiry_list(request):
    base = policies.visible_inquiries(request.user)
    deny_unless(request.user.has_cap("inquiries.manage") or base.exists())
    qs = base.select_related("service", "assigned_to")
    stage = request.GET.get("bosqich", "")
    if stage:
        qs = qs.filter(stage=stage)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(contact__icontains=q) | Q(description__icontains=q))
    if request.GET.get("meniki"):
        qs = qs.filter(assigned_to=request.user)
    counts = dict(base.values_list("stage").annotate(n=Count("pk")))
    pipeline = [{"value": v, "label": l, "count": counts.get(v, 0)} for v, l in Inquiry.Stage.choices]
    return render(request, "boshqaruv/operations/inquiries/list.html", {
        "page": paginate(request, qs), "pipeline": pipeline, "stage": stage, "today": timezone.localdate(),
    })


@login_required
def inquiry_detail(request, pk):
    inquiry = get_object_or_404(policies.visible_inquiries(request.user).select_related("service", "client", "assigned_to"), pk=pk)
    can_manage = policies.can_manage_inquiry(request.user, inquiry)
    can_assign = request.user.has_cap("inquiries.manage")
    form = InquiryUpdateForm(request.POST or None, instance=inquiry, can_assign=can_assign)
    if request.method == "POST":
        deny_unless(can_manage)
        if form.is_valid():
            changes = form_changes(form)
            previous = inquiry.assigned_to_id
            form.save()
            if changes:
                record(request.user, "inquiry.updated", inquiry, changes, request)
            if inquiry.assigned_to_id != previous:
                services.assign_inquiry(request.user, inquiry, inquiry.assigned_to)
            messages.success(request, "Murojaat yangilandi.")
            return redirect(inquiry)
    return render(request, "boshqaruv/operations/inquiries/detail.html", {
        "inquiry": inquiry,
        "form": form,
        "note_form": InquiryNoteForm(),
        "notes": inquiry.notes.select_related("author"),
        "can_manage": can_manage,
        "can_convert": policies.can_convert_inquiry(request.user, inquiry) and inquiry.stage != Inquiry.Stage.CONVERTED,
        "project": getattr(inquiry, "project", None),
        "history": AuditEvent.objects.filter(target_type="crm.inquiry", target_id=str(inquiry.pk)).select_related("actor")[:15],
    })


@require_POST
@login_required
def inquiry_note(request, pk):
    inquiry = get_object_or_404(policies.visible_inquiries(request.user), pk=pk)
    deny_unless(policies.can_manage_inquiry(request.user, inquiry))
    form = InquiryNoteForm(request.POST)
    if form.is_valid():
        InquiryNote.objects.create(inquiry=inquiry, author=request.user, body=form.cleaned_data["body"])
    return redirect(inquiry.get_absolute_url() + "#izohlar")


@require_POST
@login_required
def inquiry_convert(request, pk):
    inquiry = get_object_or_404(policies.visible_inquiries(request.user), pk=pk)
    try:
        project = services.convert_inquiry(request.user, inquiry, request)
    except services.WorkflowError as e:
        messages.error(request, str(e))
        return redirect(inquiry)
    messages.success(request, f"{project.code} loyihasi yaratildi. Jamoa va muddatlarni belgilang.")
    return redirect("crm:project_edit", project.pk)


# ------------------------------------------------------------------ announcements


@login_required
def announcements(request):
    """Hackaton e'lonlari. Yozish: e'lon huquqi berilganlar va lavozimi hackaton bilan bog'liq xodimlar."""
    from apps.notifications.channels import telegram_configured
    from apps.notifications.models import TelegramChannel

    can_post = request.user.has_cap("announcements.manage")
    channel_count = TelegramChannel.objects.count() if can_post and telegram_configured() else 0
    form = AnnouncementForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        deny_unless(can_post)
        if form.is_valid():
            a = form.save(commit=False)
            a.author = request.user
            a.save()
            images = form.cleaned_data.get("images") or []
            for index, upload in enumerate(images):
                AnnouncementImage.objects.create(announcement=a, image=upload, order=index)
            record(request.user, "announcement.created", a,
                   {"title": a.title, "images": len(images), "link": a.link_url, "telegram": form.cleaned_data.get("telegram")}, request)
            summary = " · ".join(x for x in [a.event_date and f"📅 {a.event_date:%d.%m.%Y}", a.location, a.prize and f"🎁 {a.prize}"] if x)
            notify(User.objects.filter(status=User.Status.ACTIVE), Kind.ANNOUNCEMENT, f"Hackaton: {a.title}",
                   body=(summary + "\n" if summary else "") + a.body[:200],
                   url=reverse("crm:announcements"), dedupe_key=f"announcement:{a.pk}", exclude=request.user)
            text = "Hackaton e’loni chop etildi va jamoaga bildirishnoma yuborildi."
            if form.cleaned_data.get("telegram") and channel_count:
                from apps.notifications.bot import post_announcement
                sent, failed = post_announcement(a)
                if sent:
                    text += f" Telegram: {', '.join(sent)}."
                if failed:
                    messages.warning(request, f"Telegram kanalga yuborilmadi: {', '.join(failed)}. Bot kanalda admin ekanini tekshiring.")
            messages.success(request, text)
            return redirect("crm:announcements")
    return render(request, "boshqaruv/operations/announcements.html", {
        "page": paginate(request, Announcement.objects.select_related("author").prefetch_related("images"), 15),
        "form": form if can_post else None,
        "channel_count": channel_count,
    })


@login_required
@require_POST
def announcement_delete(request, pk):
    """E'lonni uni joylagan muallif (yoki direktor) o'chiradi. Rasmlar fayllari bilan birga o'chadi."""
    item = get_object_or_404(Announcement, pk=pk)
    deny_unless(item.author_id == request.user.pk or request.user.is_owner)
    title = item.title
    record(request.user, "announcement.deleted", item, {"title": title, "images": item.images.count()}, request)
    item.delete()
    messages.success(request, "Hackaton e’loni o‘chirildi.")
    return redirect("crm:announcements")


@login_required
def announcement_image(request, pk):
    """E'lon rasmi: faqat e'lonlarni ko'ra oladigan xodimlarga, shaxsiy xotiradan."""
    deny_unless(request.user.has_cap("announcements.view") or request.user.has_cap("announcements.manage"))
    item = get_object_or_404(AnnouncementImage, pk=pk)
    resp = FileResponse(item.image.open("rb"))
    resp["Cache-Control"] = "private, max-age=86400"
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


# ------------------------------------------------------------------ notifications


@login_required
def notification_list(request):
    qs = request.user.notifications.all()
    if request.GET.get("oqilmagan"):
        qs = qs.filter(read_at__isnull=True)
    return render(request, "boshqaruv/operations/notifications.html", {
        "page": paginate(request, qs, 30), "total_count": request.user.notifications.count()})


@require_POST
@login_required
def notification_open(request, pk):
    n = get_object_or_404(Notification, pk=pk, recipient=request.user)
    if not n.read_at:
        n.read_at = timezone.now()
        n.save(update_fields=["read_at"])
    return redirect(n.safe_url)


@require_POST
@login_required
def notification_read_all(request):
    request.user.notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
    messages.success(request, "Barcha bildirishnomalar o'qildi deb belgilandi.")
    return back(request, reverse("crm:notifications"))


@require_POST
@login_required
def notification_clear(request):
    """Permanently removes the signed-in person's own notifications, after the password step."""
    from apps.core.secure_delete import confirm_delete_password

    if confirm_delete_password(request):
        count = clear_notifications(request.user)
        record(request.user, "notifications.cleared", request.user, {"count": count}, request)
        messages.success(request, f"{count} ta bildirishnoma tozalandi.")
    return redirect("crm:notifications")


# ------------------------------------------------------------------ settings & audit


@require_cap("settings.manage")
def workspace_settings(request):
    ws = WorkspaceSettings.load()
    form = WorkspaceSettingsForm(request.POST or None, instance=ws)
    if request.method == "POST" and form.is_valid():
        changes = form_changes(form)
        form.save()
        record(request.user, "settings.updated", ws, changes, request)
        messages.success(request, "Sozlamalar saqlandi.")
        return redirect("crm:settings")
    from apps.notifications.channels import status as channel_status
    email_state = channel_status('email')
    email_connected = email_state['connected']
    telegram_connected = channel_status('telegram')['connected']
    integrations = [
        {"name": "Email yuborish", "icon": "bell", "connected": email_connected,
         "hint": "Xatlar pochta serveri orqali yuboriladi." if email_connected
         else ("Sozlamalar kiritilgan. Ulanishni tekshiring." if email_state['configured'] else "Hozir xatlar yuborilmaydi. Pochta serverini ulash kerak.")},
        {"name": "Telegram bildirishnomalari", "icon": "chat", "connected": telegram_connected,
         "hint": "Bot ulanishi tekshirilgan. Shaxsiy hisobingizni ulang." if telegram_connected else "Botni sozlang va ulanishini tekshiring."},
    ]
    # A fresh copy: validating the form changes its instance, and rejected values must not look saved.
    return render(request, "boshqaruv/operations/settings.html",
                  {"form": form, "integrations": integrations, "current": WorkspaceSettings.load()})


@login_required
@require_POST
def workspace_accent(request):
    """Boshqaruv panelining asosiy rangi. Butun kompaniya uchun bitta; faqat direktor (Asoschi) o'zgartiradi."""
    deny_unless(request.user.is_owner)
    value = (request.POST.get("accent") or "").strip().lower()
    wants_json = "application/json" in request.headers.get("Accept", "")
    try:
        accent_validator(value)
    except ValidationError:
        if wants_json:
            return JsonResponse({"error": "Rang #RRGGBB ko‘rinishida bo‘lishi kerak."}, status=400)
        messages.error(request, "Rang #RRGGBB ko‘rinishida bo‘lishi kerak.")
        return back(request, reverse("enterprise:overview"))
    ws = WorkspaceSettings.load()
    old = ws.accent_color
    if value != old:
        ws.accent_color = value
        ws.save(update_fields=["accent_color"])
        record(request.user, "settings.accent", ws, {"accent_color": [old, value]}, request)
    if wants_json:
        return JsonResponse({"accent": value})
    messages.success(request, "Asosiy rang saqlandi.")
    return back(request, reverse("enterprise:overview"))


@require_cap("audit.view")
def audit_log(request):
    qs = AuditEvent.objects.select_related("actor")
    g = request.GET
    if g.get("amal"):
        qs = qs.filter(action=g["amal"])
    if int_param(request, "xodim"):
        qs = qs.filter(actor=int_param(request, "xodim"))
    if g.get("q"):
        qs = qs.filter(Q(target_repr__icontains=g["q"]) | Q(action__icontains=g["q"]))
    if _parse_date(g.get("dan")):
        qs = qs.filter(created_at__date__gte=_parse_date(g["dan"]))
    if _parse_date(g.get("gacha")):
        qs = qs.filter(created_at__date__lte=_parse_date(g["gacha"]))
    from apps.audit.services import CLEAR_PERIODS

    return render(request, "boshqaruv/operations/audit.html", {
        "page": paginate(request, qs, 40),
        "actions": sorted(ACTION_LABELS.items(), key=lambda x: x[1]),
        "labels": ACTION_LABELS,
        "actors": User.objects.filter(audit_events__isnull=False).distinct(),
        "clear_periods": [(key, label) for key, (_days, label) in CLEAR_PERIODS.items()],
    })


@require_POST
@login_required
def audit_clear(request):
    """Audit tarixini tozalash — faqat asoschi, parol bilan tasdiqlanadi; tozalashning o'zi jurnalga yoziladi."""
    from apps.audit.services import CLEAR_PERIODS, clear_events
    from apps.core.secure_delete import confirm_delete_password

    deny_unless(request.user.is_owner)
    period = request.POST.get("davr", "")
    if period not in CLEAR_PERIODS:
        messages.error(request, "Tozalash davri noto‘g‘ri tanlangan. Hech narsa o‘chirilmadi.")
        return redirect("crm:audit")
    if not confirm_delete_password(request):
        return redirect("crm:audit")
    count = clear_events(request.user, period, request)
    if count:
        messages.success(request, f"Audit tarixidan {count} ta yozuv o‘chirildi. Tozalash jurnalga qayd etildi.")
    else:
        messages.info(request, "Tanlangan davrda o‘chiriladigan yozuv topilmadi.")
    return redirect("crm:audit")
