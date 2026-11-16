"""Transactional financial engine. No materialized, editable employee balances."""
import hashlib
import json
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_DOWN
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.db.models import Sum, Q
from django.utils import timezone
from apps.accounts.models import User
from apps.accounts.policies import visible_employees
from apps.audit.services import record
from apps.crm.models import Project
from apps.crm.policies import visible_projects
from apps.notifications.services import notify
from .models import ApprovalDecision, ApprovalRule, AgreementSnapshot, FinanceOperation, LedgerEntry, OperationKind, CURRENCIES

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
C = LedgerEntry.Category
EARNINGS = [C.EARNING, C.SALARY, C.BONUS]


def money(value):
    try:
        value = Decimal(str(value))
        if not value.is_finite() or value <= 0 or value > Decimal("999999999999999999.99") or value != value.quantize(CENT):
            raise ValueError()
        return value.quantize(CENT)
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError("Musbat summa va ko‘pi bilan 2 kasr xonasi kiriting.")


def require(user, capability):
    if not user.has_cap(capability):
        raise PermissionDenied


def visible_entries(user):
    if user.has_cap("finance.view"):
        if user.company_scope:
            return LedgerEntry.objects.all()
        return LedgerEntry.objects.filter(Q(employee__in=visible_employees(user)) | Q(project__in=visible_projects(user)))
    return LedgerEntry.objects.filter(employee=user)


def employee_balance(employee, currency, project=None):
    qs = LedgerEntry.objects.filter(employee=employee, currency=currency)
    if project is not None:
        qs = qs.filter(project=project)
    earned = qs.filter(category__in=EARNINGS).aggregate(n=Sum("amount"))["n"] or ZERO
    paid = qs.filter(category=C.PAID).aggregate(n=Sum("amount"))["n"] or ZERO
    return {"earned": earned, "paid": paid, "payable": earned - paid, "currency": currency}


def company_summary(entries, currency):
    qs = entries.filter(currency=currency)
    amounts = {row["category"]: row["total"] for row in qs.values("category").annotate(total=Sum("amount"))}
    receipt = amounts.get(C.RECEIPT, ZERO)
    earning = amounts.get(C.EARNING, ZERO)
    costs = sum((amounts.get(k, ZERO) for k in [C.SALARY, C.BONUS, C.EXPENSE]), ZERO)
    return {"currency": currency, "client_receipts": receipt, "company_revenue": receipt - earning,
            "expenses": costs, "net_profit": receipt - earning - costs,
            "cash": receipt - amounts.get(C.PAID, ZERO) - amounts.get(C.EXPENSE, ZERO),
            "employee_payable": earning + amounts.get(C.SALARY, ZERO) + amounts.get(C.BONUS, ZERO) - amounts.get(C.PAID, ZERO)}


def profitability(project):
    agreement = AgreementSnapshot.objects.filter(project=project).first()
    if not agreement:
        return None
    totals = company_summary(LedgerEntry.objects.filter(project=project), agreement.currency)
    totals.update(project=project, agreement=agreement, contract=agreement.amount,
                  outstanding_client=max(ZERO, agreement.amount - totals["client_receipts"]))
    return totals


def _lock():
    # A transaction-level lock serializes posting and approvals across all workers.
    # This intentionally prioritizes correctness over ledger write throughput.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(73910233)")


def _validate_shares(shares, company):
    try:
        company = Decimal(str(company))
        if not company.is_finite() or not ZERO <= company <= 100 or company != company.quantize(Decimal('.0001')):
            raise ValueError()
        normalized, ids = [], set()
        for share in shares:
            employee_id = int(share["employee"])
            percent = Decimal(str(share["percent"]))
            if employee_id in ids or not percent.is_finite() or percent <= 0 or percent != percent.quantize(Decimal('.0001')):
                raise ValueError()
            ids.add(employee_id)
            normalized.append({"employee": employee_id, "percent": str(percent)})
        if sum((Decimal(row["percent"]) for row in normalized), company) != 100:
            raise ValueError()
        return normalized, company
    except (InvalidOperation, KeyError, TypeError, ValueError):
        raise ValidationError("Xodim ulushlari va kompaniya ulushi jami 100% bo‘lishi kerak. Xodim takrorlanmasin.")


@transaction.atomic
def request_operation(actor, *, kind, amount, currency, description, idempotency_key, employee=None, project=None, payload=None):
    require(actor, "finance.manage")
    _lock()
    if kind not in dict(OperationKind.manual()) or currency not in dict(CURRENCIES):
        raise ValidationError("Tranzaksiya turi yoki valyuta noto‘g‘ri.")
    amount = money(amount)
    if not description or len(description.strip()) < 5:
        raise ValidationError("Amal sababi va manbasini yozing (kamida 5 belgi).")
    if not actor.company_scope:
        if project and not visible_projects(actor).filter(pk=project.pk).exists():
            raise PermissionDenied
        if employee and not visible_employees(actor).filter(pk=employee.pk).exists():
            raise PermissionDenied
        if not project and not employee:
            raise PermissionDenied
    try:
        key = uuid.UUID(str(idempotency_key))
    except (ValueError, TypeError):
        raise ValidationError("So‘rovning takrorlanmas kaliti kerak.")
    payload = dict(payload or {})
    # Fingerprint the submitted intent, not current mutable project settings.
    intent = {"kind": kind, "amount": str(amount), "currency": currency, "description": description,
              "employee": employee.pk if employee else None, "project": project.pk if project else None, "payload": payload}
    fingerprint = hashlib.sha256(json.dumps(intent, sort_keys=True, default=str).encode()).hexdigest()
    existing = FinanceOperation.objects.filter(idempotency_key=key).first()
    if existing:
        if existing.administrator_id != actor.pk or existing.fingerprint != fingerprint:
            raise ValidationError("Bu kalit boshqa so‘rovda ishlatilgan. Qayta yuborish bloklandi.")
        return existing
    if kind == OperationKind.AGREEMENT:
        require(actor, "finance.distribute")
        if not project:
            raise ValidationError("Kelishuv uchun loyiha tanlang.")
        old_agreement = AgreementSnapshot.objects.filter(project=project).first()
        if old_agreement and old_agreement.currency != currency:
            raise ValidationError("Loyiha valyutasini oldingi kelishuvdan keyin o‘zgartirib bo‘lmaydi.")
        from apps.core.models import WorkspaceSettings
        shares, company = _validate_shares(payload.get("shares", []), payload.get("company_percent", str(WorkspaceSettings.load().company_share_percent)))
        allowed = set(project.members.values_list("pk", flat=True)) | {project.manager_id}
        if any(s["employee"] not in allowed or not User.objects.filter(pk=s["employee"], is_active=True).exists() for s in shares):
            raise ValidationError("Ulush faqat loyiha jamoasidagi faol xodimga beriladi.")
        payload = {"shares": shares, "company_percent": str(company)}
    elif kind == OperationKind.RECEIPT:
        agreement = AgreementSnapshot.objects.filter(project=project, currency=currency).first() if project else None
        if not agreement:
            raise ValidationError("Avval loyiha moliyaviy kelishuvini tasdiqlang.")
        payload = {"agreement_id": agreement.pk}
    elif kind in [OperationKind.PAYMENT, OperationKind.SALARY, OperationKind.BONUS]:
        if not employee or (kind!=OperationKind.PAYMENT and not employee.is_active):
            raise ValidationError("Faol xodimni tanlang.")
        payload = {}
    elif kind == OperationKind.CORRECTION:
        try:
            original = LedgerEntry.objects.get(pk=payload.get("entry_id"), corrects__isnull=True)
        except (LedgerEntry.DoesNotExist, ValueError, ValidationError):
            raise ValidationError("Tuzatiladigan asl tranzaksiya topilmadi.")
        if currency != original.currency:
            raise ValidationError("Tuzatish valyutasi asl yozuv bilan bir xil bo‘lsin.")
        employee, project = original.employee, original.project
        if not visible_entries(actor).filter(pk=original.pk).exists():
            raise PermissionDenied
        payload = {"entry_id": str(original.pk)}
    else:
        payload = {}
    rule = ApprovalRule.objects.filter(kind=kind, currency=currency).first()
    required = (rule.approvals if amount >= rule.threshold else 0) if rule else (0 if kind == OperationKind.RECEIPT else 1)
    if kind in [OperationKind.CORRECTION, OperationKind.AGREEMENT]:
        required = max(1, required)
    # Moliyaviy qarorni faqat Asoschi qabul qiladi: uning o'z so'rovi darhol kuchga kiradi,
    # boshqalarning so'rovi Asoschi tasdig'ini kutadi.
    if actor.is_owner:
        required = 0
    elif required:
        required = 1
    operation = FinanceOperation.objects.create(idempotency_key=key, fingerprint=fingerprint, kind=kind, amount=amount,
        currency=currency, description=description.strip(), employee=employee, project=project, administrator=actor,
        payload=payload, approvals_required=required, approval_capability=rule.capability if rule else "finance.approve")
    record(actor, "finance.requested", operation, {"amount": str(amount), "currency": currency, "kind": kind})
    if required == 0:
        _post(operation, actor)
    else:
        recipients = [u for u in founders() if u.pk != actor.pk]
        notify(recipients, "approval", "Moliyaviy tasdiq so‘rovi", str(operation), "/management/enterprise/finance/", f"finance:{operation.pk}")
    return operation


@transaction.atomic
def decide(actor, operation_id, approved, reason):
    _lock()
    operation = FinanceOperation.objects.select_for_update().get(pk=operation_id)
    if not actor.is_owner:  # moliyaviy qarorni faqat Asoschi qabul qiladi
        raise PermissionDenied("Moliyaviy operatsiyani faqat Asoschi tasdiqlaydi.")
    if operation.status != FinanceOperation.Status.PENDING:
        raise ValidationError("Bu so‘rov allaqachon yakunlangan.")
    if len(reason.strip()) < 5:
        raise ValidationError("Qaror sababini yozing.")
    if operation.decisions.filter(administrator=actor).exists():
        raise ValidationError("Siz bu so‘rov bo‘yicha ovoz bergansiz.")
    ApprovalDecision.objects.create(operation=operation, administrator=actor, approved=approved, reason=reason)
    record(actor, "finance.decision", operation, {"approved": approved, "reason": reason})
    if not approved:
        operation.status = FinanceOperation.Status.REJECTED
        operation.finalized_at = timezone.now()
        operation.save(update_fields=["status", "finalized_at"])
    elif operation.decisions.filter(approved=True).count() >= operation.approvals_required:
        _post(operation, actor)
    return operation


def _line(operation, actor, category, amount, employee=None, agreement=None, corrects=None):
    return LedgerEntry.objects.create(line_key=f"{operation.pk}:{category}:{employee.pk if employee else 'company'}",
        operation=operation, category=category, amount=amount, currency=operation.currency, employee=employee,
        project=operation.project, agreement=agreement, corrects=corrects, administrator=actor, description=operation.description)


def _post(operation, actor):
    if operation.kind == OperationKind.AGREEMENT:
        latest = AgreementSnapshot.objects.filter(project=operation.project).first()
        if latest and latest.currency != operation.currency:
            raise ValidationError("Loyiha valyutasi oldingi tasdiq bilan mos emas.")
        shares, company = _validate_shares(operation.payload["shares"], operation.payload["company_percent"])
        AgreementSnapshot.objects.create(project=operation.project, operation=operation, amount=operation.amount,
            currency=operation.currency, company_percent=company, shares=shares, version=(latest.version + 1 if latest else 1), confirmed_by=actor)
    elif operation.kind == OperationKind.RECEIPT:
        agreement = AgreementSnapshot.objects.get(pk=operation.payload["agreement_id"], project=operation.project)
        _line(operation, actor, C.RECEIPT, operation.amount, agreement=agreement)
        # After completion the agreed shares are already earned; a later receipt only tops up what is still missing.
        caps = None
        if FinanceOperation.objects.filter(project=operation.project, kind=OperationKind.COMPLETION, status=FinanceOperation.Status.APPROVED).exists():
            caps = {employee_id: max(ZERO, target - _earned_on_project(employee_id, operation.project, agreement.currency))
                    for employee_id, _percent, target in share_targets(agreement)}
        employee_pool = (operation.amount * (100 - agreement.company_percent) / 100).quantize(CENT, rounding=ROUND_HALF_UP)
        allocated = ZERO
        for i, share in enumerate(agreement.shares):
            amount = (operation.amount * Decimal(share["percent"]) / 100).quantize(CENT, rounding=ROUND_DOWN)
            if i == len(agreement.shares) - 1:
                amount = employee_pool - allocated
            allocated += amount
            if caps is not None:
                amount = min(amount, caps.get(int(share["employee"]), ZERO))
            if amount > 0:
                _line(operation, actor, C.EARNING, amount, User.objects.get(pk=share["employee"]), agreement)
    elif operation.kind == OperationKind.PAYMENT:
        available = employee_balance(operation.employee, operation.currency, operation.project)["payable"]
        available = min(available, employee_balance(operation.employee, operation.currency)["payable"])
        cash = company_summary(LedgerEntry.objects.all(), operation.currency)["cash"]
        if operation.amount > available or operation.amount > cash:
            raise ValidationError("To‘lov qarzdorlikdan yoki qayd qilingan pul qoldig‘idan oshadi.")
        _line(operation, actor, C.PAID, operation.amount, operation.employee)
    elif operation.kind == OperationKind.CORRECTION:
        original = LedgerEntry.objects.get(pk=operation.payload["entry_id"])
        reversed_amount = -(original.corrections.aggregate(n=Sum("amount"))["n"] or ZERO)
        if operation.amount > original.amount - reversed_amount:
            raise ValidationError("Tuzatish asl summadan oshadi.")
        if original.category in EARNINGS and operation.amount > min(employee_balance(original.employee, original.currency, original.project)["payable"],employee_balance(original.employee, original.currency)["payable"]):
            raise ValidationError("To‘langan daromadni kamaytirib bo‘lmaydi. Avval haqiqiy qaytarishni qayd qiling.")
        _line(operation, actor, original.category, -operation.amount, original.employee, original.agreement, original)
        if original.category == C.RECEIPT:
            children = list(original.operation.entries.filter(category=C.EARNING, corrects__isnull=True).order_by("employee_id"))
            for child in children:
                already = -(child.corrections.aggregate(n=Sum("amount"))["n"] or ZERO)
                target_total = (child.amount * (operation.amount + reversed_amount) / original.amount).quantize(CENT, rounding=ROUND_HALF_UP)
                value = max(ZERO, target_total - already)
                if value > min(employee_balance(child.employee, child.currency, child.project)["payable"],employee_balance(child.employee, child.currency)["payable"]):
                    raise ValidationError("Ulushlar to‘langan. Qaytarishni avval qayd qiling; xodim daromadi manfiy bo‘lmaydi.")
                if value:
                    _line(operation, actor, C.EARNING, -value, child.employee, child.agreement, child)
    else:
        category = {OperationKind.BONUS: C.BONUS, OperationKind.SALARY: C.SALARY, OperationKind.EXPENSE: C.EXPENSE}[operation.kind]
        _line(operation, actor, category, operation.amount, operation.employee if category != C.EXPENSE else None)
    operation.status = FinanceOperation.Status.APPROVED
    operation.finalized_at = timezone.now()
    operation.save(update_fields=["status", "finalized_at"])
    record(actor, "finance.posted", operation, {"entries": [str(pk) for pk in operation.entries.values_list("pk", flat=True)]})
    if operation.employee:
        notify([operation.employee], "announcement", "Moliyaviy hisob yangilandi", str(operation), "/management/enterprise/balance/", f"posted:{operation.pk}")


# ------------------------------------------------------------------ project completion earnings

COMPLETION_NAMESPACE = uuid.UUID("5b7f8c2e-31a4-4d0e-9a51-c0d7e3b1f6a2")
BALANCE_URL = "/management/enterprise/balance/"
PAYOUTS_URL = "/management/enterprise/finance/#tolovlar"
# Javob kutilayotgan to'lov: har bir sahifada tasdiqlash oynasi chiqadi, shuning uchun hammaga ochiq bosh sahifaga olib boradi.
ASK_URL = "/management/enterprise/"


def amount_text(amount, currency):
    amount = Decimal(amount)
    text = f"{amount:,.0f}" if amount == amount.to_integral_value() else f"{amount:,.2f}"
    return text.replace(",", " ") + (" so‘m" if currency == "UZS" else f" {currency}")


def percent_text(value):
    return format(Decimal(value).normalize(), "f")


def founders():
    return [user for user in User.objects.filter(is_active=True).select_related("role") if user.is_owner]


def share_targets(agreement):
    """[(employee_id, percent, amount)] of the agreed price, split to the cent exactly like client receipts."""
    pool = (agreement.amount * (100 - agreement.company_percent) / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    rows, allocated = [], ZERO
    for i, share in enumerate(agreement.shares):
        amount = (agreement.amount * Decimal(share["percent"]) / 100).quantize(CENT, rounding=ROUND_DOWN)
        if i == len(agreement.shares) - 1:
            amount = pool - allocated
        allocated += amount
        rows.append((int(share["employee"]), Decimal(share["percent"]), amount))
    return rows


def _earned_on_project(employee_id, project, currency):
    return (LedgerEntry.objects.filter(employee_id=employee_id, project=project, currency=currency, category=C.EARNING)
            .aggregate(n=Sum("amount"))["n"] or ZERO)


@transaction.atomic
def accrue_project_completion(actor, project):
    """Books every member's confirmed share as earned (payable) once the project completion is approved.

    It is an earning, not a payout. Keyed by project + agreement version, so processing the same completion
    again never creates a second earning, and shares already earned through client receipts are not repeated.
    """
    _lock()
    agreement = AgreementSnapshot.objects.filter(project=project).first()
    if not agreement or not agreement.shares:
        notify(founders(), "approval", f"Ulush hisoblanmadi: {project.name}",
               "Loyiha yakunlandi, ammo tasdiqlangan moliyaviy kelishuv yo‘q. Kelishuvni tasdiqlang.",
               "/management/enterprise/finance/", f"completion-missing:{project.pk}")
        return None
    key = uuid.uuid5(COMPLETION_NAMESPACE, f"{project.pk}:{agreement.pk}")
    existing = FinanceOperation.objects.filter(idempotency_key=key).first()
    if existing:
        return existing
    lines = []
    for employee_id, percent, target in share_targets(agreement):
        due = target - _earned_on_project(employee_id, project, agreement.currency)
        if due > 0:
            lines.append((User.objects.get(pk=employee_id), percent, target, due))
    if not lines:
        return None
    payload = {"agreement_id": agreement.pk, "agreement_version": agreement.version,
               "shares": [{"employee": u.pk, "percent": str(p), "target": str(t), "amount": str(d)} for u, p, t, d in lines]}
    operation = FinanceOperation.objects.create(
        idempotency_key=key, fingerprint=hashlib.sha256(f"completion:{key}".encode()).hexdigest(),
        kind=OperationKind.COMPLETION, amount=sum((d for *_, d in lines), ZERO), currency=agreement.currency,
        description=f"«{project.name}» loyihasi yakunlandi va tasdiqlandi: kelishuv bo‘yicha xodim ulushlari hisoblandi.",
        project=project, administrator=actor, payload=payload, approvals_required=0,
        status=FinanceOperation.Status.APPROVED, finalized_at=timezone.now())
    for user, percent, target, due in lines:
        _line(operation, actor, C.EARNING, due, user, agreement)
        notify([user], "announcement", f"Sizga {amount_text(due, agreement.currency)} hisoblandi",
               f"«{project.name}» loyihasi yakunlandi. Ulushingiz {percent_text(percent)}%. Holati: to‘lanishi kerak.",
               BALANCE_URL, f"earning:{operation.pk}:{user.pk}")
    record(actor, "finance.accrued", operation, {"project": project.name, "currency": agreement.currency,
                                                 "shares": payload["shares"]})
    return operation


# ------------------------------------------------------------------ payouts and receipt confirmation

PAYOUT_STATE_LABELS = {
    "pending": "Xodim tasdig‘i kutilmoqda",
    "confirmed": "Xodim tasdiqladi",
    "disputed": "Tasdiqlanmagan / E’tiroz bildirilgan",
    "reversed": "Tuzatish bilan bekor qilingan",
    "legacy": "Qayd etilgan",
}


def payout_state(operation):
    """Derived from the append-only event history; nothing is ever overwritten."""
    if not hasattr(operation, "payout"):
        return "legacy"
    cached = getattr(operation, "_prefetched_objects_cache", {}).get("payout_events")
    events = list(cached) if cached is not None else list(operation.payout_events.all())
    latest = events[-1] if events else None
    if latest is None or latest.kind == latest.Kind.REASKED:
        return "pending"
    return latest.kind


def payouts():
    return (FinanceOperation.objects.filter(kind=OperationKind.PAYMENT, status=FinanceOperation.Status.APPROVED, payout__isnull=False)
            .select_related("employee", "project", "administrator", "payout").prefetch_related("payout_events__actor"))


def _require_founder(actor):
    if not actor.is_owner:
        raise PermissionDenied("Bu amalni faqat Asoschi bajaradi.")


@transaction.atomic
def record_payout(actor, *, employee, amount, currency, paid_on, method, description, idempotency_key,
                  project=None, reference="", proof=None, transfer_confirmed=False):
    """The only place a real payout is created: after the Founder states the money was actually handed over."""
    from .models import PayoutDetail, PayoutMethod
    _require_founder(actor)
    if not transfer_confirmed:
        raise ValidationError("Pul xodimga haqiqatan o‘tkazilgani yoki topshirilganini tasdiqlang.")
    _lock()
    amount = money(amount)
    if currency not in dict(CURRENCIES) or method not in PayoutMethod.values:
        raise ValidationError("Valyuta yoki to‘lov usuli noto‘g‘ri.")
    if not description or len(description.strip()) < 5:
        raise ValidationError("To‘lov izohini yozing (kamida 5 belgi).")
    if paid_on > timezone.localdate():
        raise ValidationError("Kelajakdagi sana bilan to‘lov qayd etilmaydi.")
    try:
        key = uuid.UUID(str(idempotency_key))
    except (ValueError, TypeError):
        raise ValidationError("So‘rovning takrorlanmas kaliti kerak.")
    intent = {"kind": "payout", "employee": employee.pk, "project": project.pk if project else None, "amount": str(amount),
              "currency": currency, "paid_on": str(paid_on), "method": method}
    fingerprint = hashlib.sha256(json.dumps(intent, sort_keys=True).encode()).hexdigest()
    existing = FinanceOperation.objects.filter(idempotency_key=key).first()
    if existing:
        if existing.fingerprint == fingerprint and existing.administrator_id == actor.pk:
            return existing, False  # the same form sent twice: one payout only
        raise ValidationError("Bu to‘lov shakli allaqachon ishlatilgan. Sahifani yangilab, qaytadan kiriting.")
    payable = employee_balance(employee, currency)["payable"]
    if project is not None:
        payable = min(payable, employee_balance(employee, currency, project)["payable"])
    if amount > payable:
        raise ValidationError(f"To‘lov qarzdorlikdan oshadi. To‘lanishi kerak: {amount_text(max(payable, ZERO), currency)}.")
    operation = FinanceOperation.objects.create(
        idempotency_key=key, fingerprint=fingerprint, kind=OperationKind.PAYMENT, amount=amount, currency=currency,
        description=description.strip(), employee=employee, project=project, administrator=actor,
        payload={"paid_on": str(paid_on), "method": method, "reference": reference.strip()[:120]},
        approvals_required=0, status=FinanceOperation.Status.APPROVED, finalized_at=timezone.now())
    _line(operation, actor, C.PAID, amount, employee)
    PayoutDetail.objects.create(operation=operation, paid_on=paid_on, method=method, reference=reference.strip()[:120], proof=proof or "")
    record(actor, "finance.payout", operation, {"employee": str(employee), "project": str(project) if project else "",
                                               "amount": str(amount), "currency": currency, "paid_on": str(paid_on), "method": method})
    notify([employee], "approval", f"Sizga {amount_text(amount, currency)} to‘lov berildimi?",
           f"{paid_on:%d.%m.%Y} · {PayoutMethod(method).label}" + (f" · {project.name}" if project else "") + ". Iltimos, javob bering.",
           ASK_URL, f"payout:{operation.pk}")
    return operation, True


def _payout_for_update(operation_id):
    try:
        return FinanceOperation.objects.select_for_update(of=("self",)).select_related("employee", "project").get(
            pk=operation_id, kind=OperationKind.PAYMENT, status=FinanceOperation.Status.APPROVED, payout__isnull=False)
    except (FinanceOperation.DoesNotExist, ValidationError, ValueError):
        raise ValidationError("To‘lov topilmadi.")


@transaction.atomic
def respond_to_payout(employee, operation_id, received, note=""):
    """The employee only acknowledges or disputes. Money records are never created or changed here."""
    from .models import PayoutEvent
    _lock()
    operation = _payout_for_update(operation_id)
    if operation.employee_id != employee.pk:
        raise PermissionDenied("Bu to‘lov sizga tegishli emas.")
    if payout_state(operation) != "pending":
        raise ValidationError("Bu to‘lov bo‘yicha javob allaqachon berilgan.")
    note = (note or "").strip()[:500]
    kind = PayoutEvent.Kind.CONFIRMED if received else PayoutEvent.Kind.DISPUTED
    event = PayoutEvent.objects.create(operation=operation, kind=kind, actor=employee, note=note)
    record(employee, "finance.payout_confirmed" if received else "finance.payout_disputed", operation,
           {"amount": str(operation.amount), "currency": operation.currency, "note": note})
    who, sum_text = employee.display_name, amount_text(operation.amount, operation.currency)
    if received:
        notify(founders(), "announcement", f"{who} {sum_text} to‘lovni oldi", "Xodim to‘lovni olganini tasdiqladi.",
               PAYOUTS_URL, f"payout-reply:{event.pk}")
    else:
        notify(founders(), "approval", f"E’tiroz: {who} {sum_text} to‘lovni olmaganini bildirdi",
               note or "Xodim to‘lovni olmaganini bildirdi. Tekshirib, hal qiling.", PAYOUTS_URL, f"payout-reply:{event.pk}")
    return event


def remind_payout(actor, operation_id):
    """Asoschi javob kutilayotgan to'lov haqida xodimga qayta eslatadi (soatiga bir martadan ko'p emas)."""
    _require_founder(actor)
    try:
        operation = payouts().get(pk=operation_id)
    except (FinanceOperation.DoesNotExist, ValidationError, ValueError):
        raise ValidationError("To‘lov topilmadi.")
    if payout_state(operation) != "pending":
        raise ValidationError("Xodim bu to‘lovga allaqachon javob bergan.")
    from apps.notifications.models import Notification
    hour = timezone.now().strftime("%Y%m%d%H")
    key = f"payout-remind:{operation.pk}:{hour}"
    if Notification.objects.filter(recipient=operation.employee, dedupe_key=key).exists():
        raise ValidationError("Eslatma yaqinda yuborilgan. Birozdan keyin qayta urinib ko‘ring.")
    notify([operation.employee], "approval", f"Eslatma: sizga {amount_text(operation.amount, operation.currency)} to‘lov berildimi?",
           "Asoschi javobingizni kutmoqda. Iltimos, to‘lovni olganingizni tasdiqlang yoki e’tiroz bildiring.",
           ASK_URL, key)
    record(actor, "finance.payout_reminded", operation, {"employee": str(operation.employee)})


@transaction.atomic
def resolve_payout(actor, operation_id, action, note):
    """Founder's documented review of a disputed payout: ask again, or reverse it with a correction entry."""
    from .models import PayoutEvent
    _require_founder(actor)
    _lock()
    operation = _payout_for_update(operation_id)
    if payout_state(operation) != "disputed":
        raise ValidationError("Faqat e’tiroz bildirilgan to‘lov ko‘rib chiqiladi.")
    note = (note or "").strip()
    if len(note) < 5:
        raise ValidationError("Tekshiruv natijasini yozing (kamida 5 belgi).")
    sum_text = amount_text(operation.amount, operation.currency)
    if action == "reask":
        event = PayoutEvent.objects.create(operation=operation, kind=PayoutEvent.Kind.REASKED, actor=actor, note=note)
        notify([operation.employee], "approval", f"Sizga {sum_text} to‘lov berildimi?", f"Qayta so‘rov: {note}",
               ASK_URL, f"payout:{operation.pk}:{event.pk}")
    elif action == "reverse":
        paid = operation.entries.get(category=C.PAID, corrects__isnull=True)
        remaining = paid.amount + (paid.corrections.aggregate(n=Sum("amount"))["n"] or ZERO)
        if remaining <= 0:
            raise ValidationError("Bu to‘lov allaqachon tuzatilgan.")
        correction = FinanceOperation.objects.create(
            idempotency_key=uuid.uuid5(COMPLETION_NAMESPACE, f"reverse:{operation.pk}"),
            fingerprint=hashlib.sha256(f"reverse:{operation.pk}".encode()).hexdigest(), kind=OperationKind.CORRECTION,
            amount=remaining, currency=operation.currency, employee=operation.employee, project=operation.project,
            administrator=actor, description=f"E’tiroz bo‘yicha to‘lov bekor qilindi: {note}", payload={"entry_id": str(paid.pk)},
            approvals_required=0, status=FinanceOperation.Status.APPROVED, finalized_at=timezone.now())
        _line(correction, actor, C.PAID, -remaining, operation.employee, None, paid)
        event = PayoutEvent.objects.create(operation=operation, kind=PayoutEvent.Kind.REVERSED, actor=actor, note=note, correction=correction)
        notify([operation.employee], "announcement", f"{sum_text} to‘lov bekor qilindi",
               f"E’tirozingiz ko‘rib chiqildi: {note}. Summa yana «To‘lanishi kerak» qismiga qaytdi.", BALANCE_URL, f"payout-reversed:{operation.pk}")
    else:
        raise ValidationError("Noma’lum qaror.")
    record(actor, "finance.payout_resolved", operation, {"action": action, "note": note})
    return event


# ------------------------------------------------------------------ account views

def payable_by_employee():
    """{employee_id: {currency: payable}} — faqat musbat qoldiqlar (to'lov formasidagi ro'yxat uchun)."""
    rows = (LedgerEntry.objects.filter(employee__isnull=False, category__in=EARNINGS + [C.PAID])
            .values("employee_id", "currency")
            .annotate(earned=Sum("amount", filter=Q(category__in=EARNINGS)), paid=Sum("amount", filter=Q(category=C.PAID))))
    result = {}
    for row in rows:
        owed = (row["earned"] or ZERO) - (row["paid"] or ZERO)
        if owed > 0:
            result.setdefault(row["employee_id"], {})[row["currency"]] = owed
    return result


def project_accounts(currency, employee=None):
    """Per employee and project: earned, paid, remaining and payment status, straight from the ledger."""
    qs = LedgerEntry.objects.filter(currency=currency, employee__isnull=False, category__in=EARNINGS + [C.PAID])
    if employee is not None:
        qs = qs.filter(employee=employee)
    rows = list(qs.values("employee_id", "project_id").annotate(
        earned=Sum("amount", filter=Q(category__in=EARNINGS)), paid=Sum("amount", filter=Q(category=C.PAID))))
    people = User.objects.in_bulk({row["employee_id"] for row in rows})
    projects = Project.objects.in_bulk({row["project_id"] for row in rows if row["project_id"]})
    agreements = {}
    for agreement in AgreementSnapshot.objects.filter(project_id__in=projects).order_by("project_id", "-version"):
        agreements.setdefault(agreement.project_id, agreement)
    for row in rows:
        row["earned"], row["paid"] = row["earned"] or ZERO, row["paid"] or ZERO
    # Loyihaga bog'lanmagan to'lov ("umumiy hisobdan") avval ish haqi/mukofotni, ortib qolgani esa
    # eng eski loyiha qarzlarini yopadi. Aks holda loyiha qatorlari "to'lanishi kerak" bo'lib qolardi,
    # umumiy qator esa "to'langan" deb ko'rinardi — jami to'g'ri bo'lsa ham holatlar chalkashardi.
    by_employee = {}
    for row in rows:
        by_employee.setdefault(row["employee_id"], []).append(row)
    for items in by_employee.values():
        general = next((r for r in items if r["project_id"] is None), None)
        if not general or general["paid"] <= general["earned"]:
            continue
        excess = general["paid"] - general["earned"]
        general["paid"] = general["earned"]
        due = sorted((r for r in items if r["project_id"] is not None and r["earned"] > r["paid"]),
                     key=lambda r: (projects[r["project_id"]].completed_at is None,
                                    projects[r["project_id"]].completed_at or timezone.now(), r["project_id"]))
        for r in due:
            take = min(excess, r["earned"] - r["paid"])
            r["paid"] += take
            excess -= take
            if not excess:
                break
        general["paid"] += excess  # nazariy jihatdan qolmaydi: to'lov qarzdan oshishi taqiqlangan
    result = []
    for row in rows:
        earned, paid = row["earned"], row["paid"]
        if not earned and not paid:
            continue
        project = projects.get(row["project_id"])
        agreement = agreements.get(row["project_id"])
        percent = next((Decimal(s["percent"]) for s in (agreement.shares if agreement else []) if int(s["employee"]) == row["employee_id"]), None)
        remaining = earned - paid
        status = ("paid", "To‘liq to‘langan") if paid > 0 and remaining <= 0 else (("partial", "Qisman to‘langan") if paid > 0 else ("due", "To‘lanishi kerak"))
        result.append({"employee": people[row["employee_id"]], "project": project, "percent": percent_text(percent) if percent is not None else None,
                       "earned": earned, "paid": paid, "remaining": remaining, "status": status[0], "status_label": status[1],
                       "completed_at": project.completed_at if project else None})
    result.sort(key=lambda r: (-(r["remaining"] > 0), str(r["employee"]), r["project"].name if r["project"] else ""))
    return result


def account_summary(employee, currency):
    rows = project_accounts(currency, employee)
    balance = employee_balance(employee, currency)
    states = {"confirmed": ZERO, "unconfirmed": ZERO}
    for operation in payouts().filter(employee=employee, currency=currency):
        state = payout_state(operation)
        if state == "confirmed":
            states["confirmed"] += operation.amount
        elif state in ("pending", "disputed"):
            states["unconfirmed"] += operation.amount
    return {**balance, "rows": rows,
            "partial": sum((r["remaining"] for r in rows if r["status"] == "partial"), ZERO),
            "partial_count": sum(1 for r in rows if r["status"] == "partial"),
            "fully_paid": sum((r["paid"] for r in rows if r["status"] == "paid"), ZERO),
            "fully_paid_count": sum(1 for r in rows if r["status"] == "paid"),
            "confirmed": states["confirmed"], "unconfirmed": states["unconfirmed"]}
