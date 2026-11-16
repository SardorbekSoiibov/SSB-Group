import re
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, F, OuterRef, Q, Subquery
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.clickjacking import xframe_options_sameorigin
from PIL import Image, UnidentifiedImageError
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.accounts.models import User
from apps.core.models import WorkspaceSettings
from apps.core.uploads import IMAGE_EXTENSIONS, validate_attachment
from apps.notifications.services import Kind, notify
from .models import REACTIONS, Message, Presence, Reaction

EDIT_WINDOW = timedelta(hours=48)
ONLINE_SECONDS = 45
TYPING_SECONDS = 6
IMAGE_TYPES = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp'}


def require_employee(user):
    if not user.is_active or user.status != User.Status.ACTIVE:
        raise PermissionDenied('Chat faqat faol xodimlar uchun.')


def active_staff():
    return User.objects.filter(is_active=True, status=User.Status.ACTIVE).filter(
        Q(role__is_active=True) | Q(role__isnull=True))


def conversation(user, peer):
    return Message.objects.filter(Q(sender=user, recipient=peer) | Q(sender=peer, recipient=user))


def peer_for(user, pk):
    # Any colleague can be opened from search; sending to an inactive account stays blocked in send().
    peer = get_object_or_404(User.objects.select_related('role'), pk=pk)
    if peer.pk == user.pk:
        raise Http404
    return peer


APOSTROPHES = "'`‘’ʻʼ"


def word_pattern(word):
    """o‘, o' and oʻ are all typed for the same Uzbek letter, so any of them matches."""
    return ''.join(f'[{APOSTROPHES}]' if char in APOSTROPHES else re.escape(char) for char in word)


def staff_search(queryset, text):
    # Each word may match a different field, so "Sardorbek Soyibov" and "asoschi sardorbek" both work.
    for word in text.split()[:6]:
        pattern = word_pattern(word)
        queryset = queryset.filter(Q(first_name__iregex=pattern) | Q(last_name__iregex=pattern) | Q(username__iregex=pattern) |
                                   Q(role__name__iregex=pattern) | Q(job_title__iregex=pattern) | Q(department__name__iregex=pattern))
    return queryset


def own_message(user, mid):
    """A message from one of the user's own conversations (never a third party's)."""
    item = get_object_or_404(Message.objects.select_related('sender', 'recipient'), pk=mid)
    if user.pk not in (item.sender_id, item.recipient_id):
        raise Http404
    return item


def public_person(person):
    return {'id': person.pk, 'name': person.display_name, 'role': person.job_title or str(person.role or 'Xodim'),
            'verified': person.is_verified,
            'photo': f"{reverse('crm:employee_photo', args=[person.pk])}?v={person.photo_version}" if person.photo else '',
            'active': person.is_active and person.status == User.Status.ACTIVE
                      and (not person.role_id or person.role.is_active)}


def presence_data(presence, viewer, now, person):
    if presence is None:
        return {'online': False, 'last_seen': person.last_login, 'typing': False}
    seen = max(filter(None, [presence.last_seen, person.last_login]))
    return {'online': presence.last_seen > now - timedelta(seconds=ONLINE_SECONDS), 'last_seen': seen,
            'typing': bool(presence.typing_to_id == viewer.pk and presence.typing_at
                           and presence.typing_at > now - timedelta(seconds=TYPING_SECONDS))}


def touch_presence(user):
    now = timezone.now()
    # At most one write per 15 seconds per user, however often the client polls.
    if not Presence.objects.filter(user=user, last_seen__lt=now - timedelta(seconds=15)).update(last_seen=now):
        Presence.objects.get_or_create(user=user, defaults={'last_seen': now})


def cursor_value(request, name):
    raw = request.query_params.get(name)
    if raw is None:
        return None
    if not raw.isascii() or not raw.isdigit() or len(raw) > 19 or int(raw) > 9223372036854775807:
        raise ValueError('Noto‘g‘ri xabar kursori.')
    return int(raw)


def id_value(raw):
    if raw in (None, ''):
        return None
    if isinstance(raw, bool):
        raise ValueError
    text = str(raw)
    if not text.isascii() or not text.isdigit() or len(text) > 19:
        raise ValueError
    return int(text)


def no_cache(data, status=200):
    response = Response(data, status=status)
    response['Cache-Control'] = 'no-store, private'
    return response


def preview(item):
    if item.deleted_at:
        return 'Xabar o‘chirildi'
    if item.body:
        return item.body[:100]
    if item.attachment:
        return ('🖼 Rasm' if item.attachment_image else '📎 ' + item.attachment_name)[:100]
    return ''


def serialize(item, user):
    deleted = item.deleted_at is not None
    counts = {}
    for reaction in item.reactions.all():
        entry = counts.setdefault(reaction.emoji, {'emoji': reaction.emoji, 'count': 0, 'mine': False})
        entry['count'] += 1
        entry['mine'] = entry['mine'] or reaction.user_id == user.pk
    reply = item.reply_to
    return {'id': item.pk, 'body': '' if deleted else item.body, 'mine': item.sender_id == user.pk,
            'client_id': str(item.client_id), 'created_at': item.created_at, 'read_at': item.read_at,
            'updated_at': item.updated_at, 'deleted': deleted, 'edited': bool(item.edited_at) and not deleted,
            'forwarded_from': '' if deleted else item.forwarded_from, 'pinned': bool(item.pinned_at) and not deleted,
            'editable': (not deleted and item.sender_id == user.pk and not item.forwarded_from
                         and timezone.now() - item.created_at < EDIT_WINDOW),
            'attachment': None if deleted or not item.attachment else {
                'name': item.attachment_name, 'size': item.attachment_size, 'image': item.attachment_image,
                'url': reverse('chat:file', args=[item.pk])},
            'reply_to': None if not reply else {'id': reply.pk, 'name': reply.sender.display_name,
                                                'mine': reply.sender_id == user.pk, 'preview': preview(reply)},
            'reactions': [] if deleted else list(counts.values())}


def with_details(queryset):
    return queryset.select_related('reply_to__sender').prefetch_related('reactions')


@login_required
@xframe_options_sameorigin
def index(request, pk=None):
    require_employee(request.user)
    peer = peer_for(request.user, pk) if pk else None
    # Chat panelning telefon oynasi (iframe) ichida ochilganda menyusiz, ixcham ko'rinish.
    embed = request.headers.get('Sec-Fetch-Dest') == 'iframe' or request.GET.get('embed') == '1'
    response = render(request, 'boshqaruv/chat/index.html', {
        'chat_peer': public_person(peer) if peer else None, 'chat_reactions': REACTIONS,
        'chat_upload_mb': WorkspaceSettings.load().upload_max_mb, 'chat_time_zone': settings.TIME_ZONE,
        'chat_embed': embed})
    response['Vary'] = 'Sec-Fetch-Dest'
    response['Cache-Control'] = 'no-store, private'
    return response


@api_view(['GET'])
def contacts(request):
    require_employee(request.user)
    user = request.user
    touch_presence(user)
    incoming = Message.objects.filter(sender=OuterRef('pk'), recipient=user, read_at__isnull=True)
    history = Message.objects.filter(Q(sender=user, recipient=OuterRef('pk')) | Q(sender=OuterRef('pk'), recipient=user))
    staff = User.objects.select_related('role').exclude(pk=user.pk).annotate(
        has_history=Exists(history),
        last_at=Subquery(history.order_by('-id').values('created_at')[:1]),
        last_id=Subquery(history.order_by('-id').values('id')[:1]),
        unread=Subquery(incoming.order_by().values('sender').annotate(n=Count('id')).values('n')[:1])
    )
    query = request.query_params.get('q', '').strip()[:100]
    if query:
        # Search covers everyone in the database, including founders and inactive accounts.
        staff = staff_search(staff, query)
    else:
        staff = staff.filter(Q(pk__in=active_staff().values('pk')) | Q(has_history=True))
    # PostgreSQL sorts NULL first for DESC: bring actual conversations to the top.
    staff = staff.order_by(F('last_at').desc(nulls_last=True), 'first_name', 'last_name', 'pk')
    rows = list(staff[:201])
    last = Message.objects.in_bulk([person.last_id for person in rows if person.last_id])
    presence = Presence.objects.in_bulk([person.pk for person in rows])
    now = timezone.now()
    total = user.chat_received.filter(read_at__isnull=True).count()
    items = []
    for person in rows[:200]:
        message = last.get(person.last_id)
        items.append({**public_person(person), **presence_data(presence.get(person.pk), user, now, person),
                      'unread': person.unread or 0, 'last': preview(message) if message else '',
                      'last_at': person.last_at, 'last_mine': bool(message and message.sender_id == user.pk),
                      'last_read': bool(message and message.read_at),
                      'url': reverse('chat:conversation', args=[person.pk])})
    return no_cache({'user': user.pk, 'unread': total, 'has_more': len(rows) > 200, 'items': items})


def attachment_details(upload):
    """Same type/size rules as task attachments; images are verified before being shown inline."""
    validate_attachment(upload, WorkspaceSettings.load())
    name = Path(upload.name.replace('\\', '/')).name[:200] or 'fayl'
    ext = Path(name).suffix.lower().lstrip('.')
    image = False
    if ext in IMAGE_EXTENSIONS:
        try:
            with Image.open(upload) as picture:
                picture.verify()
            image = True
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
            raise ValidationError('Rasm fayli buzilgan yoki rasm emas.')
        finally:
            upload.seek(0)
    return name, image


def deliver(sender, peer, item):
    notify([peer], Kind.CHAT, f'{sender.display_name} dan yangi xabar', body=preview(item)[:120],
           url=reverse('chat:conversation', args=[sender.pk]), dedupe_key=f'chat:{item.pk}')


@api_view(['GET', 'POST'])
def messages(request, pk):
    require_employee(request.user)
    peer = peer_for(request.user, pk)
    own = conversation(request.user, peer)
    if request.method == 'POST':
        return send(request, peer, own)
    started = timezone.now()
    touch_presence(request.user)
    query = request.query_params.get('q')
    if query is not None:
        query = query.strip()[:100]
        if len(query) < 2:
            return no_cache({'error': 'Qidiruv uchun kamida 2 ta belgi kiriting.'}, 400)
        found = own.filter(deleted_at__isnull=True).filter(Q(body__icontains=query) | Q(attachment_name__icontains=query))
        return no_cache({'user': request.user.pk, 'results': [
            {'id': item.pk, 'preview': preview(item), 'created_at': item.created_at, 'mine': item.sender_id == request.user.pk}
            for item in found.order_by('-pk')[:50]]})
    try:
        after, before, around = (cursor_value(request, name) for name in ('after', 'before', 'around'))
    except ValueError as error:
        return no_cache({'error': str(error)}, 400)
    if sum(value is not None for value in (after, before, around)) > 1:
        return no_cache({'error': 'Faqat bitta kursorni yuboring.'}, 400)
    detailed = with_details(own)
    if after is not None:
        batch = list(detailed.filter(pk__gt=after).order_by('pk')[:101])
        more = len(batch) > 100
        items = batch[:100]
    elif around is not None:
        if not own.filter(pk=around).exists():
            raise Http404
        older = list(detailed.filter(pk__lt=around).order_by('-pk')[:26])
        more = len(older) > 25
        items = list(reversed(older[:25])) + list(detailed.filter(pk__gte=around).order_by('pk')[:25])
    else:
        if before is not None:
            detailed = detailed.filter(pk__lt=before)
        batch = list(detailed.order_by('-pk')[:51])
        more = len(batch) > 50
        items = list(reversed(batch[:50]))
    changes = []
    since = request.query_params.get('since')
    if since:
        moment = parse_datetime(since)
        if moment is None:
            return no_cache({'error': 'Noto‘g‘ri vaqt kursori.'}, 400)
        changes = [serialize(item, request.user) for item in with_details(own.filter(updated_at__gt=moment)).order_by('-updated_at')[:200]]
    pinned = own.filter(pinned_at__isnull=False, deleted_at__isnull=True).order_by('-pinned_at').first()
    peer_data = {**public_person(peer), **presence_data(Presence.objects.filter(user=peer).first(), request.user, timezone.now(), peer)}
    return no_cache({'user': request.user.pk, 'peer': peer_data, 'has_more': more, 'server_time': started,
        'items': [serialize(item, request.user) for item in items], 'changes': changes,
        'pinned': {'id': pinned.pk, 'preview': preview(pinned)} if pinned else None,
        'read_through': Message.objects.filter(sender=request.user, recipient=peer, read_at__isnull=False)
                        .order_by('-pk').values_list('pk', flat=True).first() or 0})


def send(request, peer, own):
    raw = request.data.get('body', '')
    text = raw.strip() if isinstance(raw, str) else None
    upload = request.FILES.get('file')
    if text is None or len(text) > 4000 or '\x00' in text or (not text and not upload):
        return no_cache({'error': 'Xabar 1–4000 ta belgidan iborat bo‘lishi yoki fayl biriktirilishi kerak.'}, 400)
    try:
        client_id = uuid.UUID(str(request.data.get('client_id', '')))
    except (ValueError, AttributeError):
        return no_cache({'error': 'Xabar identifikatori noto‘g‘ri.'}, 400)
    upload_name = Path(upload.name.replace('\\', '/')).name[:200] if upload else ''

    def matches(item):
        return item.recipient_id == peer.pk and item.body == text and item.attachment_name == upload_name

    existing = with_details(Message.objects.filter(sender=request.user, client_id=client_id)).first()
    if existing:
        if not matches(existing):
            return no_cache({'error': 'Bu identifikator boshqa xabar uchun ishlatilgan.'}, 409)
        return no_cache({'item': serialize(existing, request.user)}, 200)
    if not public_person(peer)['active']:
        return no_cache({'error': 'Bu xodim hozir faol emas. Yangi xabar yuborib bo‘lmaydi.'}, 400)
    try:
        reply_id = id_value(request.data.get('reply_to'))
    except ValueError:
        return no_cache({'error': 'Javob berilayotgan xabar noto‘g‘ri.'}, 400)
    reply = own.filter(pk=reply_id).first() if reply_id else None
    if reply_id and not reply:
        return no_cache({'error': 'Javob berilayotgan xabar bu suhbatda topilmadi.'}, 400)
    image = False
    if upload:
        try:
            upload_name, image = attachment_details(upload)
        except ValidationError as error:
            return no_cache({'error': ' '.join(error.messages)}, 400)
    item = Message(sender=request.user, recipient=peer, body=text, client_id=client_id, reply_to=reply)
    if upload:
        item.attachment, item.attachment_name, item.attachment_size, item.attachment_image = upload, upload_name, upload.size, image
    try:
        with transaction.atomic():
            item.save()
            deliver(request.user, peer, item)
    except IntegrityError:
        if item.attachment and getattr(item.attachment, '_committed', False):
            item.attachment.delete(save=False)
        item = Message.objects.filter(sender=request.user, client_id=client_id).first()
        if not item:
            raise
        if not matches(item):
            return no_cache({'error': 'Bu identifikator boshqa xabar uchun ishlatilgan.'}, 409)
    Presence.objects.filter(user=request.user, typing_to=peer).update(typing_to=None, typing_at=None)
    return no_cache({'item': serialize(with_details(Message.objects.filter(pk=item.pk)).get(), request.user)}, 201)


@api_view(['POST'])
def forward(request, pk):
    require_employee(request.user)
    peer = peer_for(request.user, pk)
    if not public_person(peer)['active']:
        return no_cache({'error': 'Bu xodim hozir faol emas. Xabar yuborib bo‘lmaydi.'}, 400)
    try:
        source_id = id_value(request.data.get('message'))
        client_id = uuid.UUID(str(request.data.get('client_id', '')))
    except (ValueError, AttributeError):
        return no_cache({'error': 'Uzatiladigan xabar noto‘g‘ri.'}, 400)
    if source_id is None:
        return no_cache({'error': 'Uzatiladigan xabar noto‘g‘ri.'}, 400)
    source = own_message(request.user, source_id)
    if source.deleted_at:
        return no_cache({'error': 'O‘chirilgan xabarni uzatib bo‘lmaydi.'}, 400)
    existing = Message.objects.filter(sender=request.user, client_id=client_id).first()
    if existing:
        if existing.recipient_id != peer.pk:
            return no_cache({'error': 'Bu identifikator boshqa xabar uchun ishlatilgan.'}, 409)
        return no_cache({'item': serialize(with_details(Message.objects.filter(pk=existing.pk)).get(), request.user)}, 200)
    item = Message(sender=request.user, recipient=peer, body=source.body, client_id=client_id,
                   forwarded_from=(source.forwarded_from or source.sender.display_name)[:150])
    if source.attachment:
        # Each message owns its file, so deleting one copy never breaks another conversation.
        try:
            with source.attachment.open('rb') as handle:
                content = handle.read()
        except (FileNotFoundError, OSError):
            return no_cache({'error': 'Asl fayl topilmadi.'}, 400)
        item.attachment.save(source.attachment_name or 'fayl', ContentFile(content), save=False)
        item.attachment_name, item.attachment_size, item.attachment_image = source.attachment_name, source.attachment_size, source.attachment_image
    try:
        with transaction.atomic():
            item.save()
            deliver(request.user, peer, item)
    except IntegrityError:
        if item.attachment:
            item.attachment.delete(save=False)
        raise
    return no_cache({'item': serialize(with_details(Message.objects.filter(pk=item.pk)).get(), request.user)}, 201)


@api_view(['PATCH', 'DELETE'])
def message_detail(request, mid):
    require_employee(request.user)
    item = own_message(request.user, mid)
    if item.sender_id != request.user.pk:
        raise PermissionDenied('Faqat o‘z xabaringizni o‘zgartira olasiz.')
    if item.deleted_at:
        return no_cache({'error': 'Xabar allaqachon o‘chirilgan.'}, 400)
    if request.method == 'DELETE':
        with transaction.atomic():
            stored = item.attachment.name if item.attachment else ''
            item.body, item.attachment, item.attachment_name, item.attachment_size = '', '', '', 0
            item.attachment_image, item.forwarded_from, item.pinned_at, item.pinned_by = False, '', None, None
            item.deleted_at = timezone.now()
            item.touch('body', 'attachment', 'attachment_name', 'attachment_size', 'attachment_image',
                       'forwarded_from', 'pinned_at', 'pinned_by', 'deleted_at')
            item.reactions.all().delete()
            from apps.notifications.models import Notification
            Notification.objects.filter(recipient=item.recipient, dedupe_key=f'chat:{item.pk}').update(body='Xabar o‘chirildi')
            if stored:
                transaction.on_commit(lambda: item.attachment.storage.delete(stored))
        return no_cache({'item': serialize(with_details(Message.objects.filter(pk=item.pk)).get(), request.user)})
    raw = request.data.get('body')
    text = raw.strip() if isinstance(raw, str) else None
    if item.forwarded_from or timezone.now() - item.created_at >= EDIT_WINDOW:
        return no_cache({'error': 'Bu xabarni endi tahrirlab bo‘lmaydi.'}, 400)
    if text is None or len(text) > 4000 or '\x00' in text or (not text and not item.attachment):
        return no_cache({'error': 'Xabar 1–4000 ta belgidan iborat bo‘lishi kerak.'}, 400)
    if text != item.body:
        item.body, item.edited_at = text, timezone.now()
        item.touch('body', 'edited_at')
    return no_cache({'item': serialize(with_details(Message.objects.filter(pk=item.pk)).get(), request.user)})


@api_view(['POST'])
def react(request, mid):
    require_employee(request.user)
    item = own_message(request.user, mid)
    emoji = request.data.get('emoji')
    if item.deleted_at or not isinstance(emoji, str) or emoji not in REACTIONS:
        return no_cache({'error': 'Bu reaksiyani qo‘yib bo‘lmaydi.'}, 400)
    with transaction.atomic():
        current = Reaction.objects.select_for_update().filter(message=item, user=request.user).first()
        if current and current.emoji == emoji:
            current.delete()
        elif current:
            current.emoji = emoji
            current.save(update_fields=['emoji'])
        else:
            try:
                with transaction.atomic():
                    Reaction.objects.create(message=item, user=request.user, emoji=emoji)
            except IntegrityError:
                Reaction.objects.filter(message=item, user=request.user).update(emoji=emoji)
        item.touch()
    return no_cache({'item': serialize(with_details(Message.objects.filter(pk=item.pk)).get(), request.user)})


@api_view(['POST'])
def pin(request, mid):
    require_employee(request.user)
    item = own_message(request.user, mid)
    pinned = request.data.get('pinned')
    if item.deleted_at or not isinstance(pinned, bool):
        return no_cache({'error': 'Xabarni qadab bo‘lmaydi.'}, 400)
    item.pinned_at, item.pinned_by = (timezone.now(), request.user) if pinned else (None, None)
    item.touch('pinned_at', 'pinned_by')
    return no_cache({'item': serialize(with_details(Message.objects.filter(pk=item.pk)).get(), request.user)})


@api_view(['POST'])
def typing(request, pk):
    require_employee(request.user)
    peer = peer_for(request.user, pk)
    now = timezone.now()
    active = request.data.get('typing', True) is not False
    Presence.objects.update_or_create(user=request.user, defaults={
        'last_seen': now, 'typing_to': peer if active else None, 'typing_at': now if active else None})
    return no_cache({'ok': True})


@login_required
def attachment(request, mid):
    require_employee(request.user)
    item = own_message(request.user, mid)
    if item.deleted_at or not item.attachment:
        raise Http404
    try:
        handle = item.attachment.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404('Fayl topilmadi.')
    ext = Path(item.attachment_name).suffix.lower().lstrip('.')
    inline = item.attachment_image and ext in IMAGE_TYPES and request.GET.get('download') != '1'
    response = FileResponse(handle, as_attachment=not inline, filename=item.attachment_name,
                            content_type=IMAGE_TYPES[ext] if inline else 'application/octet-stream')
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "default-src 'none'; img-src 'self'; sandbox"
    return response


@api_view(['POST'])
def read(request, pk):
    require_employee(request.user)
    peer = peer_for(request.user, pk)
    through = request.data.get('through')
    if isinstance(through, bool) or not isinstance(through, int) or through < 0 or through > 9223372036854775807:
        return no_cache({'error': 'Noto‘g‘ri xabar identifikatori.'}, 400)
    if through and not conversation(request.user, peer).filter(pk=through).exists():
        raise Http404
    with transaction.atomic():
        changed = Message.objects.filter(sender=peer, recipient=request.user, pk__lte=through,
                                         read_at__isnull=True).update(read_at=timezone.now())
        # Only chat notices for messages actually displayed are acknowledged.
        from django.db.models import CharField, Value
        from django.db.models.functions import Cast, Concat
        ids = Message.objects.filter(sender=peer, recipient=request.user, pk__lte=through).annotate(
            notification_key=Concat(Value('chat:'), Cast('pk', output_field=CharField()))).values('notification_key')
        from apps.notifications.models import Notification
        Notification.objects.filter(recipient=request.user, kind=Kind.CHAT, read_at__isnull=True,
            dedupe_key__in=Subquery(ids)).update(read_at=timezone.now())
    return no_cache({'read': changed, 'unread': request.user.chat_received.filter(read_at__isnull=True).count()})
