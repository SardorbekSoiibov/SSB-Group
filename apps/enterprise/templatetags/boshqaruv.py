from decimal import Decimal, InvalidOperation
from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register=template.Library()

@register.filter
def is_decimal(value):
    return isinstance(value,Decimal)

@register.filter
def can(user,capability):return user.has_cap(capability)

@register.filter
def money(value):
    try:return f'{Decimal(value or 0):,.2f}'.replace(',',' ')
    except (InvalidOperation,TypeError,ValueError):return '—'

@register.filter
def initials(person):
    return ''.join(word[0] for word in str(getattr(person,'display_name',person) or 'SSB').split()[:2]).upper()

@register.simple_tag
def people_options(field):
    from apps.crm.forms import picker_rows
    return picker_rows(field)

@register.simple_tag
def ui_icon(name):
    paths={
        'chat':'<path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5H3l2-5a8.5 8.5 0 1 1 16-3.5Z"/><path d="M8 10h8m-8 4h5"/>',
        'home':'<path d="M3.5 10.5 12 3.5l8.5 7"/><path d="M5.5 9v10.5a1 1 0 0 0 1 1H10v-6h4v6h3.5a1 1 0 0 0 1-1V9"/>',
        'grid':'<rect x="3.5" y="3.5" width="7" height="7" rx="2"/><rect x="13.5" y="3.5" width="7" height="7" rx="2"/><rect x="3.5" y="13.5" width="7" height="7" rx="2"/><circle cx="17" cy="17" r="3.5"/>',
        'overview':'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
        'task':'<path d="m4 6 2 2 3-4M12 6h8M4 13h5m3 0h8M4 20h5m3 0h8"/>',
        'project':'<path d="M3 7a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v9H3Z"/>',
        'people':'<circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6m3 10v-3a6 6 0 0 0-3-5"/>',
        'handshake':'<path d="m11 17 2 2a1.4 1.4 0 0 0 2-2"/><path d="m14 14 2.5 2.5a1.4 1.4 0 0 0 2-2L15 11"/><path d="m21 3-4 4-4-1-5 5a1.4 1.4 0 0 0 2 2l3-3 3 3"/><path d="M3 3l4 4 1 1M3 13l5 5a1.4 1.4 0 0 0 2-2"/>',
        'money':'<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M3 10h18m-6 5h3"/>',
        'calendar':'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 2v6m10-6v6M3 11h18m-12 4h2m3 0h2"/>',
        'chart':'<path d="M3 3v18h18M7 16v-5m5 5V7m5 9V4"/>',
        'file':'<path d="M5 3h9l5 5v13H5Zm9 0v5h5M8 13h8m-8 4h5"/>',
        'bell':'<path d="M4 17h16l-2-4V9a6 6 0 0 0-12 0v4Zm6 4h4"/>',
        'settings':'<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="9" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="8" cy="18" r="2"/>',
        'search':'<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
        'arrow':'<path d="M5 12h14m-5-5 5 5-5 5"/>',
        'plus':'<path d="M12 4v16M4 12h16"/>',
        'download':'<path d="M12 4v11m-5-5 5 5 5-5M4 20h16"/>',
        'trash':'<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6m4-6v6"/>',
        'menu':'<path d="M4 6h16M4 12h16M4 18h16"/>',
        'gift':'<rect x="3" y="9" width="18" height="4" rx="1"/><path d="M5 13v8h14v-8M12 9v12M12 9S10.5 3 7.5 4 9 9 12 9Zm0 0s1.5-6 4.5-5S15 9 12 9Z"/>',
        'spark':'<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9ZM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8Z"/>',
        'kanban':'<rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M9 4v16m6-16v16"/>',
        'edit':'<path d="M4 20h4L19 9l-4-4L4 16Zm9-13 4 4"/>',
        'lock':'<rect x="4" y="10" width="16" height="11" rx="2.5"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/>',
        'camera':'<path d="M3 8.5A2.5 2.5 0 0 1 5.5 6H8l1.5-2h5L16 6h2.5A2.5 2.5 0 0 1 21 8.5v9a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5Z"/><circle cx="12" cy="13" r="3.5"/>',
        'mail':'<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="m4 7 8 6 8-6"/>',
        'phone':'<path d="M5 3h4l2 5-2.5 1.5a11 11 0 0 0 6 6L16 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 5a2 2 0 0 1 2-2Z"/>',
        'send':'<path d="M21 3 3 10.5l7 2.5 2.5 7ZM10 13l5-5"/>',
        'star':'<path d="m12 3 2.7 5.8 6.3.8-4.6 4.3 1.2 6.3-5.6-3.1-5.6 3.1 1.2-6.3L3 9.6l6.3-.8Z"/>',
        'close':'<path d="m6 6 12 12M6 18 18 6"/>',
        'check':'<path d="m4 12 5 5L20 6"/>',
        'shield':'<path d="m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6Z"/><path d="m8 12 3 3 5-6"/>',
        'desktop':'<rect x="3" y="3" width="18" height="13" rx="2"/><path d="M12 16v5m-5 0h10"/>',
    }
    return format_html('<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{}</svg>',mark_safe(paths.get(name,paths['project'])))

@register.filter
def audit_label(action):
    from apps.audit.services import ACTION_LABELS
    return ACTION_LABELS.get(action, action)

@register.filter
def audit_changes(value):
    import json
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


@register.filter
def plain_filesize(value):
    # Django's Uzbek translation writes "160bayt" with no space between the number and the unit.
    import re
    from django.template.defaultfilters import filesizeformat
    return re.sub(r'(?<=[0-9])(?=[^0-9,. ])', ' ', filesizeformat(value).replace('\xa0', ' '))
