from datetime import timedelta
from django.db.models import Count, Q
from django.utils import timezone
from apps.accounts.policies import visible_employees
from apps.crm.models import Project
from apps.crm.policies import visible_projects
from .models import FinanceOperation, LedgerEntry
from .finance import profitability, company_summary, employee_balance


def management_insights(actor):
    today = timezone.localdate()
    projects = visible_projects(actor).exclude(status__in=[Project.Status.ARCHIVED, Project.Status.COMPLETED, Project.Status.CANCELLED])
    result = []
    late = projects.filter(deadline__lt=today).count()
    upcoming = projects.filter(deadline__range=[today,today+timedelta(days=7)]).count()
    review = projects.filter(status=Project.Status.UNDER_REVIEW).count()
    if late: result.append({'level':'danger','text':f'{late} ta loyiha muddati o‘tgan.','url':'/management/loyihalar/'})
    if upcoming: result.append({'level':'warning','text':f'{upcoming} ta loyiha shu hafta yakunlanishi kerak.','url':'/management/loyihalar/taqvim/'})
    if review and (actor.is_owner or actor.has_cap('projects.approve')): result.append({'level':'info','text':f'{review} ta loyiha tekshiruvingizni kutmoqda.','url':'/management/loyihalar/?holat=under_review'})
    if actor.has_cap('finance.view'):
        from .finance import visible_entries
        entries=visible_entries(actor)
        for currency in entries.values_list('currency',flat=True).distinct():
            total=company_summary(entries,currency)
            if total['employee_payable']>0:
                result.append({'level':'warning','text':f"Xodimlarga to‘lanishi kerak: {total['employee_payable']:,.2f} {currency}. Manba: tasdiqlangan reyestr.",'url':'/management/enterprise/reports/?report=outstanding&currency='+currency})
        client_pending=sum(1 for project in projects[:100] if (data:=profitability(project)) and data['outstanding_client']>0)
        if client_pending:result.append({'level':'info','text':f'{client_pending} ta loyihada mijoz to‘lovi kutilmoqda (dastlabki 100 loyiha).','url':'/management/enterprise/reports/?report=profitability'})
        risks = [p for p in projects[:100] if (data:=profitability(p)) and (data['net_profit']<0 or (p.deadline and p.deadline<today and data['outstanding_client']>0))]
        if risks: result.append({'level':'danger','text':f'{len(risks)} ta loyihada moliyaviy xavf bor (ko‘rinadigan dastlabki 100 loyiha).','url':'/management/enterprise/reports/?report=profitability'})
        pending = FinanceOperation.objects.filter(status='pending').count() if actor.company_scope else FinanceOperation.objects.filter(status='pending',administrator=actor).count()
        if pending: result.append({'level':'info','text':f'{pending} ta moliyaviy amal tasdiq kutmoqda.','url':'/management/enterprise/finance/'})
        recent = FinanceOperation.objects.filter(created_at__gte=timezone.now()-timedelta(days=7))
        if not actor.company_scope:
            recent=recent.filter(administrator=actor)
        unusual=recent.filter(kind='correction').count()+recent.filter(status='rejected').count()
        if unusual>=3:result.append({'level':'warning','text':f'7 kun ichida {unusual} ta tuzatish yoki rad etish qayd etilgan. Manbalarni tekshiring.','url':'/management/enterprise/finance/'})
    return result


WIDGETS = {
    'employees': ('Xodimlar statistikasi', 'employees.view'),
    'activity': ('Oxirgi harakatlar', 'audit.view'),
    'applications': ('Mijoz murojaatlari', 'inquiries.manage'),
    'approvals': ('Tasdiq kutayotgan amallar', 'finance.view'),
    'monthly': ('Oylik tushum va xarajatlar', 'finance.view'),
    'ranking': ('Jamoa reytingi', 'performance.view'),
    'insights': ('Boshqaruv ogohlantirishlari', None),
    'finance': ('Moliyaviy holat', 'finance.view'),
    'balance': ('Shaxsiy balans', 'finance.balance'),
    'projects': ('Loyihalar', 'projects.own'),
    'schedule': ('Ish jadvali', 'schedule.view'),
    'performance': ('Faoliyat baholari', 'performance.self'),
    'notifications': ('Bildirishnomalar', None),
    'archives': ('Loyiha fayllari', 'archive.use'),
}


def allowed_widgets(actor):
    return {key:label for key,(label,cap) in WIDGETS.items() if cap is None or actor.has_cap(cap)}
