"""Independent SSB Boshqaruv navigation and role experience; backend policies remain authoritative."""
from django.urls import reverse
from django.utils import timezone
from django.contrib import messages
from django.conf import settings

P = 'projects.own|projects.view_all|projects.create|projects.edit|projects.assign|projects.approve'

ITEMS = [
    # Har bir band faqat Asoschi bergan funksiya bo'lsa ko'rinadi (Asoschi hammasini ko'radi).
    ('Ish maydoni', 'enterprise:overview', 'Bosh sahifa', 'overview', None),
    ('Ish maydoni', 'crm:projects', 'Loyihalar', 'project', P),
    ('Ish maydoni', 'enterprise:schedule', 'Ish jadvali', 'calendar', 'schedule.view|schedule.manage'),
    ('Ish maydoni', 'enterprise:performance', 'Baholash va reyting', 'chart', 'performance.self|performance.view|performance.manage'),
    ('Ish maydoni', 'chat:index', 'Xodimlar chati', 'chat', 'chat.use'),

    ('Boshqaruv', 'crm:employees', 'Xodimlar', 'people', 'employees.view|employees.manage'),
    ('Boshqaruv', 'crm:roles', 'Kompaniya tuzilmasi', 'people', 'roles.manage'),
    ('Boshqaruv', 'crm:inquiries', 'Murojaatlar (CRM)', 'project', 'inquiries.manage'),

    ('Moliya', 'enterprise:balance', 'Shaxsiy hisobim', 'money', 'finance.balance|finance.view'),
    ('Moliya', 'enterprise:finance', 'Moliyaviy reyestr', 'money', 'finance.view|finance.manage'),

    ('Kompaniya', 'crm:announcements', 'Hackaton e’lonlari', 'spark', 'announcements.view|announcements.manage'),
    # Hamma ko'radi: Asoschi — barcha jihozlarni, xodim — faqat o'ziga biriktirilganlarini.
    ('Kompaniya', 'crm:equipment', 'Jihozlar', 'desktop', None),
    ('Kompaniya', 'enterprise:archives', 'Xavfsiz arxiv', 'file', 'archive.use|archive.manage'),
    ('Kompaniya', 'crm:cms', 'Sayt va Portfolio', 'file', 'cms.edit'),
    ('Kompaniya', 'crm:clients', 'Mijozlar bazasi', 'people', 'clients.view|clients.manage'),
    # Faqat Asoschi: rolga berib bo'lmaydigan funksiya (has_cap Asoschi uchun doim True).
    ('Kompaniya', 'crm:partners', 'Hamkorlar', 'handshake', 'partners.founder_only'),

    ('Tizim', 'crm:notifications', 'Bildirishnomalar', 'bell', None),
    ('Tizim', 'enterprise:desktop', 'Windows ilovasi', 'desktop', None),
    ('Tizim', 'crm:settings', 'Tizim sozlamalari', 'settings', 'settings.manage'),
    ('Tizim', 'crm:audit', 'Audit tarixi', 'shield', 'audit.view'),
    # Faqat Asoschi: bo'limlarni bazadan butunlay tozalash (rolga berib bo'lmaydi).
    ('Tizim', 'enterprise:data_reset', 'Ma’lumotlarni tozalash', 'trash', 'data.founder_only'),
]

def nav_route(match):
    """Which sidebar item a resolved URL belongs to (e.g. a task page belongs to 'Loyihalar')."""
    current = match.view_name
    nav_current = current
    name = match.url_name or ''
    if match.namespace == 'chat':
        nav_current = 'chat:index'
    if match.namespace == 'crm':
        for prefix, route in [
            ('task', 'crm:projects'), ('project', 'crm:projects'), ('calendar', 'crm:projects'), ('workload', 'crm:projects'), ('milestone', 'crm:projects'),
            ('employee', 'crm:employees'), ('inquiry', 'crm:inquiries'), ('client', 'crm:clients'),
            ('role', 'crm:roles'), ('department', 'crm:roles'), ('cms', 'crm:cms'),
            ('announcement', 'crm:announcements'), ('notification', 'crm:notifications'), ('partner', 'crm:partners'), ('equipment', 'crm:equipment'),
            ('setting', 'crm:settings'), ('audit', 'crm:audit')
        ]:
            if name.startswith(prefix):
                nav_current = route
                break
    if match.namespace == 'enterprise':
        nav_current = {
            'rules': 'enterprise:finance', 'entry': 'enterprise:finance', 'decision': 'enterprise:finance',
            'payout_create': 'enterprise:finance', 'operation_new': 'enterprise:finance',
            'archive_code': 'enterprise:archives', 'archive_download': 'enterprise:archives',
            'archive_unlock': 'enterprise:archives', 'archive_lock': 'enterprise:archives', 'archive_delete': 'enterprise:archives',
            'review_approve': 'enterprise:performance', 'cancel_shift': 'enterprise:schedule',
            'rating': 'enterprise:performance', 'evaluation_detail': 'enterprise:performance',
            'performance_history': 'enterprise:performance', 'weekly_publish': 'enterprise:performance',
            'weekly_reward': 'enterprise:performance',
            'layout': 'enterprise:overview'
        }.get(name, current)
    return nav_current


def _notification_path(url):
    from urllib.parse import urlsplit
    return urlsplit(url or '').path


def mark_page_notifications_read(request):
    """Opening the page a notification points to counts as reading it, so the section badge clears."""
    if request.method != 'GET':
        return
    from apps.notifications.models import Notification
    unread = Notification.objects.filter(recipient=request.user, read_at__isnull=True,
                                         url__startswith=request.path).only('pk', 'url')
    ids = [n.pk for n in unread if _notification_path(n.url) == request.path]
    if ids:
        Notification.objects.filter(pk__in=ids).update(read_at=timezone.now())


def section_unread(user):
    """Unread notifications per sidebar section, keyed by the section's URL."""
    from django.urls import Resolver404, resolve
    from apps.notifications.models import Notification
    counts, routes = {}, {}
    urls = (Notification.objects.filter(recipient=user, read_at__isnull=True)
            .exclude(kind=Notification.Kind.CHAT).values_list('url', flat=True)[:500])
    for url in urls:
        path = _notification_path(url)
        if path not in routes:
            try:
                routes[path] = nav_route(resolve(path))
            except Resolver404:
                routes[path] = None
        route = routes[path]
        if not route:
            continue
        try:
            key = reverse(route)
        except Exception:
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


def shell(request):
    match = getattr(request, 'resolver_match', None)
    if not match or match.namespace not in ['crm', 'enterprise', 'accounts', 'chat'] or not request.user.is_authenticated:
        return {}
    is_desktop = any(marker in request.headers.get('User-Agent', '') for marker in ('SSBDesktop/', 'Electron/'))
    nav_current = nav_route(match)
    mark_page_notifications_read(request)
    section_counts = section_unread(request.user)

    groups = []
    from apps.chat.models import Message
    chat_unread = Message.objects.filter(recipient=request.user, read_at__isnull=True).count()
    for group, route, label, icon, capabilities in ITEMS:
        if is_desktop and route == 'enterprise:desktop':
            continue
        if capabilities and not any(request.user.has_cap(cap) for cap in capabilities.split('|')):
            continue
        if not groups or groups[-1]['title'] != group:
            groups.append({'title': group, 'items': []})
        url = reverse(route)
        groups[-1]['items'].append({
            'url': url,
            'unread': section_counts.get(url, 0),
            'label': label,
            'icon': icon,
            'active': route == nav_current,
            'is_chat': route == 'chat:index', 'chat_unread': chat_unread if route == 'chat:index' else 0
        })

    if not request.user.has_cap('cms.edit') and (request.user.has_cap('team.manage') or request.user.has_cap('employees.manage')):
        url = reverse('crm:cms_list', args=['team'])
        if groups:
            groups[-1]['items'].append({'url': url, 'label': 'Jamoa kartalari', 'icon': 'people', 'active': request.path == url})

    active = next((item for group in groups for item in group['items'] if item['active']), None)

    # Telefon uchun pastki tab-panel: Asosiy · Bo'limlar · (Loyihalar / Chat / Bildirishnomalar) · Kabinet.
    available = {item['route']: item for item in (
        {'route': 'crm:projects', 'label': 'Loyihalar', 'icon': 'project'},
        {'route': 'chat:index', 'label': 'Chat', 'icon': 'chat', 'is_chat': True},
        {'route': 'crm:notifications', 'label': 'Xabarlar', 'icon': 'bell'},
    ) if any(i['url'] == reverse(item['route']) for group in groups for i in group['items'])}
    middle = [dict(available[route], url=reverse(route), active=nav_current == route and not available[route].get('is_chat'))
              for route in ('crm:projects', 'chat:index', 'crm:notifications') if route in available][:2]
    profile_active = match.url_name in ('profile', 'password_change')
    mobile_tabs = {
        'home': {'url': reverse('enterprise:overview'), 'active': nav_current == 'enterprise:overview'},
        'middle': middle,
        'profile': {'url': reverse('crm:profile'), 'active': profile_active},
    }
    mobile_tabs['sections_active'] = not (mobile_tabs['home']['active'] or profile_active or any(t['active'] for t in middle))

    actions = []
    for capability, label, route in [
        ('projects.create', 'Yangi loyiha yaratish', 'crm:project_create'),
        ('employees.manage', 'Yangi xodim qo‘shish', 'crm:employee_create'),
        ('finance.manage', 'Moliyaviy so‘rov yaratish', 'enterprise:finance'),
        ('schedule.manage', 'Navbatchilik jadvali tuzish', 'enterprise:schedule'),
        ('inquiries.manage', 'Murojaatlarni ko‘rish', 'crm:inquiries'),
        ('announcements.manage', 'Hackaton e’loni yozish', 'crm:announcements')
    ]:
        if request.user.has_cap(capability):
            actions.append({'label': label, 'url': reverse(route)})

    if request.user.has_cap('archive.use') or request.user.has_cap('archive.manage'):
        actions.append({'label': 'Loyiha faylini arxivga yuklash', 'url': reverse('enterprise:archives')})
    if request.user.has_cap('finance.balance') or request.user.has_cap('finance.view'):
        actions.append({'label': 'Shaxsiy balansni tekshirish', 'url': reverse('enterprise:balance')})

    toasts = [{'text': str(item), 'level': 'error' if item.level >= messages.ERROR else 'success'} for item in messages.get_messages(request)]
    from apps.core.models import ACCENT_PRESETS, DEFAULT_ACCENT, WorkspaceSettings
    workspace = WorkspaceSettings.load()

    role_titles = {
        'founder': 'Kompaniya boshqaruvi',
        'cofounder': 'Hammuassis boshqaruvi',
        'management': 'Direktor ish maydoni',
        'employee': 'Xodim ish maydoni'
    }

    # Xodim javob bermagan to'lovlar: qaysi sahifada bo'lmasin, tasdiqlash oynasi chiqadi
    # ("Shaxsiy hisobim" bo'limi ochilmagan xodim ham javob bera oladi).
    from . import finance as _finance
    payout_asks = [op for op in _finance.payouts().filter(employee=request.user).order_by('-created_at')[:20]
                   if _finance.payout_state(op) == 'pending'][:5]

    return {
        'payout_asks': payout_asks,
        'app_navigation': groups,
        # Recounted after this page marked its own notifications read (overrides the earlier processor).
        'unread_count': request.user.notifications.filter(read_at__isnull=True).count(),
        'mobile_tabs': mobile_tabs,
        'chat_unread': chat_unread,
        'is_desktop_app': is_desktop,
        'screenshot_blocked': request.user.screenshot_blocked,
        'app_section': active['label'] if active else {'profile': 'Mening profilim', 'password_change': 'Parolni o‘zgartirish'}.get(match.url_name, 'Ish maydoni'),
        'app_today': timezone.localdate(),
        'workspace': workspace,
        'app_date_format': workspace.date_format,
        'app_datetime_format': workspace.date_format + ' H:i',
        'quick_actions': actions,
        'toast_messages': toasts,
        'ui_version': settings.DESKTOP_VERSION,
        # Kompaniya bo'yicha bitta asosiy rang; tanlash faqat direktorga (Asoschi) ko'rinadi.
        'accent_color': workspace.accent_color or DEFAULT_ACCENT,
        'accent_presets': ACCENT_PRESETS,
        'can_change_accent': request.user.is_owner,
        'role_heading': role_titles.get(request.user.dashboard_kind, 'Xodim ish maydoni')
    }
