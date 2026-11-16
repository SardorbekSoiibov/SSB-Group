from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from apps.crm.models import Task
from apps.crm.policies import visible_projects, visible_tasks
from apps.notifications.models import Notification
from apps.notifications.reminders import refresh_deadline_reminders
from . import finance, operations
from .forms import OperationForm, ShiftForm, ReviewForm
from .models import WorkShift, PerformanceReview, DashboardLayout
from .views import visible_operations
from .insights import allowed_widgets, management_insights


@api_view(['GET'])
def session(request):
    return Response({'id':request.user.pk,'name':request.user.display_name,'role':str(request.user.role or ''),
        'permissions':sorted(request.user.caps()),'csrf':get_token(request),'dashboard':request.user.dashboard_kind})


@api_view(['GET'])
def projects(request):
    return Response([{'id':p.pk,'name':p.name,'code':p.code,'status':p.status,'deadline':p.deadline,'progress':p.progress}
                     for p in visible_projects(request.user).with_progress()[:100]])


@api_view(['GET'])
def tasks(request):
    return Response(list(visible_tasks(request.user).values('id','title','status','deadline','project_id','assignee_id')[:100]))


@api_view(['GET'])
def notifications(request):
    raw = request.query_params.get('after')
    if raw is not None and (not raw.isascii() or not raw.isdigit() or len(raw) > 19 or int(raw) > 9223372036854775807):
        return Response({'error': 'Noto‘g‘ri bildirishnoma kursori.'}, status=400)
    refresh_deadline_reminders()
    from .weekly_rating import announce_due
    announce_due()
    # Server dushanba 00:00 da o‘chiq bo‘lgan bo‘lsa ham, birinchi ochilgan sahifa o‘tgan haftani yopib e’lon qiladi.
    from .performance_system import ensure_closed_async
    ensure_closed_async()
    # Dev serverda ham Telegram bot javob bersin: ochiq sahifa bo'lsa, fon oqimlari ishga tushadi (allaqachon ishlasa — hech narsa qilmaydi).
    from apps.notifications.runtime import start_worker
    start_worker()
    # Every open workspace page polls here, so presence reflects the whole system, not only the chat.
    from apps.chat.views import touch_presence
    touch_presence(request.user)
    own = Notification.objects.filter(recipient=request.user)
    unread = own.filter(read_at__isnull=True)
    if raw is None:
        cursor = own.order_by('-pk').values_list('pk', flat=True).first() or 0
        items = list(unread.filter(pk__lte=cursor).order_by('-pk')[:20])
        more = False
    else:
        cursor = int(raw)
        batch = list(own.filter(pk__gt=cursor).order_by('pk')[:101])
        more = len(batch) > 100
        scanned = batch[:100]
        cursor = scanned[-1].pk if scanned else cursor
        items = [item for item in scanned if item.read_at is None]
    from apps.chat.models import Message
    from .ui import section_unread
    response = Response({'user': request.user.pk, 'unread': unread.count(),
        'sections': section_unread(request.user),
        'chat_unread': Message.objects.filter(recipient=request.user, read_at__isnull=True).count(),
        'cursor': cursor, 'has_more': more,
        'items': [{'id': item.pk, 'title': item.title, 'body': item.body, 'url': item.safe_url,
                   'kind': item.kind, 'created_at': item.created_at, 'priority': item.priority} for item in items]})
    response['Cache-Control'] = 'no-store, private'
    return response


@api_view(['POST'])
def notification_read(request, pk):
    changed=Notification.objects.filter(pk=pk,recipient=request.user,read_at__isnull=True).update(read_at=timezone.now())
    return Response({'read':bool(changed)})


@api_view(['GET','POST'])
def ledger(request):
    if request.method=='POST':
        finance.require(request.user,'finance.manage')
        form=OperationForm(request.data,actor=request.user)
        if not form.is_valid():return Response({'errors':form.errors},status=400)
        data=form.cleaned_data
        try:
            item=finance.request_operation(request.user,kind=data['kind'],amount=data['amount'],currency=data['currency'],description=data['description'],
                idempotency_key=data['idempotency_key'],employee=data['employee'],project=data['project'],payload=form.payload())
            return Response({'id':str(item.pk),'status':item.status},status=201)
        except ValidationError as error:return Response({'errors':error.messages},status=400)
    return Response([{'id':str(e.pk),'type':e.category,'amount':str(e.amount),'currency':e.currency,'employee':e.employee_id,
        'project':e.project_id,'source':str(e.operation_id),'corrects':str(e.corrects_id) if e.corrects_id else None,'description':e.description,'date':e.created_at}
        for e in finance.visible_entries(request.user)[:100]])


@api_view(['POST'])
def decision(request, pk):
    if not isinstance(request.data.get('approved'),bool):return Response({'error':'approved must be boolean'},status=400)
    try:
        item=finance.decide(request.user,pk,request.data['approved'],str(request.data.get('reason','')))
        return Response({'id':str(item.pk),'status':item.status})
    except ValidationError as error:return Response({'errors':error.messages},status=400)
    except finance.FinanceOperation.DoesNotExist:return Response({'error':'Not found'},status=404)


@api_view(['GET','POST'])
def schedule(request):
    if request.method=='POST':
        finance.require(request.user,'schedule.manage')
        form=ShiftForm(request.data,actor=request.user)
        if not form.is_valid():return Response({'errors':form.errors},status=400)
        try:
            shift=operations.save_shift(request.user,**form.cleaned_data)
            return Response({'id':shift.pk},status=201)
        except ValidationError as error:return Response({'errors':error.messages},status=400)
    qs=WorkShift.objects.filter(employee__in=operations.visible_employees(request.user)) if request.user.has_cap('schedule.manage') else WorkShift.objects.filter(employee=request.user)
    return Response(list(qs.filter(ends_at__gte=timezone.now()).values('id','employee_id','starts_at','ends_at','location','cancelled')[:100]))


@api_view(['GET'])
def insights(request):
    return Response({'items':management_insights(request.user)})
