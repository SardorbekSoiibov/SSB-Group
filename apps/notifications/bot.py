"""SSB Group Telegram boti.

Hamma uchun: /start — salomlashish, hisobni ulash (/start <kod>), boshqaruv paneliga tugma, /id.
Adminlar uchun (TELEGRAM_ADMIN_IDS yoki bot orqali qo'shilganlar): ⚙️ Admin panel —
  📝 Post yuborish: kanal tanlash → matn/rasm/video → "Tugma qo'shilsinmi?" → nom + havola → ko'rib chiqish → yuborish
  📡 Kanallar: ro'yxat, qo'shish (forward, @username yoki botni kanalga admin qilish orqali avtomatik), o'chirish
  👥 Adminlar: ro'yxat, ID orqali qo'shish, o'chirish (asosiy adminlarni bot orqali o'chirib bo'lmaydi)
"""
import hashlib
import html
import logging
import re
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .channels import fingerprint, telegram_call
from .configuration import value
from .models import TelegramAdmin, TelegramBotState, TelegramChannel, TelegramConnection, TelegramPost

logger = logging.getLogger(__name__)
ALLOWED_UPDATES = ['message', 'callback_query', 'my_chat_member']
STATE_TTL = timedelta(hours=12)
_me = {}


# ------------------------------------------------------------------ yordamchilar

def esc(text):
    return html.escape(str(text or ''), quote=False)


def owner_ids():
    raw = value('TELEGRAM_ADMIN_IDS', settings.TELEGRAM_ADMIN_IDS) or ''
    return {int(x) for x in re.findall(r'-?\d{5,20}', raw)}


def is_owner(uid):
    return uid in owner_ids()


def is_admin(uid):
    return is_owner(uid) or TelegramAdmin.objects.filter(telegram_id=uid).exists()


def bot_me():
    token_print = fingerprint('telegram')
    if _me.get('fp') != token_print:
        _me.clear()
        _me.update(telegram_call('getMe'), fp=token_print)
    return _me


def public_site():
    """Telegram tugmasi uchun havola: faqat haqiqiy domen (localhost tugmalarini Telegram rad etadi)."""
    base = (value('SITE_URL', settings.SITE_URL) or '').rstrip('/')
    parts = urlsplit(base)
    host = (parts.hostname or '').lower()
    if parts.scheme in ('http', 'https') and '.' in host and host not in ('127.0.0.1',) and not host.endswith('.local'):
        return base
    return ''


def btn(text, data):
    return {'text': text, 'callback_data': data}


def url_btn(text, url):
    return {'text': text, 'url': url}


def markup(rows):
    rows = [[b for b in row if b] for row in rows]
    return {'inline_keyboard': [row for row in rows if row]}


def send(chat_id, text, rows=None, **extra):
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML', 'link_preview_options': {'is_disabled': True}, **extra}
    if rows:
        payload['reply_markup'] = markup(rows)
    return telegram_call('sendMessage', payload)


def show(cb, text, rows=None):
    """Tugma bosilgan xabarni joyida yangilaydi (zamonaviy menyu); bo'lmasa yangi xabar yuboradi."""
    message = cb.get('message') or {}
    chat_id = message.get('chat', {}).get('id') or cb['from']['id']
    if message.get('text') is not None:
        try:
            payload = {'chat_id': chat_id, 'message_id': message['message_id'], 'text': text, 'parse_mode': 'HTML',
                       'link_preview_options': {'is_disabled': True}}
            if rows:
                payload['reply_markup'] = markup(rows)
            return telegram_call('editMessageText', payload)
        except ValidationError:
            pass
    return send(chat_id, text, rows)


def answer(cb, text='', alert=False):
    try:
        telegram_call('answerCallbackQuery', {'callback_query_id': cb['id'], 'text': text[:190], 'show_alert': alert})
    except ValidationError:
        pass


def full_name(user):
    return ' '.join(x for x in [user.get('first_name', ''), user.get('last_name', '')] if x).strip() or user.get('username', '') or str(user.get('id'))


# ------------------------------------------------------------------ suhbat holati

def get_state(uid):
    state = TelegramBotState.objects.filter(telegram_id=uid).first()
    if state and state.updated_at < timezone.now() - STATE_TTL:
        state.delete()
        return None
    return state


def set_state(uid, step, data=None):
    TelegramBotState.objects.update_or_create(telegram_id=uid, defaults={'step': step, 'data': data or {}})


def clear_state(uid):
    TelegramBotState.objects.filter(telegram_id=uid).delete()


# ------------------------------------------------------------------ ekranlar

def welcome(uid, name):
    linked = TelegramConnection.objects.filter(chat_id=uid, enabled=True).select_related('user').first()
    lines = [f'👋 Assalomu alaykum, <b>{esc(name)}</b>!', '', 'Bu — <b>SSB Group</b> rasmiy boti.', '']
    if linked:
        lines.append(f'✅ Hisobingiz ulangan: <b>{esc(linked.user.display_name)}</b>')
        lines.append('Vazifalar, muddatlar, e’lonlar va reyting haqidagi bildirishnomalar shu yerga keladi.')
    else:
        lines.append('🔔 Bildirishnomalarni olish uchun boshqaruv panelidagi <b>Ulanishlar</b> sahifasida «Telegramni ulash» tugmasini bosing.')
    site = public_site()
    rows = [[url_btn('🌐 Boshqaruv paneli', site + '/management/')] if site else [],
            [btn('⚙️ Admin panel', 'm:home')] if is_admin(uid) else [],
            [btn('🆔 Mening ID raqamim', 'me:id')]]
    return '\n'.join(lines), rows


def panel(uid):
    channels, admins = TelegramChannel.objects.count(), len(owner_ids() | set(TelegramAdmin.objects.values_list('telegram_id', flat=True)))
    posts = TelegramPost.objects.count()
    text = ('⚙️ <b>Admin panel</b>\n\n'
            f'📡 Kanallar: <b>{channels}</b>\n'
            f'👥 Adminlar: <b>{admins}</b>\n'
            f'📝 Yuborilgan postlar: <b>{posts}</b>\n\n'
            'Kerakli bo‘limni tanlang 👇')
    rows = [[btn('📝 Post yuborish', 'p:new')],
            [btn('📡 Kanallar', 'c:list'), btn('👥 Adminlar', 'a:list')],
            [btn('➕ Kanal qo‘shish', 'c:add'), btn('➕ Admin qo‘shish', 'a:add')],
            [btn('✖️ Yopish', 'm:close')]]
    return text, rows


def channels_screen():
    items = list(TelegramChannel.objects.all())
    if not items:
        return ('📡 <b>Kanallar</b>\n\nHali kanal qo‘shilmagan.\n\n'
                'Kanal qo‘shish uchun botni kanalingizga <b>admin</b> qiling (post yuborish huquqi bilan) — bot uni o‘zi taniydi.',
                [[btn('➕ Kanal qo‘shish', 'c:add')], [btn('⬅️ Orqaga', 'm:home')]])
    lines = ['📡 <b>Kanallar</b>', '']
    rows = []
    for n, ch in enumerate(items, 1):
        lines.append(f'{n}. <b>{esc(ch.title)}</b>' + (f' — @{esc(ch.username)}' if ch.username else ''))
        rows.append([btn(f'🗑 {ch.title[:28]}', f'c:del:{ch.pk}')])
    lines += ['', 'O‘chirish uchun kanal nomini bosing.']
    rows += [[btn('➕ Kanal qo‘shish', 'c:add')], [btn('⬅️ Orqaga', 'm:home')]]
    return '\n'.join(lines), rows


def admins_screen(uid):
    owners = sorted(owner_ids())
    extra = list(TelegramAdmin.objects.exclude(telegram_id__in=owners))
    lines = ['👥 <b>Adminlar</b>', '']
    for tid in owners:
        lines.append(f'⭐ <code>{tid}</code> — asosiy admin' + (' (siz)' if tid == uid else ''))
    rows = []
    for adm in extra:
        label = adm.name or str(adm.telegram_id)
        lines.append(f'👤 <b>{esc(label)}</b> — <code>{adm.telegram_id}</code>' + (' (siz)' if adm.telegram_id == uid else ''))
        if adm.telegram_id != uid:
            rows.append([btn(f'🗑 {label[:28]}', f'a:del:{adm.pk}')])
    if not owners and not extra:
        lines.append('Admin yo‘q.')
    lines += ['', '⭐ Asosiy adminlar server sozlamasida belgilangan, ularni bot orqali o‘chirib bo‘lmaydi.']
    rows += [[btn('➕ Admin qo‘shish', 'a:add')], [btn('⬅️ Orqaga', 'm:home')]]
    return '\n'.join(lines), rows


CANCEL_ROW = [btn('❌ Bekor qilish', 'p:cancel')]


# ------------------------------------------------------------------ hisobni ulash (eski oqim)

def link_account(uid, token):
    if not re.fullmatch(r'[A-Za-z0-9_-]{32}', token):
        return False
    with transaction.atomic():
        link = (TelegramConnection.objects.select_for_update()
                .filter(link_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at__gt=timezone.now(),
                        user__is_active=True, bot_fingerprint=fingerprint('telegram')).select_related('user').first())
        if not link or TelegramConnection.objects.filter(chat_id=uid).exclude(pk=link.pk).exists():
            return False
        link.chat_id, link.enabled, link.link_hash, link.expires_at = uid, True, '', None
        link.save()
    return True


# ------------------------------------------------------------------ kanal qo'shish

def channel_ref(msg):
    """Forward qilingan post, @username, t.me havola yoki -100... ID dan kanalni aniqlaydi."""
    origin = msg.get('forward_origin') or {}
    if origin.get('type') == 'channel' and origin.get('chat'):
        return origin['chat']['id']
    if msg.get('forward_from_chat'):
        return msg['forward_from_chat']['id']
    text = (msg.get('text') or '').strip()
    found = re.fullmatch(r'(?:https?://)?(?:t\.me/|telegram\.me/)?@?([A-Za-z][A-Za-z0-9_]{3,31})/?', text)
    if found:
        return '@' + found.group(1)
    if re.fullmatch(r'-?\d{5,20}', text):
        return int(text)
    return None


def register_channel(ref, uid):
    """Kanalni tekshirib saqlaydi. Muvaffaqiyatli bo'lsa TelegramChannel, aks holda tushunarli xato matni."""
    try:
        chat = telegram_call('getChat', {'chat_id': ref})
    except ValidationError:
        return None, ('Kanal topilmadi. Tekshiring:\n• @username to‘g‘ri yozilganmi\n'
                      '• yopiq kanal bo‘lsa — undan istalgan postni shu yerga <b>forward</b> qiling\n• bot kanalga qo‘shilganmi')
    if chat.get('type') not in ('channel', 'supergroup', 'group'):
        return None, 'Bu kanal yoki guruh emas.'
    try:
        member = telegram_call('getChatMember', {'chat_id': chat['id'], 'user_id': bot_me()['id']})
    except ValidationError:
        member = {}
    can_post = member.get('status') == 'creator' or (member.get('status') == 'administrator' and
                                                     (chat['type'] != 'channel' or member.get('can_post_messages')))
    if not can_post:
        return None, (f'Bot <b>{esc(chat.get("title"))}</b> da admin emas yoki post yuborish huquqi yo‘q.\n\n'
                      'Kanal sozlamalari → Administratorlar → botni qo‘shing va «Xabarlar yuborish» huquqini yoqing, so‘ng qayta urinib ko‘ring.')
    item, _ = TelegramChannel.objects.update_or_create(chat_id=chat['id'], defaults={
        'title': (chat.get('title') or str(chat['id']))[:255], 'username': chat.get('username') or '', 'added_by': uid})
    return item, ''


# ------------------------------------------------------------------ post yaratish

def post_from_message(msg):
    if msg.get('photo'):
        return {'kind': 'photo', 'file_id': msg['photo'][-1]['file_id'], 'text': msg.get('caption', ''), 'entities': msg.get('caption_entities', [])}
    if msg.get('video'):
        return {'kind': 'video', 'file_id': msg['video']['file_id'], 'text': msg.get('caption', ''), 'entities': msg.get('caption_entities', [])}
    if msg.get('animation'):
        return {'kind': 'animation', 'file_id': msg['animation']['file_id'], 'text': msg.get('caption', ''), 'entities': msg.get('caption_entities', [])}
    if msg.get('text'):
        return {'kind': 'text', 'file_id': '', 'text': msg['text'], 'entities': msg.get('entities', [])}
    return None


def send_post(chat_id, post, buttons):
    payload = {'chat_id': chat_id}
    if buttons:
        payload['reply_markup'] = markup([[url_btn(b['text'], b['url'])] for b in buttons])
    if post['kind'] == 'text':
        payload.update(text=post['text'], entities=post.get('entities') or [])
        return telegram_call('sendMessage', payload)
    method = {'photo': 'sendPhoto', 'video': 'sendVideo', 'animation': 'sendAnimation'}[post['kind']]
    payload.update({post['kind']: post['file_id'], 'caption': post.get('text', ''), 'caption_entities': post.get('entities') or []})
    return telegram_call(method, payload)


def clean_url(text):
    text = (text or '').strip()
    if re.fullmatch(r'@[A-Za-z][A-Za-z0-9_]{3,31}', text):
        text = 'https://t.me/' + text[1:]
    if not re.match(r'^[a-z]+://', text, re.I):
        text = 'https://' + text
    parts = urlsplit(text)
    if parts.scheme.lower() not in ('http', 'https') or '.' not in (parts.hostname or '') or len(text) > 2000 or ' ' in text:
        return ''
    return text


def channel_names(ids):
    return ', '.join(TelegramChannel.objects.filter(pk__in=ids).values_list('title', flat=True)) or '—'


def ask_button(chat_id, data):
    count = len(data.get('buttons', []))
    text = ('🔘 <b>Postga tugma qo‘shilsinmi?</b>\n\nTugma bosilganda havola ochiladi (sayt, Telegram, Instagram va h.k.).'
            if not count else f'✅ Tugma qo‘shildi. Hozir: <b>{count}</b> ta.\n\nYana tugma qo‘shasizmi?')
    rows = [[btn('✅ Ha, qo‘shish' if not count else '➕ Yana tugma', 'p:btn:yes'),
             btn('➡️ Yo‘q, davom etish' if not count else '✅ Tayyor', 'p:btn:no')], CANCEL_ROW]
    send(chat_id, text, rows)


def preview(chat_id, uid, data):
    try:
        send_post(chat_id, data['post'], data.get('buttons', []))
    except ValidationError:
        set_state(uid, 'post_btn_ask', {**data, 'buttons': []})
        send(chat_id, '⚠️ Postni ko‘rsatib bo‘lmadi — ehtimol tugma havolasi noto‘g‘ri. Tugmalar olib tashlandi.')
        return ask_button(chat_id, {**data, 'buttons': []})
    set_state(uid, 'post_confirm', data)
    send(chat_id, f'👆 <b>Post shunday ko‘rinadi.</b>\n\n📡 Kanal: <b>{esc(channel_names(data["channels"]))}</b>\n\nYuboraymi?',
         [[btn('🚀 Yuborish', 'p:send')], [btn('✏️ Qaytadan yozish', 'p:redo'), btn('❌ Bekor qilish', 'p:cancel')]])


# ------------------------------------------------------------------ xabarlar

def handle_message(msg):
    chat = msg.get('chat', {})
    sender = msg.get('from') or {}
    if chat.get('type') != 'private' or chat.get('id') != sender.get('id'):
        return
    uid, name = sender['id'], full_name(sender)
    text = (msg.get('text') or '').strip()

    if text.startswith('/start'):
        token = text[6:].strip()
        clear_state(uid)
        if token:
            if link_account(uid, token):
                send(uid, '✅ <b>Hisobingiz ulandi!</b>\n\nEndi bildirishnomalar shu yerga keladi.')
            else:
                send(uid, '⚠️ Ulash havolasi eskirgan yoki allaqachon ishlatilgan. Boshqaruv panelida yangi havola oling.')
        body, rows = welcome(uid, name)
        return send(uid, body, rows)
    if text == '/stop':
        TelegramConnection.objects.filter(chat_id=uid).update(enabled=False, link_hash='', expires_at=None)
        return send(uid, '🔕 Bildirishnomalar o‘chirildi. Qayta yoqish uchun boshqaruv panelida hisobingizni qayta ulang.')
    if text == '/id':
        return send(uid, f'🆔 Sizning Telegram ID raqamingiz: <code>{uid}</code>\n\nBosib nusxalang va adminga yuboring.')
    if text in ('/cancel', '/bekor'):
        clear_state(uid)
        if is_admin(uid):
            return send(uid, *panel(uid))
        return send(uid, 'Bekor qilindi.')
    if text == '/admin':
        clear_state(uid)
        if not is_admin(uid):
            return send(uid, f'⛔️ Siz bot admini emassiz.\n\nID raqamingiz: <code>{uid}</code> — uni admin qo‘shishi uchun yuboring.')
        return send(uid, *panel(uid))

    state = get_state(uid) if is_admin(uid) else None
    if not state or not state.step:
        body, rows = welcome(uid, name)
        return send(uid, body, rows)
    data = dict(state.data)

    if state.step == 'channel_add':
        ref = channel_ref(msg)
        if ref is None:
            return send(uid, 'Kanal @username ini yuboring yoki kanaldagi istalgan postni shu yerga forward qiling.', [CANCEL_ROW])
        item, error = register_channel(ref, uid)
        if not item:
            return send(uid, '⚠️ ' + error, [CANCEL_ROW])
        clear_state(uid)
        return send(uid, f'✅ <b>{esc(item.title)}</b> kanali qo‘shildi!\n\nEndi unga post yuborishingiz mumkin.',
                    [[btn('📝 Post yuborish', 'p:new')], [btn('⬅️ Admin panel', 'm:home')]])

    if state.step == 'admin_add':
        origin = msg.get('forward_origin') or {}
        new_id = None
        if origin.get('type') == 'user':
            new_id = origin['sender_user']['id']
        elif msg.get('forward_from'):
            new_id = msg['forward_from']['id']
        elif re.fullmatch(r'\d{5,15}', text):
            new_id = int(text)
        if not new_id:
            return send(uid, 'Faqat raqamlardan iborat Telegram ID yuboring. Masalan: <code>123456789</code>\n\n'
                             'ID ni bilish uchun u odam botga /id deb yozsin.', [CANCEL_ROW])
        if is_admin(new_id):
            clear_state(uid)
            return send(uid, f'ℹ️ <code>{new_id}</code> allaqachon admin.', [[btn('⬅️ Admin panel', 'm:home')]])
        try:
            info = telegram_call('getChat', {'chat_id': new_id})
            label = full_name(info)
        except ValidationError:
            label = ''
        TelegramAdmin.objects.create(telegram_id=new_id, name=label[:200], added_by=uid)
        clear_state(uid)
        try:
            send(new_id, '🎉 <b>Siz SSB Group boti admini etib tayinlandingiz!</b>\n\nAdmin panelni ochish uchun pastdagi tugmani bosing.',
                 [[btn('⚙️ Admin panel', 'm:home')]])
            note = 'U botga xabar oldi.'
        except ValidationError:
            note = 'U hali botni ishga tushirmagan — botga /start yozsa, admin panel ochiladi.'
        return send(uid, f'✅ Yangi admin qo‘shildi: <b>{esc(label or new_id)}</b> (<code>{new_id}</code>)\n\n{note}',
                    [[btn('👥 Adminlar', 'a:list')], [btn('⬅️ Admin panel', 'm:home')]])

    if state.step == 'post_content':
        post = post_from_message(msg)
        if not post:
            return send(uid, 'Matn, rasm yoki video yuboring.', [CANCEL_ROW])
        limit = 4096 if post['kind'] == 'text' else 1024
        if len(post['text']) > limit:
            return send(uid, f'⚠️ Matn juda uzun: {len(post["text"])} belgi. {"Rasmli" if post["kind"] != "text" else "Oddiy"} postda ko‘pi bilan {limit} belgi bo‘ladi.', [CANCEL_ROW])
        data.update(post=post, buttons=[])
        set_state(uid, 'post_btn_ask', data)
        return ask_button(uid, data)

    if state.step == 'post_btn_text':
        if not text or len(text) > 64:
            return send(uid, 'Tugma nomi 1–64 belgi bo‘lsin. Masalan: <i>Batafsil</i>, <i>Ro‘yxatdan o‘tish</i>', [CANCEL_ROW])
        data['pending'] = text
        set_state(uid, 'post_btn_url', data)
        return send(uid, f'🔗 «<b>{esc(text)}</b>» tugmasi uchun <b>havolani</b> yuboring.\n\nMasalan: <code>https://ssbgroup.uz</code> yoki <code>@kanal_nomi</code>', [CANCEL_ROW])

    if state.step == 'post_btn_url':
        url = clean_url(text)
        if not url:
            return send(uid, '⚠️ Havola noto‘g‘ri. To‘liq manzil yuboring, masalan: <code>https://ssbgroup.uz</code>', [CANCEL_ROW])
        data.setdefault('buttons', []).append({'text': data.pop('pending', 'Ochish'), 'url': url})
        if len(data['buttons']) >= 8:
            return preview(uid, uid, data)
        set_state(uid, 'post_btn_ask', data)
        return ask_button(uid, data)

    body, rows = welcome(uid, name)
    send(uid, body, rows)


# ------------------------------------------------------------------ tugmalar

def handle_callback(cb):
    uid = cb['from']['id']
    data = cb.get('data', '')
    message = cb.get('message') or {}
    chat_id = message.get('chat', {}).get('id', uid)

    if data == 'me:id':
        answer(cb)
        return send(chat_id, f'🆔 Sizning Telegram ID raqamingiz: <code>{uid}</code>\n\nBosib nusxalang.')
    if not is_admin(uid):
        return answer(cb, 'Bu bo‘lim faqat adminlar uchun.', alert=True)

    if data == 'm:home':
        clear_state(uid)
        answer(cb)
        return show(cb, *panel(uid))
    if data == 'm:close':
        clear_state(uid)
        answer(cb, 'Yopildi')
        try:
            telegram_call('deleteMessage', {'chat_id': chat_id, 'message_id': message['message_id']})
        except (ValidationError, KeyError):
            pass
        return

    # --- kanallar
    if data == 'c:list':
        answer(cb)
        return show(cb, *channels_screen())
    if data == 'c:add':
        set_state(uid, 'channel_add')
        answer(cb)
        name = bot_me().get('username', '')
        return show(cb, '➕ <b>Kanal qo‘shish</b>\n\n'
                        f'1️⃣ Botni (@{esc(name)}) kanalingizga <b>administrator</b> qiling va «Xabarlar yuborish» huquqini yoqing.\n'
                        '2️⃣ Shu yerga kanal <b>@username</b> ini yuboring yoki kanaldagi istalgan postni <b>forward</b> qiling.\n\n'
                        '💡 Botni kanalga admin qilganingizda u kanalni o‘zi ham taniydi.', [CANCEL_ROW])
    if data.startswith('c:del:'):
        item = TelegramChannel.objects.filter(pk=data[6:]).first() if data[6:].isdigit() else None
        answer(cb)
        if not item:
            return show(cb, *channels_screen())
        return show(cb, f'🗑 <b>{esc(item.title)}</b> kanalini ro‘yxatdan o‘chiraymi?\n\nKanalning o‘zi va undagi postlar o‘chmaydi.',
                    [[btn('✅ Ha, o‘chirish', f'c:delok:{item.pk}'), btn('⬅️ Yo‘q', 'c:list')]])
    if data.startswith('c:delok:'):
        TelegramChannel.objects.filter(pk=data[8:] if data[8:].isdigit() else 0).delete()
        answer(cb, 'O‘chirildi')
        return show(cb, *channels_screen())

    # --- adminlar
    if data == 'a:list':
        answer(cb)
        return show(cb, *admins_screen(uid))
    if data == 'a:add':
        set_state(uid, 'admin_add')
        answer(cb)
        return show(cb, '➕ <b>Admin qo‘shish</b>\n\nYangi adminning <b>Telegram ID</b> raqamini yuboring.\nMasalan: <code>123456789</code>\n\n'
                        '💡 ID ni bilish uchun u odam shu botga /id deb yozsin. Yoki uning istalgan xabarini shu yerga forward qiling.', [CANCEL_ROW])
    if data.startswith('a:del:'):
        item = TelegramAdmin.objects.filter(pk=data[6:]).first() if data[6:].isdigit() else None
        answer(cb)
        if not item or is_owner(item.telegram_id) or item.telegram_id == uid:
            return show(cb, *admins_screen(uid))
        return show(cb, f'🗑 <b>{esc(item.name or item.telegram_id)}</b> adminlikdan olinsinmi?',
                    [[btn('✅ Ha', f'a:delok:{item.pk}'), btn('⬅️ Yo‘q', 'a:list')]])
    if data.startswith('a:delok:'):
        item = TelegramAdmin.objects.filter(pk=data[8:] if data[8:].isdigit() else 0).first()
        if item and not is_owner(item.telegram_id) and item.telegram_id != uid:
            item.delete()
            clear_state(item.telegram_id)
        answer(cb, 'Adminlikdan olindi')
        return show(cb, *admins_screen(uid))

    # --- post
    if data == 'p:cancel':
        clear_state(uid)
        answer(cb, 'Bekor qilindi')
        return show(cb, *panel(uid))
    if data == 'p:new':
        answer(cb)
        items = list(TelegramChannel.objects.all())
        if not items:
            return show(cb, '📝 <b>Post yuborish</b>\n\nAvval kamida bitta kanal qo‘shing.',
                        [[btn('➕ Kanal qo‘shish', 'c:add')], [btn('⬅️ Orqaga', 'm:home')]])
        if len(items) == 1:
            return start_post(cb, uid, [items[0].pk])
        rows = [[btn(f'📡 {ch.title[:40]}', f'p:ch:{ch.pk}')] for ch in items]
        rows += [[btn('📢 Barcha kanallarga', 'p:all')], [btn('⬅️ Orqaga', 'm:home')]]
        return show(cb, '📝 <b>Post yuborish</b>\n\nQaysi kanalga yuboramiz?', rows)
    if data.startswith('p:ch:') and data[5:].isdigit():
        answer(cb)
        return start_post(cb, uid, [int(data[5:])])
    if data == 'p:all':
        answer(cb)
        return start_post(cb, uid, list(TelegramChannel.objects.values_list('pk', flat=True)))

    state = get_state(uid)
    sdata = dict(state.data) if state else {}
    if data == 'p:redo' and state and sdata.get('channels'):
        answer(cb)
        return start_post(cb, uid, sdata['channels'], fresh=True)
    if data == 'p:btn:yes' and state and state.step == 'post_btn_ask':
        set_state(uid, 'post_btn_text', sdata)
        answer(cb)
        return show(cb, '✍️ <b>Tugma nomini</b> yuboring.\n\nMasalan: <i>Batafsil</i>, <i>Saytga o‘tish</i>, <i>Ro‘yxatdan o‘tish</i>', [CANCEL_ROW])
    if data == 'p:btn:no' and state and state.step == 'post_btn_ask':
        answer(cb)
        return preview(chat_id, uid, sdata)
    if data == 'p:send':
        with transaction.atomic():
            locked = TelegramBotState.objects.select_for_update().filter(telegram_id=uid, step='post_confirm').first()
            post_data = dict(locked.data) if locked else None
            if locked:
                locked.delete()
        if not post_data:
            return answer(cb, 'Bu post allaqachon yuborilgan yoki bekor qilingan.', alert=True)
        answer(cb, 'Yuborilmoqda…')
        return publish(chat_id, uid, post_data)
    answer(cb, 'Bu tugma eskirgan. Admin panelni qayta oching.', alert=True)


def start_post(cb, uid, channel_ids, fresh=False):
    set_state(uid, 'post_content', {'channels': channel_ids})
    text = (f'📝 <b>Yangi post</b>\n📡 Kanal: <b>{esc(channel_names(channel_ids))}</b>\n\n'
            'Post <b>matnini</b> yoki <b>rasmni</b> (izohi bilan) yuboring. Video ham bo‘ladi.\n'
            '💡 Qalin, kursiv va havolalar saqlanib qoladi.')
    if fresh:
        return send(cb['from']['id'], text, [CANCEL_ROW])
    return show(cb, text, [CANCEL_ROW])


def publish(chat_id, uid, data):
    results, rows = [], []
    for ch in TelegramChannel.objects.filter(pk__in=data.get('channels', [])):
        try:
            sent = send_post(ch.chat_id, data['post'], data.get('buttons', []))
            TelegramPost.objects.create(channel=ch, channel_title=ch.title, message_id=sent.get('message_id'), kind=data['post']['kind'],
                                        text=data['post'].get('text', ''), buttons=data.get('buttons', []), sent_by=uid)
            results.append(f'✅ {esc(ch.title)}')
            if ch.username and sent.get('message_id'):
                rows.append([url_btn(f'👁 {ch.title[:30]}', f'https://t.me/{ch.username}/{sent["message_id"]}')])
        except ValidationError:
            results.append(f'⚠️ {esc(ch.title)} — yuborilmadi (bot admin emasmi yoki tugma havolasi noto‘g‘ri?)')
    if not results:
        results.append('⚠️ Tanlangan kanal topilmadi.')
    rows += [[btn('📝 Yana post', 'p:new')], [btn('⬅️ Admin panel', 'm:home')]]
    send(chat_id, '🚀 <b>Natija</b>\n\n' + '\n'.join(results), rows)


# ------------------------------------------------------------------ bot kanalga qo'shilganda

def handle_membership(update):
    chat, actor = update.get('chat', {}), update.get('from', {})
    if chat.get('type') not in ('channel', 'supergroup', 'group'):
        return
    status = (update.get('new_chat_member') or {}).get('status')
    if status in ('left', 'kicked'):
        removed = TelegramChannel.objects.filter(chat_id=chat['id']).first()
        if removed:
            removed.delete()
            if actor.get('id') and is_admin(actor['id']):
                try:
                    send(actor['id'], f'ℹ️ Bot <b>{esc(removed.title)}</b> kanalidan chiqarildi va ro‘yxatdan olib tashlandi.')
                except ValidationError:
                    pass
        return
    if status in ('administrator', 'creator') and actor.get('id') and is_admin(actor['id']):
        item, error = register_channel(chat['id'], actor['id'])
        try:
            if item:
                send(actor['id'], f'✅ <b>{esc(item.title)}</b> kanali avtomatik qo‘shildi!',
                     [[btn('📝 Post yuborish', 'p:new')], [btn('⬅️ Admin panel', 'm:home')]])
            else:
                send(actor['id'], '⚠️ ' + error)
        except ValidationError:
            pass


def announcement_text(item):
    """Hackaton e'lonini Telegram uchun chiroyli HTML matnga aylantiradi."""
    lines = [f'🏆 <b>{esc(item.title)}</b>']
    facts = []
    if item.event_date:
        facts.append(f'📅 Sana: <b>{item.event_date:%d.%m.%Y}</b>')
    if item.registration_deadline:
        facts.append(f'⏳ Ro‘yxatdan o‘tish: <b>{item.registration_deadline:%d.%m.%Y}</b> gacha')
    if item.location:
        facts.append(f'📍 Joy: <b>{esc(item.location)}</b>')
    if item.prize:
        facts.append(f'🎁 Mukofot: <b>{esc(item.prize)}</b>')
    if facts:
        lines += [''] + facts
    if item.body:
        lines += ['', esc(item.body)]
    lines += ['', '#hackaton · <i>SSB Group</i>']
    return '\n'.join(lines)


def post_announcement(item):
    """E'lonni barcha qo'shilgan kanallarga yuboradi (birinchi rasm + tugma). Natija: (yuborilgan, xato) kanal nomlari."""
    from .channels import telegram_upload
    rows = [[url_btn(f'👉 {item.button_label}', item.link_url)]] if item.link_url else []
    text = announcement_text(item)
    image = item.images.first()
    content = None
    if image:
        with image.image.open('rb') as f:
            content = f.read()
    sent, failed = [], []
    for ch in TelegramChannel.objects.all():
        try:
            if content and len(text) <= 1024:
                result = telegram_upload('sendPhoto', {'chat_id': ch.chat_id, 'caption': text, 'parse_mode': 'HTML',
                                                       'reply_markup': markup(rows) if rows else None}, 'photo', image.image.name, content)
            else:
                if content:  # Matn rasm izohiga sig'masa: avval rasm, keyin to'liq matn tugma bilan.
                    telegram_upload('sendPhoto', {'chat_id': ch.chat_id}, 'photo', image.image.name, content)
                result = send(ch.chat_id, text, rows or None)
            TelegramPost.objects.create(channel=ch, channel_title=ch.title, message_id=result.get('message_id'),
                                        kind='photo' if content else 'text', text=text,
                                        buttons=[{'text': item.button_label, 'url': item.link_url}] if item.link_url else [], sent_by=0)
            sent.append(ch.title)
        except ValidationError:
            failed.append(ch.title)
    return sent, failed


def handle_update(update):
    if 'callback_query' in update:
        return handle_callback(update['callback_query'])
    if 'message' in update:
        return handle_message(update['message'])
    if 'my_chat_member' in update:
        return handle_membership(update['my_chat_member'])


def set_commands():
    """Bot menyusidagi buyruqlar (chap pastdagi «Menu» tugmasi)."""
    try:
        telegram_call('setMyCommands', {'commands': [
            {'command': 'start', 'description': 'Bosh menyu'},
            {'command': 'admin', 'description': 'Admin panel'},
            {'command': 'id', 'description': 'Mening Telegram ID raqamim'},
            {'command': 'cancel', 'description': 'Joriy amalni bekor qilish'},
        ]})
    except ValidationError:
        pass
