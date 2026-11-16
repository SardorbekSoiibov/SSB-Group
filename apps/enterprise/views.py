from apps.core.currencies import SUPPORTED_CURRENCIES as CURRENCIES
import csv
import hashlib
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth, TruncYear
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from urllib.parse import urlencode
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from apps.accounts.models import User
from apps.accounts.policies import visible_employees
from apps.core.models import WorkspaceSettings
from apps.audit.services import record
from apps.crm.models import Project, Task
from apps.crm.policies import visible_projects
from apps.notifications.models import Notification
from . import finance, operations, schedule_ai, weekly_rating
from .archive_access import active_archives, has_archive_access, remove_archive
from .forms import OperationForm, RuleForm, ShiftForm, ArchiveForm, ArchiveUnlockForm, ArchiveCodeForm, ReviewForm
from .models import FinanceOperation, ApprovalRule, LedgerEntry, WorkShift, ProjectArchive, ArchiveAccess, PerformanceReview, ReviewApproval, DashboardLayout
from .insights import allowed_widgets, management_insights
from apps.crm.views.base import paginate


def fail(request, error):
    messages.error(request, ' '.join(error.messages) if isinstance(error, ValidationError) else str(error))


def visible_operations(actor):
    if not actor.has_cap('finance.view'):
        return FinanceOperation.objects.none()
    qs = FinanceOperation.objects.select_related('employee','project','administrator')
    if actor.company_scope:
        return qs
    return qs.filter(Q(employee__in=visible_employees(actor)) | Q(project__in=visible_projects(actor)) | Q(administrator=actor))


WEEKDAYS=('Dushanba','Seshanba','Chorshanba','Payshanba','Juma','Shanba','Yakshanba')
MONTHS=('yanvar','fevral','mart','aprel','may','iyun','iyul','avgust','sentabr','oktabr','noyabr','dekabr')
SCHEDULE_MAX_DAYS=42


def _week_start(day):
    return day-timedelta(days=day.weekday())


def _period_query(start,end):
    return urlencode({'dan':start.isoformat(),'gacha':end.isoformat()})


def _period_label(start,end):
    if (start.year,start.month)==(end.year,end.month):
        return f'{start.day}–{end.day} {MONTHS[end.month-1]} {end.year}'
    if start.year==end.year:
        return f'{start.day} {MONTHS[start.month-1]} – {end.day} {MONTHS[end.month-1]} {end.year}'
    return f'{start.day} {MONTHS[start.month-1]} {start.year} – {end.day} {MONTHS[end.month-1]} {end.year}'


def _schedule_days(shifts,start,end,today):
    by_day={}
    for shift in shifts:
        begins=timezone.localtime(shift.starts_at).date()
        shift.overnight=timezone.localtime(shift.ends_at).date()!=begins
        by_day.setdefault(begins,[]).append(shift)
    count=(end-start).days+1
    # A very long period lists only the days that have shifts, so the page stays readable.
    dates=[start+timedelta(days=i) for i in range(count)] if count<=SCHEDULE_MAX_DAYS else sorted(by_day)
    return [{'date':day,'name':WEEKDAYS[day.weekday()],'month':MONTHS[day.month-1],'is_today':day==today,'shifts':by_day.get(day,[])} for day in dates]


def _schedule_stats(shifts):
    active=[shift for shift in shifts if not shift.cancelled]
    hours=sum((shift.ends_at-shift.starts_at).total_seconds() for shift in active)/3600
    return {'shifts':len(active),'people':len({shift.employee_id for shift in active}),'hours':f'{hours:.1f}'.removesuffix('.0'),'cancelled':len(shifts)-len(active)}


def date_filters(request):
    today = timezone.localdate()
    try:
        start = parse_date(request.GET.get('dan','')) or today.replace(day=1)
        end = parse_date(request.GET.get('gacha','')) or today
    except ValueError:
        start, end = today.replace(day=1), today
    return (start,end) if start<=end else (end,start)


@never_cache
@login_required
def overview(request):
    widgets = allowed_widgets(request.user)
    layout = DashboardLayout.objects.filter(user=request.user).first()
    defaults={'founder':['employees','ranking','activity'],
              'cofounder':['ranking','notifications'],
              'management':['employees','activity'],
              'employee':['performance','archives','notifications']}
    selected = layout.widgets if layout else [{"key":key,"size":"normal"} for key in defaults.get(request.user.dashboard_kind,defaults['employee']) if key in widgets]
    selected = [item for item in selected if isinstance(item,dict) and item.get('key') in widgets]
    widget_rows = [{**item,'label':widgets[item['key']],'enabled':True} for item in selected]
    used = {item['key'] for item in selected}
    widget_rows += [{'key':key,'label':label,'size':'normal','enabled':False} for key,label in widgets.items() if key not in used]
    shifts = WorkShift.objects.filter(cancelled=False, ends_at__gte=timezone.now()).select_related('employee')
    shifts = shifts.filter(employee__in=visible_employees(request.user)) if request.user.has_cap('schedule.manage') else shifts.filter(employee=request.user)
    ledger = finance.visible_entries(request.user)
    currencies = sorted(set(ledger.values_list('currency',flat=True)))
    financial = [finance.company_summary(ledger,currency) for currency in currencies] if request.user.has_cap('finance.view') else []
    month = timezone.localdate().replace(day=1)
    monthly = [finance.company_summary(ledger.filter(created_at__date__gte=month),currency) for currency in currencies] if request.user.has_cap('finance.view') else []
    from apps.audit.models import AuditEvent
    from apps.crm.models import Inquiry
    from apps.crm.policies import visible_inquiries
    ranks = PerformanceReview.objects.filter(employee__in=visible_employees(request.user),reviewapproval__isnull=False).select_related('employee').order_by('employee_id','-period_end','-created_at').distinct('employee_id') if request.user.has_cap('performance.view') else []
    from django.db.models.functions import TruncMonth
    today=timezone.localdate()
    my_projects=visible_projects(request.user)
    open_projects=my_projects.exclude(status__in=[Project.Status.COMPLETED,Project.Status.ARCHIVED,Project.Status.CANCELLED])
    # Bosh sahifa puli qaysi valyutada bo'lsa, o'shani ko'rsatadi (oxirgi moliyaviy harakat valyutasi).
    currency=request.GET.get('currency')
    if currency not in dict(CURRENCIES):
        own=ledger if request.user.has_cap('finance.view') else ledger.filter(employee=request.user)
        currency=own.order_by('-created_at').values_list('currency',flat=True).first() or WorkspaceSettings.load().default_currency
    if currency not in dict(CURRENCIES):currency='UZS'
    awaiting_payouts=sum(1 for op in finance.payouts().filter(currency=currency) if finance.payout_state(op)=='pending') if request.user.is_owner else 0
    chart_rows=list(ledger.filter(currency=currency,category='receipt').annotate(month=TruncMonth('created_at')).values('month').annotate(total=Sum('amount')).order_by('-month')[:6]) if request.user.has_cap('finance.view') else []
    chart_rows.reverse()
    role_template={'founder':'founder','cofounder':'cofounder','management':'director','employee':'employee'}.get(request.user.dashboard_kind,'employee')
    return render(request,f'boshqaruv/dashboards/{role_template}.html',{'selected':selected,'available':widgets,'widgets':widget_rows,
        'kpi_active_projects':open_projects.count(),
        'kpi_review':open_projects.filter(status=Project.Status.UNDER_REVIEW).count(),
        'kpi_overdue':open_projects.filter(deadline__lt=today).count(),
        'kpi_completed_projects':my_projects.filter(status=Project.Status.COMPLETED).count(),
        'current_summary':finance.company_summary(ledger,currency) if request.user.has_cap('finance.view') else None,
        'current_balance':finance.employee_balance(request.user,currency),'currency':currency,'currencies':CURRENCIES,
        'awaiting_payouts':awaiting_payouts,
        'income_chart':{'labels':[row['month'].strftime('%m.%Y') for row in chart_rows],'values':[str(row['total']) for row in chart_rows],'label':'Mijoz tushumi'},
        'has_income_chart':bool(chart_rows),
        'dashboard_kind':request.user.dashboard_kind,
        'monthly':monthly,'month':month,
        'employee_count':visible_employees(request.user).count() if request.user.has_cap('employees.view') else 0,
        'active_employee_count':visible_employees(request.user).filter(status=User.Status.ACTIVE).count() if request.user.has_cap('employees.view') else 0,
        'recent_activity':AuditEvent.objects.select_related('actor')[:6] if request.user.has_cap('audit.view') and request.user.company_scope else [],
        'applications':visible_inquiries(request.user)[:6] if request.user.has_cap('inquiries.manage') else [],
        'pending':visible_operations(request.user).filter(status='pending')[:6],
        'ranking':sorted(list(ranks),key=lambda item:item.score,reverse=True)[:6],
        'insights':management_insights(request.user),'financial':financial,
        'balances':[finance.employee_balance(request.user,currency) for currency in currencies],
        'shifts':shifts[:6],'projects':visible_projects(request.user).with_progress().exclude(status=Project.Status.ARCHIVED)[:6],
        'notifications':Notification.objects.filter(recipient=request.user)[:6],
        'reviews':PerformanceReview.objects.filter(employee=request.user,reviewapproval__isnull=False)[:4],
        'archives':active_archives().select_related('project').order_by('-created_at')[:4] if has_archive_access(request) else []})


@login_required
@require_POST
def layout_save(request):
    finance.require(request.user,'dashboard.customize')
    import json
    try:
        items = json.loads(request.POST.get('layout','[]'))
        allowed = allowed_widgets(request.user)
        if not isinstance(items,list) or len(items)>len(allowed):raise ValueError()
        seen=set()
        for item in items:
            if not isinstance(item,dict) or item.get('key') not in allowed or item['key'] in seen or item.get('size') not in ['normal','wide']:raise ValueError()
            seen.add(item['key'])
        DashboardLayout.objects.update_or_create(user=request.user,defaults={'widgets':items})
        record(request.user,'dashboard.layout',None,{'widgets':items})
        messages.success(request,'Dashboard joylashuvi saqlandi.')
    except (ValueError,TypeError):
        messages.error(request,'Vidjetlar ro‘yxati noto‘g‘ri.')
    return redirect('enterprise:overview')


@login_required
def financial(request):
    actor=request.user
    personal=request.resolver_match.url_name=='balance'
    form=OperationForm(request.POST or None,actor=actor) if actor.has_cap('finance.manage') and not personal else None
    if request.method=='POST':
        finance.require(actor,'finance.manage')
        if personal:raise PermissionDenied
        if form.is_valid():
            data=form.cleaned_data
            try:
                operation=finance.request_operation(actor,kind=data['kind'],amount=data['amount'],currency=data['currency'],description=data['description'],
                    idempotency_key=data['idempotency_key'],employee=data['employee'],project=data['project'],payload=form.payload())
                messages.success(request,f'Amal qayd qilindi: {operation.pk} · {operation.get_status_display()}')
                return redirect('enterprise:finance')
            except ValidationError as error:form.add_error(None,error)
    entries=finance.visible_entries(actor).select_related('employee','project','administrator','operation','agreement')
    if personal:entries=entries.filter(employee=actor)
    # Xodimning o'z hisobi: puli qaysi valyutada bo'lsa, o'sha ochiladi (oxirgi harakat valyutasi).
    my_currencies=[c for c in dict(CURRENCIES) if LedgerEntry.objects.filter(employee=actor,currency=c).exists()]
    currency=request.GET.get('currency')
    if currency not in dict(CURRENCIES):
        latest=LedgerEntry.objects.filter(employee=actor).order_by('-created_at').values_list('currency',flat=True).first() if personal else None
        currency=latest or WorkspaceSettings.load().default_currency
    if currency not in dict(CURRENCIES):currency='UZS'
    summary=finance.company_summary(entries,currency) if actor.has_cap('finance.view') and not personal else None
    entries=entries.filter(currency=currency)
    query=request.GET.get('q','').strip()[:150]
    if query:entries=entries.filter(Q(description__icontains=query)|Q(project__name__icontains=query)|Q(employee__username__icontains=query))
    category=request.GET.get('category','')
    if category in dict(LedgerEntry.Category.choices):entries=entries.filter(category=category)
    if request.GET.get('dan') or request.GET.get('gacha'):
        start,end=date_filters(request);entries=entries.filter(created_at__date__range=[start,end])
    order=request.GET.get('order','newest')
    entries=entries.order_by(*{'newest':['-created_at','id'],'oldest':['created_at','id'],'amount':['-amount','id']}.get(order,['-created_at','id']))
    sums={row['category']:row['total'] for row in entries.order_by().values('category').annotate(total=Sum('amount'))}
    ledger_totals={'count':entries.count(),'in':sums.get('receipt',Decimal('0')),
                   'out':sums.get('paid',Decimal('0'))+sums.get('expense',Decimal('0')),
                   'accrued':sums.get('earning',Decimal('0'))+sums.get('salary',Decimal('0'))+sums.get('bonus',Decimal('0'))}
    page=paginate(request,entries,30)
    breakdown={row['category']:row['total'] for row in LedgerEntry.objects.filter(employee=actor,currency=currency).values('category').annotate(total=Sum('amount'))}
    return render(request,'boshqaruv/business/finance.html',{'form':form,'entries':page,'page':page,'q':query,'category':category,'categories':LedgerEntry.Category.choices,'order':order,
        'personal_salary':breakdown.get('salary',Decimal('0')),'personal_bonus':breakdown.get('bonus',Decimal('0')),'personal_project_earnings':breakdown.get('earning',Decimal('0')),
        'operations':visible_operations(actor).filter(status='pending')[:60] if not personal else [], 'currency':currency,'currencies':CURRENCIES,
        'summary':summary,'ledger_totals':ledger_totals,'my_currencies':my_currencies,'personal':personal,'filtered':bool(query or category or request.GET.get('dan') or request.GET.get('gacha')),
        **_payout_context(actor,currency,personal),
        'balance':finance.employee_balance(actor,currency),'is_company':actor.has_cap('finance.view') and not personal})


@login_required
def operation_new(request):
    """Moliyaviy amal kiritish: turini tanlash, faqat kerakli maydonlar va pul qanday bo'linishini oldindan ko'rish."""
    actor=request.user
    finance.require(actor,'finance.manage')
    kind=request.POST.get('kind') or request.GET.get('kind') or 'receipt'
    if kind=='payment':
        return redirect('enterprise:payout_create')
    initial={key:request.GET[key] for key in ('project','employee','currency') if request.GET.get(key)}
    initial['kind']=kind
    form=OperationForm(request.POST or None,actor=actor,initial=initial)
    if request.method=='POST' and form.is_valid():
        data=form.cleaned_data
        try:
            operation=finance.request_operation(actor,kind=data['kind'],amount=data['amount'],currency=data['currency'],description=data['description'],
                idempotency_key=data['idempotency_key'],employee=data['employee'],project=data['project'],payload=form.payload())
            if operation.status=='approved':
                messages.success(request,f'Saqlandi: {operation.get_kind_display()} · {finance.amount_text(operation.amount,operation.currency)}.')
            else:
                messages.info(request,f'{operation.get_kind_display()} Asoschi tasdig‘iga yuborildi.')
            target=f"{reverse('enterprise:finance')}?currency={operation.currency}#reyestr"
            return JsonResponse({'redirect':target}) if _is_modal(request) else redirect(target)
        except ValidationError as error:
            form.add_error(None,error)
    # Har bir loyihaning amaldagi kelishuvi: mijoz to'lovi qanday bo'linishini oldindan ko'rsatish uchun.
    from .models import AgreementSnapshot
    projects=list(form.fields['project'].queryset.only('pk','name'))
    latest={}
    for item in AgreementSnapshot.objects.filter(project__in=projects).order_by('project_id','-version'):
        latest.setdefault(item.project_id,item)
    people={u.pk:u.display_name for u in User.objects.filter(pk__in={int(s['employee']) for a in latest.values() for s in a.shares})}
    agreements={str(pid):{'currency':a.currency,'amount':str(a.amount),'company':str(a.company_percent),
                          'shares':[{'name':people.get(int(s['employee']),'Xodim'),'percent':str(s['percent'])} for s in a.shares]}
                for pid,a in latest.items()}
    kinds=[k for k,_ in form.fields['kind'].choices if k!='payment']
    template='boshqaruv/business/_operation_body.html' if _is_modal(request) else 'boshqaruv/business/operation_new.html'
    return render(request,template,{'form':form,'kind':kind,'kinds':kinds,'agreements':agreements})


def _is_modal(request):
    """Moliya sahifasidagi modal so'rovi: sahifaning faqat ichki qismi qaytariladi."""
    return request.headers.get('X-Modal')=='1'


@login_required
@require_POST
def decision(request, pk):
    try:
        finance.decide(request.user,pk,request.POST.get('decision')=='approve',request.POST.get('reason',''))
        messages.success(request,'Moliyaviy qaror saqlandi.')
    except (ValidationError, FinanceOperation.DoesNotExist) as error:
        fail(request,error)
    return redirect('enterprise:finance')


@login_required
def entry_detail(request, pk):
    entry=get_object_or_404(finance.visible_entries(request.user).select_related('employee','project','administrator','operation','agreement','corrects'),pk=pk)
    return render(request,'boshqaruv/business/entry.html',{'entry':entry,'decisions':entry.operation.decisions.select_related('administrator'),
        'corrections':finance.visible_entries(request.user).filter(corrects=entry),'can_see_operation':request.user.has_cap('finance.view')})


@login_required
def rules(request):
    finance.require(request.user,'finance.rules')
    instance=get_object_or_404(ApprovalRule,pk=request.GET['edit']) if request.GET.get('edit') else None
    form=RuleForm(request.POST or None,instance=instance)
    if request.method=='POST' and form.is_valid():
        item=form.save(commit=False);item.updated_by=request.user;item.save()
        record(request.user,'finance.rule_changed',item,{'kind':item.kind,'threshold':str(item.threshold),'approvals':item.approvals})
        messages.success(request,'Yangi qoida faqat keyingi so‘rovlarga qo‘llanadi.')
        return redirect('enterprise:rules')
    return render(request,'boshqaruv/business/form.html',{'form':form,'title':'Moliyaviy tasdiqlash qoidalari','items':ApprovalRule.objects.all(),'mode':'rules'})


@login_required
def schedule(request):
    manager=request.user.has_cap('schedule.manage')
    shift=get_object_or_404(WorkShift,pk=request.GET['edit'],employee__in=visible_employees(request.user)) if manager and request.GET.get('edit') else None
    initial={'employee':shift.employee_id,'starts_at':shift.starts_at,'ends_at':shift.ends_at,'location':shift.location,'notes':shift.notes} if shift else {'location':'Ofis'}
    form=ShiftForm(request.POST or None,actor=request.user,initial=initial,editing=bool(shift)) if manager else None
    # A shift belongs to one person; moving it to someone else is a new shift.
    if shift:form.fields['employee'].disabled=True
    if request.method=='POST':
        finance.require(request.user,'schedule.manage')
        if request.POST.get('action')=='copy_week':
            monday=_week_start(parse_date(request.POST.get('hafta') or '') or timezone.localdate())
            created,skipped=operations.copy_week(request.user,monday)
            if created:messages.success(request,f'O‘tgan haftadan {len(created)} ta smena ko‘chirildi.'+(f' {skipped} tasi band bo‘lgani uchun o‘tkazildi.' if skipped else ''))
            else:messages.error(request,'Ko‘chiradigan smena topilmadi (o‘tgan hafta bo‘sh yoki vaqtlar band).')
            return redirect(reverse('enterprise:schedule')+'?'+_period_query(monday,monday+timedelta(days=6)))
        if form.is_valid():
            data=dict(form.cleaned_data)
            try:
                if shift:
                    data.pop('days',None);data.pop('repeat',None)
                    saved=operations.save_shift(request.user,**data,shift_id=shift.pk)
                    messages.success(request,'Smena saqlandi va xodim xabardor qilindi.')
                else:
                    days,repeat=data.pop('days',None),data.pop('repeat',1)
                    created,skipped=operations.save_shift_series(request.user,**data,days=days,repeat=repeat)
                    saved=created[0]
                    messages.success(request,(f'{len(created)} ta smena qo‘shildi' if len(created)>1 else 'Smena qo‘shildi')+' va xodim xabardor qilindi.'
                                     +(f' {skipped} tasi band yoki o‘tgan kun bo‘lgani uchun o‘tkazildi.' if skipped else ''))
                monday=_week_start(timezone.localtime(saved.starts_at).date())
                return redirect(reverse('enterprise:schedule')+'?'+_period_query(monday,monday+timedelta(days=6)))
            except ValidationError as error:form.add_error(None,error)
    # Jadval har doim to'liq hafta: dushanbadan yakshanbagacha (tanlangan sana qaysi haftada bo'lsa, o'sha hafta).
    try:
        picked=parse_date(request.GET.get('dan') or '') or timezone.localdate()
    except ValueError:
        picked=timezone.localdate()
    start=_week_start(picked);end=start+timedelta(days=6)
    shifts=WorkShift.objects.filter(cancelled=False,starts_at__date__range=[start,end]).select_related('employee','administrator')
    shifts=shifts.filter(employee__in=visible_employees(request.user)) if manager else shifts.filter(employee=request.user)
    shifts=list(shifts)
    today=timezone.localdate();span=timedelta(days=7);monday=_week_start(today)
    return render(request,'boshqaruv/business/schedule.html',{'form':form,'shifts':shifts,'start':start,'end':end,'manager':manager,
        'today':today,'editing':bool(shift),'days':_schedule_days(shifts,start,end,today),'stats':_schedule_stats(shifts),
        'period_label':_period_label(start,end),'period_query':_period_query(start,end),
        'prev_query':_period_query(start-span,end-span),'next_query':_period_query(start+span,end+span),
        'week_query':_period_query(monday,monday+timedelta(days=6)),'is_this_week':start==monday,
        'has_last_week':manager and WorkShift.objects.filter(cancelled=False,employee__in=visible_employees(request.user),
            starts_at__date__range=[start-timedelta(days=7),start-timedelta(days=1)]).exists()})


def _rating_week(value):
    try:
        return parse_date(value or '')
    except ValueError:
        return None


def _rating_places(request,people):
    places={}
    for person in people:
        raw=request.POST.get(f'place_{person.pk}','')
        if raw.isdigit() and 0<int(raw)<=len(people):places[person.pk]=int(raw)
    return places


@never_cache
@login_required
def rating(request):
    manager=request.user.has_cap(weekly_rating.MANAGE)
    today=timezone.localdate()
    weekly_rating.announce_due(today)
    weeks=weekly_rating.editable_weeks(today)
    current=weeks[0]
    context={'manager':manager,'next_label':f'{current.day} {weekly_rating.MONTHS[current.month-1]}, yakshanba 00:00','editing':False}
    wanted=_rating_week(request.POST.get('hafta') if request.method=='POST' else request.GET.get('hafta'))
    posted={}
    prize=None
    if request.method=='POST':
        finance.require(request.user,weekly_rating.MANAGE)
        people=list(weekly_rating.rated_people())
        posted=_rating_places(request,people)
        prize=request.POST.get('prize','')
        try:
            saved=weekly_rating.save_places(request.user,wanted or current,prize,posted,today)
            messages.success(request,'Reyting saqlandi. U yakshanba 00:00 da e’lon qilinadi.' if saved.publish_on>today else 'Reyting e’lon qilindi.')
            return redirect(reverse('enterprise:rating')+('?belgilash=1' if saved.publish_on>today else ''))
        except ValidationError as error:
            messages.error(request,error.messages[0])
    if manager and (request.method=='POST' or request.GET.get('belgilash')):
        week=wanted if wanted in weeks else current
        stored=weekly_rating.WeeklyRating.objects.filter(publish_on=week).first()
        rows=weekly_rating.week_facts(week)
        chosen=posted if request.method=='POST' else dict(stored.places.values_list('employee_id','place')) if stored else {}
        for row in rows:row['chosen']=chosen.get(row['person'].pk)
        closed=weeks[1] if len(weeks)>1 and week==current else None
        context.update(editing=True,week=week,week_label=weekly_rating.week_label(week),rows=rows,place_numbers=range(1,len(rows)+1),
            prize=prize if prize is not None else (stored.prize if stored else ''),overdue_week=closed,
            overdue_label=weekly_rating.week_label(closed) if closed else '')
        return render(request,'boshqaruv/business/rating.html',context)
    public=weekly_rating.published(today)
    shown=(public.filter(publish_on=wanted).first() if wanted else None) or public.first()
    if shown:
        places=list(shown.places.select_related('employee__role'))
        context.update(shown=shown,shown_label=weekly_rating.week_label(shown.publish_on),winner=next((item for item in places if item.place==1),None),
            others=[item for item in places if item.place!=1],
            older=public.filter(publish_on__lt=shown.publish_on).values_list('publish_on',flat=True).first(),
            newer=public.filter(publish_on__gt=shown.publish_on).order_by('publish_on').values_list('publish_on',flat=True).first())
    return render(request,'boshqaruv/business/rating.html',context)


def _ai_payload(request):
    finance.require(request.user,'schedule.manage')
    try:
        data=json.loads(request.body or b'{}')
    except ValueError:
        return None
    return data if isinstance(data,dict) else None


@login_required
@require_POST
def schedule_ai_ask(request):
    data=_ai_payload(request)
    if data is None:return JsonResponse({'error':'So‘rovni o‘qib bo‘lmadi.'},status=400)
    week=parse_date(str(data.get('week') or ''))
    return JsonResponse(schedule_ai.propose(request.user,str(data.get('text') or '')[:1000],_week_start(week) if week else None))


@login_required
@require_POST
def schedule_ai_apply(request):
    data=_ai_payload(request)
    if data is None:return JsonResponse({'error':'So‘rovni o‘qib bo‘lmadi.'},status=400)
    try:
        saved,skipped=schedule_ai.apply(request.user,data.get('shifts'))
    except ValidationError as error:
        return JsonResponse({'error':error.messages[0]},status=400)
    if not saved:
        return JsonResponse({'error':'Hech narsa qo‘shilmadi: bu vaqtlar band.'},status=400)
    text=f'SSB AI {len(saved)} ta smena qo‘shdi va xodimlar xabardor qilindi.'
    messages.success(request,text+(f' {skipped} tasi band bo‘lgani uchun o‘tkazib yuborildi.' if skipped else ''))
    monday=_week_start(timezone.localtime(saved[0].starts_at).date())
    return JsonResponse({'url':reverse('enterprise:schedule')+'?'+_period_query(monday,monday+timedelta(days=6))})


@login_required
@require_POST
def cancel_shift(request, pk):
    shift=get_object_or_404(WorkShift,pk=pk,employee__in=visible_employees(request.user))
    try:
        operations.delete_shift(request.user,shift)
        messages.success(request,'Smena jadvaldan butunlay o‘chirildi.')
    except ValidationError as error:fail(request,error)
    monday=_week_start(timezone.localtime(shift.starts_at).date())
    return redirect(reverse('enterprise:schedule')+'?'+_period_query(monday,monday+timedelta(days=6)))


@never_cache
@login_required
def data_reset(request):
    """Founder only. Step 1 lists what goes, step 2 is the founder's password; then the section starts from zero."""
    from apps.core.secure_delete import confirm_delete_password
    from . import data_reset as reset
    if not request.user.is_owner:
        raise PermissionDenied('Bu bo‘lim faqat Asoschi uchun.')
    if request.method=='POST':
        key=request.POST.get('bolim','')
        if key not in reset.SECTIONS:
            messages.error(request,'Bo‘lim noto‘g‘ri tanlangan. Hech narsa o‘chirilmadi.')
        elif confirm_delete_password(request):
            removed=reset.reset_section(request.user,key,request)
            messages.success(request,f'«{reset.SECTIONS[key][0]}» bo‘limi tozalandi ({removed} ta yozuv). Bo‘lim noldan boshlanadi.')
        return redirect('enterprise:data_reset')
    return render(request,'boshqaruv/business/data_reset.html',{'sections':reset.sections(request.user)})


ARCHIVE_SORTS={'new':('-created_at','-pk'),'old':('created_at','pk'),'name':('project_name','filename','pk'),'size':('-size','-pk')}


def _archive_page(request, *, form=None, unlock_form=None, code_form=None, status=200):
    from .archive_access import has_archive_access, require_staff
    require_staff(request.user)
    policy=ArchiveAccess.load()
    unlocked=has_archive_access(request,policy)
    items=active_archives().select_related('project','uploader') if unlocked else ProjectArchive.objects.none()
    query=request.GET.get('q','').strip()[:150]
    if query:items=items.filter(Q(filename__icontains=query)|Q(project_name__icontains=query)|Q(project__name__icontains=query)|Q(uploader__username__icontains=query))
    sort=request.GET.get('sort','new')
    if sort not in ARCHIVE_SORTS:sort='new'
    page=paginate(request,items.order_by(*ARCHIVE_SORTS[sort]),24)
    stats=active_archives().aggregate(total=Count('pk'),authors=Count('uploader',distinct=True),size=Sum('size')) if unlocked else {}
    return render(request,'boshqaruv/business/archives.html',{
        'form':form if form is not None else ArchiveForm(actor=request.user),
        'unlock_form':unlock_form if unlock_form is not None else ArchiveUnlockForm(),
        'code_form':code_form if code_form is not None else ArchiveCodeForm(),
        'unlocked':unlocked,'code_configured':bool(policy.access_hash),'code_updated_at':policy.updated_at,
        'items':page,'page':page,'q':query,'sort':sort,'stats':stats,'founder':request.user.is_owner},status=status)


@never_cache
@login_required
def archives(request):
    from .archive_access import has_archive_access, require_staff
    require_staff(request.user)
    if request.method=='POST':
        if not has_archive_access(request):
            messages.error(request,'Avval arxiv bo‘limining kodini kiriting.')
            return _archive_page(request,status=403)
        form=ArchiveForm(request.POST,request.FILES,actor=request.user)
        if form.is_valid():
            try:
                operations.upload_archive(request,form.cleaned_data['project_name'],form.cleaned_data['file'],form.cleaned_data['upload_key'])
                messages.success(request,'Fayl umumiy himoyalangan arxivga saqlandi.')
                return redirect('enterprise:archives')
            except ValidationError as error:form.add_error(None,error)
        return _archive_page(request,form=form)
    return _archive_page(request)


@never_cache
@login_required
@require_POST
def archive_code(request):
    from .archive_access import grant_access, require_staff
    require_staff(request.user)
    if not request.user.is_owner:raise PermissionDenied
    form=ArchiveCodeForm(request.POST)
    if form.is_valid():
        try:
            policy=operations.set_archive_code(request.user,form.cleaned_data['code'])
            grant_access(request,policy)
            messages.success(request,'Umumiy arxiv kodi yangilandi. Boshqa sessiyalarda yangi kod qayta kiritiladi.')
            return redirect('enterprise:archives')
        except ValidationError as error:form.add_error(None,error)
    return _archive_page(request,code_form=form)


@never_cache
@login_required
@require_POST
def archive_unlock(request):
    form=ArchiveUnlockForm(request.POST)
    if form.is_valid():
        try:
            operations.verify_archive_code(request,form.cleaned_data['code'])
            messages.success(request,'Umumiy arxiv bir soatga ochildi.')
            return redirect('enterprise:archives')
        except ValidationError as error:form.add_error('code',error)
    return _archive_page(request,unlock_form=form)


@never_cache
@login_required
@require_POST
def archive_lock(request):
    from .archive_access import GRANT_KEY
    request.session.pop(GRANT_KEY,None)
    return redirect('enterprise:archives')


@never_cache
@login_required
@require_POST
def archive_delete(request, pk):
    from apps.core.secure_delete import confirm_delete_password
    if not confirm_delete_password(request):return redirect('enterprise:archives')
    archive=remove_archive(request,pk)
    messages.success(request,f'“{archive.display_project_name}” loyihasi arxivdan o‘chirildi.')
    return redirect('enterprise:archives')


@never_cache
@login_required
def download_archive(request, pk):
    from .archive_access import has_archive_access, new_challenge, check_challenge
    import secrets
    if not has_archive_access(request):
        if request.method=='GET':
            messages.info(request,'Arxivga kirish uchun avval kodni kiriting.')
            return redirect('enterprise:archives')
        raise PermissionDenied('Avval arxiv bo‘limi kodini kiriting.')
    archive=get_object_or_404(active_archives().select_related('project','uploader'),pk=pk)
    error=''
    if request.method=='POST':
        if not check_challenge(request,archive.pk,request.POST.get('answer')):
            error='Javob noto‘g‘ri yoki misol muddati tugagan. Yangi misolni yeching.'
            record(request.user,'archive.challenge_failed',archive)
    if request.method!='POST' or error:
        return render(request,'boshqaruv/business/archive_download.html',
            {'archive':archive,'question':new_challenge(request,archive.pk),'error':error},status=400 if error else 200)
    try:
        opened=archive.file.open('rb')
        digest=hashlib.sha256()
        for chunk in opened.chunks():digest.update(chunk)
        if not secrets.compare_digest(digest.hexdigest(),archive.sha256):
            opened.close()
            record(request.user,'archive.integrity_failed',archive)
            raise PermissionDenied('Fayl yaxlitligi tekshiruvdan o‘tmadi. Asoschiga murojaat qiling.')
        opened.seek(0)
        response=FileResponse(opened,as_attachment=True,filename=archive.filename,content_type='application/octet-stream')
    except (FileNotFoundError,OSError):raise Http404('Saqlangan fayl topilmadi.')
    response['Cache-Control']='private, no-store';response['X-Content-Type-Options']='nosniff'
    # Lets the page see that the file really started, since a file response never reloads it.
    token=request.POST.get('download_token','')
    if token.isascii() and token.isalnum() and 8<=len(token)<=40:
        response.set_cookie('ssb_archive_download',token,max_age=120,samesite='Lax',secure=request.is_secure())
    record(request.user,'archive.downloaded',archive,{'sha256':archive.sha256})
    return response


@login_required
def performance(request):
    manager=request.user.has_cap('performance.manage')
    form=ReviewForm(request.POST or None,actor=request.user) if manager else None
    if request.method=='POST':
        finance.require(request.user,'performance.manage')
        if form.is_valid():
            try:
                data=form.cleaned_data
                operations.create_review(request.user,data['employee'],data['period_start'],data['period_end'],data['feedback'],data.get('quality_score'),data.get('director_score'))
                messages.success(request,'Baholash qoralamasi yaratildi. Yakuniy tasdiq talab qilinadi.')
                return redirect('enterprise:performance')
            except ValidationError as error:form.add_error(None,error)
    reviews=PerformanceReview.objects.select_related('employee','administrator').order_by('-period_end','-score')
    if request.user.has_cap('performance.view') or manager:reviews=reviews.filter(employee__in=visible_employees(request.user))
    else:reviews=reviews.filter(employee=request.user,reviewapproval__isnull=False)
    # The ranking is for the whole company: approved totals only. Comments and analysis stay in the reviews above.
    approved=PerformanceReview.objects.filter(reviewapproval__isnull=False,employee__is_active=True).select_related('employee__department')
    approved=approved.order_by('employee_id','-period_end','-created_at').distinct('employee_id')
    ranking=sorted(approved,key=lambda review:review.score,reverse=True)
    return render(request,'boshqaruv/business/performance.html',{'form':form,'reviews':reviews[:100],'ranking':ranking,'manager':manager,'ai_configured':bool(settings.PERFORMANCE_AI_ENDPOINT and settings.PERFORMANCE_AI_KEY)})


@login_required
@require_POST
def review_approve(request, pk):
    review=get_object_or_404(PerformanceReview,pk=pk)
    try:operations.approve_review(request.user,review);messages.success(request,'Baholash tasdiqlandi.')
    except ValidationError as error:fail(request,error)
    return redirect('enterprise:performance')


def _csv_value(value):
    if isinstance(value,(Decimal,int,float)):return str(value)
    value=str(value if value is not None else '')
    return "'"+value if value.lstrip().startswith(('=','+','-','@')) or value.startswith(('\t','\r','\n')) else value


@never_cache
@login_required
def reports(request):
    finance.require(request.user,'finance.view')
    from .reporting import ReportFilters, REPORTS
    filters=ReportFilters(request.GET,actor=request.user,currency=WorkspaceSettings.load().default_currency)
    if not filters.is_valid():
        return render(request,'boshqaruv/business/reports.html',{
            'filters':filters,'filter_errors':True,'filter_projects':visible_projects(request.user),
            'filter_employees':visible_employees(request.user),'filter_roles':[], 'rows':[], 'headers':[]},status=400)
    start,end=filters.cleaned_data['dan'],filters.cleaned_data['gacha']
    currency=filters.cleaned_data['currency'];name=filters.cleaned_data['report']
    # Writers use the exclusive version of this lock. Keep every report query in
    # the request transaction on the same committed financial state.
    if connection.vendor=='postgresql':
        with connection.cursor() as cursor:cursor.execute('SELECT pg_advisory_xact_lock_shared(73910233)')
    entries=finance.visible_entries(request.user).filter(currency=currency)
    selected_project=None;selected_employee=None;selected_role=None
    from apps.crm.views.base import int_param
    from apps.accounts.models import Role
    if request.GET.get('project'):
        selected_project=get_object_or_404(visible_projects(request.user),pk=int_param(request,'project'))
        entries=entries.filter(project=selected_project)
    if request.GET.get('employee'):
        selected_employee=get_object_or_404(visible_employees(request.user),pk=int_param(request,'employee'))
        entries=entries.filter(employee=selected_employee)
    roles=Role.objects.filter(users__in=visible_employees(request.user)).distinct()
    if request.GET.get('position'):
        selected_role=get_object_or_404(roles,pk=int_param(request,'position'))
        entries=entries.filter(employee__role=selected_role)
    project_scope=False
    if (selected_employee or selected_role) and name in ['daily','weekly','monthly','annual','profit','expenses']:
        project_ids=entries.exclude(project_id=None).values('project_id')
        entries=finance.visible_entries(request.user).filter(currency=currency,project_id__in=project_ids)
        project_scope=True
    period=entries.filter(operation__finalized_at__date__range=[start,end]);rows=[]
    headers=['Nomi / davr','Summa','Manba'];sources=period
    if name in ['daily','weekly','monthly','annual']:
        function={'daily':TruncDay,'weekly':TruncWeek,'monthly':TruncMonth,'annual':TruncYear}[name]
        sources=period.filter(category='receipt')
        rows=[[str(row['period'].date()),row['amount'],'Mijoz tushumi; reyestr'] for row in period.filter(category='receipt').annotate(period=function('operation__finalized_at')).values('period').annotate(amount=Sum('amount')).order_by('period')]
    elif name in ['earnings','bonuses','expenses','departments','payouts']:
        categories={'earnings':['earning','salary','bonus'],'bonuses':['bonus'],'expenses':['expense','salary','bonus'],'departments':['earning','salary','bonus'],'payouts':['paid']}[name]
        sources=period.filter(category__in=categories)
        field='employee__department__name' if name=='departments' else 'employee__username'
        rows=[[row[field] or 'Kompaniya',row['amount'],'Tasdiqlangan reyestr'] for row in period.filter(category__in=categories).values(field).annotate(amount=Sum('amount')).order_by(field)]
    elif name=='profit':
        sources=period.exclude(category='paid')
        totals=finance.company_summary(period,currency)
        rows=[['Kompaniya ulushi',totals['company_revenue'],'Mijoz tushumi − loyiha ulushlari'],['Xarajatlar',totals['expenses'],'Ish haqi + bonus + operatsion xarajat'],['Sof foyda',totals['net_profit'],'Kompaniya ulushi − xarajatlar']]
    elif name=='performance':
        finance.require(request.user,'performance.view')
        headers=['Xodim','Bo‘lim','Davr','Baho / 100','Tasdiqlangan tahlil manbasi']
        reviews=PerformanceReview.objects.filter(employee__in=visible_employees(request.user),reviewapproval__isnull=False,period_end__range=[start,end]).select_related('employee__department').order_by('-score')
        if selected_employee:reviews=reviews.filter(employee=selected_employee)
        if selected_role:reviews=reviews.filter(employee__role=selected_role)
        if selected_project:reviews=reviews.filter(employee__in=selected_project.team())
        rows=[[item.employee.display_name,str(item.employee.department or ''),f'{item.period_start} — {item.period_end}',item.score,item.analysis_source] for item in reviews]
    elif name=='profitability':
        headers=['Loyiha','Mijoz tushumi','Xodim ulushi','Kompaniya ulushi','Xarajat','Sof foyda','Mijoz qarzi','Xodim qarzi']
        projects=visible_projects(request.user).filter(financial_agreements__currency=currency,financial_agreements__operation__finalized_at__date__lte=end).distinct()
        if selected_project:projects=projects.filter(pk=selected_project.pk)
        if selected_employee:projects=projects.filter(financial_agreements__shares__contains=[{'employee':selected_employee.pk}],financial_agreements__operation__finalized_at__date__lte=end)
        if selected_role:projects=projects.filter(ledger_entries__employee__role=selected_role,ledger_entries__operation__finalized_at__date__lte=end).distinct()
        sources=finance.visible_entries(request.user).filter(currency=currency,project__in=projects,operation__finalized_at__date__lte=end)
        for project in projects:
            agreement=project.financial_agreements.filter(currency=currency,operation__finalized_at__date__lte=end).first()
            data=finance.company_summary(finance.visible_entries(request.user).filter(project=project,operation__finalized_at__date__lte=end),currency)
            data['outstanding_client']=max(Decimal('0'),agreement.amount-data['client_receipts'])
            rows.append([project.name,data['client_receipts'],data['client_receipts']-data['company_revenue'],data['company_revenue'],data['expenses'],data['net_profit'],data['outstanding_client'],data['employee_payable']])
    elif name=='outstanding':
        headers=['Xodim','Hisoblangan','To‘langan','Qolgan']
        employees=visible_employees(request.user)
        if selected_employee:employees=employees.filter(pk=selected_employee.pk)
        if selected_role:employees=employees.filter(role=selected_role)
        sources=entries.filter(operation__finalized_at__date__lte=end,category__in=finance.EARNINGS+['paid']).exclude(employee=None)
        balances=sources.values('employee_id').annotate(
            earned=Sum('amount',filter=Q(category__in=finance.EARNINGS)),paid=Sum('amount',filter=Q(category='paid')))
        by_employee={item['employee_id']:item for item in balances}
        for employee in employees:
            data=by_employee.get(employee.pk,{})
            earned,paid=data.get('earned') or Decimal('0'),data.get('paid') or Decimal('0')
            if earned-paid:rows.append([employee.display_name,earned,paid,earned-paid])
    else:raise Http404
    source_count=sources.count()
    report_title=dict(REPORTS)[name]
    if name=='performance':source_count=len(rows)
    if request.GET.get('export') in ['xlsx','pdf']:
        from .exports import export_report
        record(request.user,'finance.report_export',None,{'report':name,'format':request.GET['export'],'currency':currency,'from':str(start),'to':str(end)})
        return export_report(request.GET['export'],f'ssb-{name}-{currency}',headers,rows,f'SSB Boshqaruv · {report_title} · {start} — {end} · {currency}')
    if request.GET.get('export')=='csv':
        response=HttpResponse(content_type='text/csv; charset=utf-8');response['Content-Disposition']=f'attachment; filename="ssb-{name}-{currency}.csv"'
        response.write('\ufeff');writer=csv.writer(response);writer.writerow(headers)
        for row in rows:writer.writerow([_csv_value(value) for value in row])
        record(request.user,'finance.report_export',None,{'report':name,'currency':currency,'from':str(start),'to':str(end)})
        response['Cache-Control']='private, no-store'
        return response
    chart=[]
    if name in ['daily','weekly','monthly','annual'] and rows:
        maximum=max(abs(row[1]) for row in rows) or Decimal('1')
        chart=[{'label':row[0],'amount':row[1],'height':(max(2,int(abs(row[1])/maximum*100)) if row[1] else 0),'negative':row[1]<0} for row in rows[-24:]]
    return render(request,'boshqaruv/business/reports.html',{'filters':filters,'source_entries':sources.select_related('project','employee','operation').order_by('-operation__finalized_at','pk')[:30] if name!='performance' else [],'source_count':source_count,'report_title':report_title,'headers':headers,'rows':rows,'chart':chart,'start':start,'end':end,'currency':currency,'report':name,'currencies':CURRENCIES,'all_time':name in ['profitability','outstanding'],
        'filter_projects':visible_projects(request.user),'filter_employees':visible_employees(request.user),'filter_roles':roles,
        'selected_project':selected_project,'selected_employee':selected_employee,'selected_role':selected_role,'project_scope':project_scope})


# ---------------------------------------------------------------- payouts

def _with_state(operations):
    items=list(operations)
    for item in items:
        item.state=finance.payout_state(item)
        item.state_label=finance.PAYOUT_STATE_LABELS[item.state]
        item.events=list(item.payout_events.all())
    return items


def _payout_context(actor, currency, personal):
    """Earnings, payouts and receipt confirmations for the finance page."""
    context={'account':finance.account_summary(actor,currency),
             'my_payouts':_with_state(finance.payouts().filter(employee=actor,currency=currency)[:200])}
    if actor.is_owner and not personal:
        rows=finance.project_accounts(currency)
        payouts=_with_state(finance.payouts().filter(currency=currency)[:200])
        # Har bir xodim bo'yicha: to'langan pulning qancha qismi hali xodim tasdig'ini kutmoqda.
        awaiting={}
        for item in payouts:
            if item.state=='pending':
                awaiting[item.employee_id]=awaiting.get(item.employee_id,Decimal('0'))+item.amount
        shown=set()
        for row in rows:
            row['awaiting']=awaiting.get(row['employee'].pk) if row['employee'].pk not in shown else None
            shown.add(row['employee'].pk)
        context.update({'payout_rows':rows,'payout_list':payouts,'is_founder_view':True,
                        'payout_due_total':sum((row['remaining'] for row in rows if row['remaining']>0),Decimal('0')),
                        'disputed_count':sum(1 for item in payouts if item.state=='disputed'),
                        'awaiting_count':sum(1 for item in payouts if item.state=='pending')})
    return context


@never_cache
@login_required
def payout_create(request):
    if not request.user.is_owner:
        raise PermissionDenied
    from .forms import PayoutForm
    initial={key:request.GET[key] for key in ('employee','project','amount','currency') if request.GET.get(key)}
    form=PayoutForm(request.POST or None,request.FILES or None,actor=request.user,initial=initial)
    if request.method=='POST' and form.is_valid():
        data=form.cleaned_data
        try:
            operation,created=finance.record_payout(request.user,employee=data['employee'],project=data['project'],amount=data['amount'],
                currency=data['currency'],paid_on=data['paid_on'],method=data['method'],description=data['description'],
                reference=data['reference'],proof=data['proof'],idempotency_key=data['idempotency_key'],
                transfer_confirmed=request.POST.get('transfer_confirmed')=='1')
            if created:
                messages.success(request,f'To‘lov qayd etildi: {finance.amount_text(operation.amount,operation.currency)}. Xodimdan tasdiq so‘raldi.')
            else:
                messages.info(request,'Bu to‘lov avval qayd etilgan. Takror yozuv yaratilmadi.')
            target=f"{reverse('enterprise:finance')}?currency={operation.currency}#tolovlar"
            return JsonResponse({'redirect':target}) if _is_modal(request) else redirect(target)
        except ValidationError as error:
            form.add_error(None,error)
    currency=form['currency'].value() or 'UZS'
    # Boshqa valyutadagi qarzni taklif qilish uchun (xodimlar ro'yxatida qarz ko'rsatilmaydi).
    debts=finance.payable_by_employee()
    employee=form['employee'].value()
    preview=None
    try:
        person=User.objects.get(pk=employee) if employee else None
    except (User.DoesNotExist,ValueError,TypeError):
        person=None
    if person:
        preview={'person':person,'balance':finance.employee_balance(person,currency),
                 'rows':[row for row in finance.project_accounts(currency,person) if row['remaining']>0],
                 'other':[(code,amount) for code,amount in sorted(debts.get(person.pk,{}).items()) if code!=currency]}
    template='boshqaruv/business/_payout_body.html' if _is_modal(request) else 'boshqaruv/business/payout_form.html'
    return render(request,template,{'form':form,'preview':preview,'currency':currency})


@login_required
@require_POST
def payout_respond(request, pk):
    from django.utils.http import url_has_allowed_host_and_scheme
    answer=request.POST.get('answer')
    back=request.POST.get('next') or request.META.get('HTTP_REFERER') or ''
    if not url_has_allowed_host_and_scheme(back,allowed_hosts={request.get_host()},require_https=request.is_secure()):
        back=''
    back=back or reverse('enterprise:overview')
    text=None
    try:
        if answer not in ('yes','no'):
            raise ValidationError('Javobni tanlang.')
        finance.respond_to_payout(request.user,pk,answer=='yes',request.POST.get('note',''))
        text='Rahmat! To‘lovni olganingiz tasdiqlandi.' if answer=='yes' else 'E’tirozingiz Asoschiga yuborildi. U tekshirib, javob beradi.'
    except ValidationError as error:
        error_text=' '.join(error.messages)
        if _is_modal(request):
            return JsonResponse({'ok':False,'message':error_text},status=400)
        messages.error(request,error_text)
        return redirect(back)
    if _is_modal(request):
        return JsonResponse({'ok':True,'message':text})
    messages.success(request,text)
    return redirect(back)


@login_required
@require_POST
def payout_remind(request, pk):
    if not request.user.is_owner:
        raise PermissionDenied
    try:
        finance.remind_payout(request.user,pk)
        messages.success(request,'Xodimga eslatma yuborildi.')
    except ValidationError as error:
        fail(request,error)
    return redirect(f"{reverse('enterprise:finance')}#tolovlar")


@login_required
@require_POST
def payout_resolve(request, pk):
    if not request.user.is_owner:
        raise PermissionDenied
    try:
        finance.resolve_payout(request.user,pk,request.POST.get('action',''),request.POST.get('note',''))
        messages.success(request,'Qaror saqlandi va xodimga xabar yuborildi.')
    except ValidationError as error:
        fail(request,error)
    return redirect(f"{reverse('enterprise:finance')}#tolovlar")


@login_required
def payout_proof(request, pk):
    operation=get_object_or_404(finance.payouts(),pk=pk)
    if not (request.user.is_owner or operation.employee_id==request.user.pk):
        raise PermissionDenied
    proof=operation.payout.proof
    if not proof:
        raise Http404
    name=f"tolov-{str(operation.pk)[:8]}{Path(proof.name).suffix.lower()}"
    return FileResponse(proof.open('rb'),as_attachment=True,filename=name)


@login_required
def search(request):
    query=request.GET.get('q','').strip()[:150]
    projects=visible_projects(request.user).filter(Q(name__icontains=query)|Q(code__icontains=query))[:20] if query else []
    tasks=[]
    employees=visible_employees(request.user).filter(Q(first_name__icontains=query)|Q(last_name__icontains=query)|Q(job_title__icontains=query))[:20] if query and request.user.has_cap('employees.view') else []
    return render(request,'boshqaruv/business/search.html',{'q':query,'projects':projects,'tasks':tasks,'employees':employees})


@login_required
def desktop(request):
    release=Path(settings.DESKTOP_RELEASE_PATH)
    return render(request,'boshqaruv/business/desktop.html',{'available':release.is_file(),'version':settings.DESKTOP_VERSION,'size':release.stat().st_size if release.is_file() else 0})


@login_required
def desktop_download(request):
    release=Path(settings.DESKTOP_RELEASE_PATH)
    if not release.is_file():raise Http404('O‘rnatuvchi hali yig‘ilmagan.')
    record(request.user,'desktop.downloaded',None,{'version':settings.DESKTOP_VERSION})
    response=FileResponse(release.open('rb'),as_attachment=True,filename=release.name)
    response['Cache-Control']='private, no-store';return response
