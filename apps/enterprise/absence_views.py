from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from . import absence
from .absence_models import AbsenceRequest


def _date(value):
    try:
        return parse_date(value or "")
    except ValueError:
        return None


def _back(request):
    target = request.POST.get("next", "")
    return redirect(target if target.startswith("/management/enterprise/schedule/") else "enterprise:schedule")


@login_required
@require_POST
def absence_create(request):
    try:
        absence.submit(request.user, _date(request.POST.get("date_from")),
                       _date(request.POST.get("date_to")) or _date(request.POST.get("date_from")), request.POST.get("reason"))
        messages.success(request, "So‘rovingiz asoschiga yuborildi. Javob kelganda bildirishnoma olasiz.")
    except ValidationError as error:
        messages.error(request, error.messages[0])
    return _back(request)


@login_required
@require_POST
def absence_decide(request, pk):
    action = request.POST.get("action")
    if action not in {"approve", "reject"}:
        raise Http404
    try:
        absence.decide(request.user, pk, action == "approve", request.POST.get("note"))
        messages.success(request, "Qaror xodimga yuborildi.")
    except AbsenceRequest.DoesNotExist:
        raise Http404
    except ValidationError as error:
        messages.error(request, error.messages[0])
    return _back(request)
