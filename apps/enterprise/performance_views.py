"""Baholash va reyting — bitta sahifa.

Hafta: dushanba 00:00 — yakshanba 23:59 (Asia/Tashkent). Asoschidan boshqa barcha faol xodimlar baholanadi.
Hafta davomida rahbar har bir xodimga baho va izoh qo‘yadi; dushanba 00:00 da hafta avtomatik yopiladi,
SSB AI (Claude) har bir xodimni vazifalari bo‘yicha tahlil qiladi va “Haftaning eng faol xodimi” e’lon qilinadi.
"""
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.conf import settings
from django.http import HttpResponseNotAllowed, JsonResponse
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.models import User
from apps.accounts.policies import visible_employees
from apps.core.forms import StyledFormMixin
from . import performance_system as system
from .models import EvaluationWeek, ManagerWeeklyScore, PerformanceReview, WeeklyEvaluation, WeeklyReward


class RewardForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = WeeklyReward
        fields = ['place', 'kind', 'description', 'value', 'currency', 'status']
        labels = {'place': 'O‘rin (1–3)', 'kind': 'Mukofot turi', 'description': 'Tavsif', 'value': 'Qiymat', 'currency': 'Valyuta', 'status': 'Holat'}


def _published_week(request):
    weeks = EvaluationWeek.objects.filter(published_at__isnull=False)
    try:
        day = parse_date(request.GET.get('week', '') or '')
    except ValueError:
        day = None
    return (weeks.filter(starts_on=day).first() if day else None) or weeks.first()


def _ranking(week):
    rows = [dict(r) for r in week.ranking] if week else []
    people = User.objects.select_related('role').in_bulk([r['employee_id'] for r in rows])
    for row in rows:
        row['person'] = people.get(row['employee_id'])
    return rows


@never_cache
@login_required
def performance(request):
    user = request.user
    manager = user.is_active and user.has_cap('performance.manage')
    system.ensure_closed_async()
    if request.method == 'POST':
        ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        error = None
        try:
            item = system.save_manager_score(user, int(request.POST.get('employee', 0) or 0), request.POST.get('score', ''), request.POST.get('comment', ''))
        except ValidationError as exc:
            error = ' '.join(exc.messages)
        except (ValueError, TypeError):
            error = 'Xodim tanlanmadi.'
        if ajax:
            if error:
                return JsonResponse({'ok': False, 'error': error}, status=400)
            return JsonResponse({'ok': True, 'by': f"{item.author.display_name} · {timezone.localtime(item.updated_at):%d.%m %H:%M}",
                                 'scored': ManagerWeeklyScore.objects.filter(week_start=item.week_start, employee__in=system.scorable(user)).count()})
        if error:
            messages.error(request, error)
        else:
            messages.success(request, 'Rahbar bahosi saqlandi. Hafta yopilguncha uni o‘zgartirish mumkin.')
        return redirect(reverse('enterprise:performance') + f"#xodim-{request.POST.get('employee', '')}")

    start = system.week_start()
    close_at = system.close_moment(start)
    week = _published_week(request)
    ranking = _ranking(week)
    winner = ranking[0] if ranking and ranking[0].get('completed', len(ranking[0].get('achievements', []))) else None
    personal = next((r for r in ranking if r['employee_id'] == user.pk), None)

    board = []
    if manager:
        scorable = set(system.scorable(user).values_list('pk', flat=True))
        people = list(system.rated_people().filter(pk__in=visible_employees(user).values('pk')))
        board = system.live_rows(people, start)
        for row in board:
            row['can_score'] = row['person'].pk in scorable
    mine = None
    if system.rated_people().filter(pk=user.pk).exists():
        mine = system.live_rows([user], start)[0]

    rewards = []
    company_manager = manager and user.company_scope
    if week:
        rewards = list(week.rewards.select_related('employee', 'operation'))
        if not manager:
            rewards = [r for r in rewards if r.status != 'draft']
        if company_manager:
            for item in rewards:
                item.edit_form = RewardForm(instance=item, auto_id=f'reward_{item.pk}_%s')

    return render(request, 'boshqaruv/business/performance_board.html', {
        'manager': manager, 'company_manager': company_manager,
        'start': start, 'end': start + timedelta(days=6), 'close_at': close_at,
        'close_at_iso': close_at.isoformat(), 'week': week,
        'week_end': week.starts_on + timedelta(days=6) if week else None,
        'weeks': EvaluationWeek.objects.filter(published_at__isnull=False)[:52],
        'ranking': ranking, 'winner': winner, 'personal': personal,
        'podium': [r for place in (2, 1, 3) for r in ranking if r['place'] == place],
        'board': board, 'mine': mine, 'scored_count': sum(1 for r in board if r['manager']),
        'scorable_count': sum(1 for r in board if r.get('can_score')),
        'weights': system.DEFAULT_WEIGHTS, 'criteria_labels': system.CRITERIA,
        'ai_configured': bool(settings.ANTHROPIC_API_KEY), 'ai_model': settings.PERFORMANCE_AI_MODEL,
        'rewards': rewards, 'reward_form': RewardForm(initial={'place': 1, 'value': 0}) if company_manager and week else None,
    })


@never_cache
@login_required
@require_GET
def detail(request, pk):
    user = request.user
    viewer = user.has_cap('performance.manage') or user.has_cap('performance.view')
    qs = WeeklyEvaluation.objects.select_related('employee__role', 'week', 'reviewed_by').filter(week__published_at__isnull=False)
    qs = qs.filter(employee__in=visible_employees(user)) if viewer else qs.filter(employee=user)
    item = get_object_or_404(qs, pk=pk)
    weights = item.week.weights
    manager_scored = item.evidence.get('manager_scored', bool(item.reviewed_by_id))
    rule = item.evidence.get('rule_criteria', {})
    criteria = [{'key': k, 'label': label, 'rule': rule.get(k), 'final': item.final_criteria.get(k), 'weight': weights.get(k),
                 'skipped': k == 'manager' and not manager_scored} for k, label in system.CRITERIA.items()]
    row = next((r for r in item.week.ranking if r['employee_id'] == item.employee_id), {})
    return render(request, 'boshqaruv/business/evaluation_detail.html', {
        'item': item, 'criteria': criteria, 'place': row.get('place'), 'total': len(item.week.ranking),
        'manager_scored': manager_scored, 'week_end': item.week.starts_on + timedelta(days=6),
        'tasks': [t for t in item.evidence.get('tasks', []) if t.get('completed_in_week')],
    })


@never_cache
@login_required
def rating(request):
    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])
    query = request.GET.get('week') or request.GET.get('hafta')
    return redirect(reverse('enterprise:performance') + (f'?week={query}' if query else '') + '#reyting')


@never_cache
@login_required
@require_GET
def legacy(request):
    items = PerformanceReview.objects.select_related('employee').order_by('-period_end')
    if request.user.has_cap('performance.manage') or request.user.has_cap('performance.view'):
        items = items.filter(employee__in=visible_employees(request.user))
    else:
        items = items.filter(employee=request.user, reviewapproval__isnull=False)
    return render(request, 'boshqaruv/business/performance.html', {'reviews': items[:100], 'manager': False, 'ranking': []})


@login_required
@require_POST
def publish(request, pk):
    messages.info(request, 'Reyting har dushanba soat 00:00 da avtomatik e’lon qilinadi.')
    return redirect('enterprise:performance')


@login_required
@require_POST
def reward(request, pk):
    system.require_manager(request.user, company=True)
    week = get_object_or_404(EvaluationWeek, pk=pk)
    form = RewardForm(request.POST)
    if form.is_valid():
        try:
            system.save_reward(request.user, week.pk, **form.cleaned_data)
            messages.success(request, 'Mukofot saqlandi. Pul mukofoti mavjud moliya tasdiqlash tartibidan o‘tadi.')
        except ValidationError as error:
            messages.error(request, ' '.join(error.messages))
    else:
        messages.error(request, 'Mukofot ma’lumotlarini to‘liq kiriting.')
    return redirect(reverse('enterprise:performance') + f'?week={week.starts_on}#mukofotlar')
