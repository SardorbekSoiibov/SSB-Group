import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.db.models import Q
from apps.core.storage import RandomName, private_storage

USER = settings.AUTH_USER_MODEL
CURRENCIES = [("UZS", "UZS"), ("USD", "USD"), ("EUR", "EUR")]


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("O‘zgarmas yozuvni tahrirlash mumkin emas.")

    def delete(self):
        raise ValueError("O‘zgarmas yozuvni o‘chirish mumkin emas.")


class Immutable(models.Model):
    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Asl yozuv saqlanadi. Tuzatish amali yarating.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Moliyaviy tarix o‘chirilmaydi.")


class OperationKind(models.TextChoices):
    AGREEMENT = "agreement", "Moliyaviy kelishuv"
    RECEIPT = "receipt", "Mijoz to‘lovi"
    PAYMENT = "payment", "Xodimga to‘lov"
    SALARY = "salary", "Ish haqi hisoblash"
    BONUS = "bonus", "Mukofot hisoblash"
    EXPENSE = "expense", "Kompaniya xarajati"
    CORRECTION = "correction", "Tuzatish / qaytarish"
    COMPLETION = "completion", "Loyiha yakuni bo‘yicha daromad"

    @classmethod
    def manual(cls):
        """Kinds an administrator may request by hand. Completion earnings are created only by the system."""
        return [(key, label) for key, label in cls.choices if key != cls.COMPLETION]


class ApprovalRule(models.Model):
    kind = models.CharField(max_length=20, choices=OperationKind.choices)
    currency = models.CharField(max_length=3, choices=CURRENCIES, default="UZS")
    threshold = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    approvals = models.PositiveSmallIntegerField(default=1)
    capability = models.CharField(max_length=40, default="finance.approve")
    updated_by = models.ForeignKey(USER, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kind", "currency"], name="enterprise_unique_rule"),
            models.CheckConstraint(condition=Q(threshold__gte=0) & Q(approvals__gte=1) & Q(approvals__lte=3), name="enterprise_rule_bounds"),
        ]


class FinanceOperation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Tasdiq kutilmoqda"
        APPROVED = "approved", "Tasdiqlangan"
        REJECTED = "rejected", "Rad etilgan"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.UUIDField(unique=True)
    fingerprint = models.CharField(max_length=64)
    kind = models.CharField(max_length=20, choices=OperationKind.choices)
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=3, choices=CURRENCIES, default="UZS")
    employee = models.ForeignKey(USER, null=True, blank=True, on_delete=models.PROTECT, related_name="financial_operations")
    project = models.ForeignKey("crm.Project", null=True, blank=True, on_delete=models.PROTECT)
    administrator = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="registered_operations")
    description = models.TextField()
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    approvals_required = models.PositiveSmallIntegerField(default=1)
    approval_capability = models.CharField(max_length=40, default="finance.approve")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="enterprise_positive_operation")]

    @property
    def payment_status(self):
        if self.status != self.Status.APPROVED:
            return "Amal bajarilmagan"
        return "O‘tkazilgan" if self.kind in [OperationKind.PAYMENT, OperationKind.RECEIPT, OperationKind.EXPENSE] else "Hisoblangan"

    def __str__(self):
        return f"{self.get_kind_display()} · {self.amount} {self.currency}"


class ApprovalDecision(Immutable):
    operation = models.ForeignKey(FinanceOperation, on_delete=models.PROTECT, related_name="decisions")
    administrator = models.ForeignKey(USER, on_delete=models.PROTECT)
    approved = models.BooleanField()
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["operation", "administrator"], name="enterprise_one_vote")]


class AgreementSnapshot(Immutable):
    project = models.ForeignKey("crm.Project", on_delete=models.PROTECT, related_name="financial_agreements")
    operation = models.OneToOneField(FinanceOperation, on_delete=models.PROTECT)
    version = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=3, choices=CURRENCIES)
    company_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("30"))
    shares = models.JSONField()  # [{employee: id, percent: decimal string}]
    confirmed_by = models.ForeignKey(USER, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version"]
        constraints = [models.UniqueConstraint(fields=["project", "version"], name="enterprise_agreement_version")]


class LedgerEntry(Immutable):
    class Category(models.TextChoices):
        RECEIPT = "receipt", "Mijozdan tushum"
        EARNING = "earning", "Loyihadan daromad"
        SALARY = "salary", "Ish haqi"
        BONUS = "bonus", "Mukofot"
        PAID = "paid", "Haqiqiy to‘lov"
        EXPENSE = "expense", "Xarajat"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    line_key = models.CharField(max_length=140, unique=True)
    operation = models.ForeignKey(FinanceOperation, on_delete=models.PROTECT, related_name="entries")
    category = models.CharField(max_length=12, choices=Category.choices)
    amount = models.DecimalField(max_digits=20, decimal_places=2)  # negative only for approved corrections
    currency = models.CharField(max_length=3, choices=CURRENCIES)
    employee = models.ForeignKey(USER, null=True, blank=True, on_delete=models.PROTECT, related_name="ledger_entries")
    project = models.ForeignKey("crm.Project", null=True, blank=True, on_delete=models.PROTECT, related_name="ledger_entries")
    agreement = models.ForeignKey(AgreementSnapshot, null=True, blank=True, on_delete=models.PROTECT)
    corrects = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="corrections")
    administrator = models.ForeignKey(USER, on_delete=models.PROTECT)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "id"]
        constraints = [
            models.CheckConstraint(condition=~Q(amount=0), name="enterprise_nonzero_entry"),
            models.CheckConstraint(condition=Q(amount__gt=0) | Q(corrects__isnull=False), name="enterprise_negative_only_correction"),
            models.CheckConstraint(condition=Q(category__in=["receipt", "expense"], employee__isnull=True) | Q(category__in=["earning", "salary", "bonus", "paid"], employee__isnull=False), name="enterprise_entry_owner"),
        ]


class PayoutMethod(models.TextChoices):
    CASH = "cash", "Naqd pul"
    CARD = "card", "Bank kartasiga"
    TRANSFER = "transfer", "Bank o‘tkazmasi"
    OTHER = "other", "Boshqa usul"


class PayoutDetail(Immutable):
    """What the Founder declared when registering an actual payout. One per PAYMENT operation, never edited."""
    operation = models.OneToOneField(FinanceOperation, on_delete=models.PROTECT, related_name="payout")
    paid_on = models.DateField()
    method = models.CharField(max_length=12, choices=PayoutMethod.choices)
    reference = models.CharField(max_length=120, blank=True)
    proof = models.FileField(storage=private_storage, upload_to=RandomName("payout-proofs"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PayoutEvent(Immutable):
    """Append-only receipt history of a payout. The current state is always the latest event."""

    class Kind(models.TextChoices):
        CONFIRMED = "confirmed", "Xodim tasdiqladi"
        DISPUTED = "disputed", "Tasdiqlanmagan / E’tiroz bildirilgan"
        REASKED = "reasked", "Xodimdan qayta so‘raldi"
        REVERSED = "reversed", "Tuzatish bilan bekor qilindi"

    operation = models.ForeignKey(FinanceOperation, on_delete=models.PROTECT, related_name="payout_events")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    actor = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    note = models.TextField(blank=True)
    correction = models.ForeignKey(FinanceOperation, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class ArchivePolicy(models.Model):
    project = models.OneToOneField("crm.Project", on_delete=models.PROTECT)
    access_hash = models.CharField(max_length=255)
    version = models.PositiveIntegerField(default=1)
    updated_by = models.ForeignKey(USER, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)


class ArchiveAccess(models.Model):
    """One company-wide archive code. Only the Founder may rotate it."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    access_hash = models.CharField(max_length=255, blank=True, default='')
    version = models.PositiveIntegerField(default=1)
    updated_by = models.ForeignKey(USER, on_delete=models.PROTECT, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(id=1), name='enterprise_archive_access_singleton')]

    @classmethod
    def load(cls):
        return cls.objects.get_or_create(pk=1)[0]


class ArchiveAccessAttempt(models.Model):
    user = models.OneToOneField(USER, on_delete=models.CASCADE, primary_key=True)
    failures = models.PositiveSmallIntegerField(default=0)
    window_started = models.DateTimeField()


class ProjectArchive(Immutable):
    project = models.ForeignKey("crm.Project", on_delete=models.PROTECT, null=True, blank=True)
    project_name = models.CharField(max_length=200, blank=True, default='')
    upload_key = models.UUIDField(null=True, unique=True, editable=False)
    uploader = models.ForeignKey(USER, on_delete=models.PROTECT)
    file = models.FileField(storage=private_storage, upload_to=RandomName("project-archives"))
    filename = models.CharField(max_length=200)
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    scan_status = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def display_project_name(self):
        return self.project_name or (self.project.name if self.project_id else 'Nomsiz loyiha')

    def __str__(self):
        return self.display_project_name

    @property
    def file_type(self):
        return self.filename.rsplit('.', 1)[-1].upper()[:4] if '.' in self.filename else 'FAYL'


class WorkShift(models.Model):
    employee = models.ForeignKey(USER, on_delete=models.PROTECT)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    location = models.CharField(max_length=180)
    notes = models.TextField(blank=True)
    cancelled = models.BooleanField(default=False)
    administrator = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="scheduled_shifts")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["starts_at"]
        constraints = [models.CheckConstraint(condition=Q(ends_at__gt=models.F("starts_at")), name="enterprise_shift_duration")]


class PerformanceReview(Immutable):
    employee = models.ForeignKey(USER, on_delete=models.PROTECT)
    period_start = models.DateField()
    period_end = models.DateField()
    metrics = models.JSONField()
    score = models.DecimalField(max_digits=5, decimal_places=2)
    feedback = models.TextField()
    analysis = models.TextField()
    analysis_source = models.CharField(max_length=30, default="rules")
    administrator = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="performance_reviews_created")
    created_at = models.DateTimeField(auto_now_add=True)


class ReviewApproval(Immutable):
    review = models.OneToOneField(PerformanceReview, on_delete=models.PROTECT)
    administrator = models.ForeignKey(USER, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class DashboardLayout(models.Model):
    user = models.OneToOneField(USER, on_delete=models.CASCADE)
    widgets = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)


class WeeklyRating(models.Model):
    """One week between two Sundays 00:00. Nobody but the boss sees it before publish_on."""

    publish_on = models.DateField(unique=True)
    prize = models.CharField(max_length=200, blank=True)
    announced = models.BooleanField(default=False)
    updated_by = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-publish_on"]


class WeeklyPlace(models.Model):
    rating = models.ForeignKey(WeeklyRating, on_delete=models.CASCADE, related_name="places")
    employee = models.ForeignKey(USER, on_delete=models.CASCADE, related_name="weekly_places")
    place = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["place"]
        constraints = [models.UniqueConstraint(fields=["rating", "place"], name="enterprise_one_person_per_place"),
                       models.UniqueConstraint(fields=["rating", "employee"], name="enterprise_one_place_per_person")]


class EvaluationWeek(models.Model):
    """A Monday–Sunday evaluation cohort and its immutable published snapshot."""
    starts_on = models.DateField(unique=True)
    weights = models.JSONField(default=dict)
    published_at = models.DateTimeField(null=True, blank=True)
    ranking = models.JSONField(default=list)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-starts_on']


class WeeklyEvaluation(models.Model):
    week = models.ForeignKey(EvaluationWeek, on_delete=models.PROTECT, related_name='evaluations')
    employee = models.ForeignKey(USER, on_delete=models.PROTECT, related_name='evaluations')
    evidence = models.JSONField(default=dict)
    original_criteria = models.JSONField(default=dict)
    original_score = models.DecimalField(max_digits=5, decimal_places=2)
    final_criteria = models.JSONField(default=dict)
    final_score = models.DecimalField(max_digits=5, decimal_places=2)
    analysis = models.JSONField(default=dict)
    source = models.CharField(max_length=20, default='rules')
    status = models.CharField(max_length=20, default='draft', choices=[('draft', 'Tekshiruv kutilmoqda'), ('returned', 'Tuzatishga qaytarilgan'), ('approved', 'Tasdiqlangan')])
    feedback = models.TextField(blank=True)
    adjustment_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(USER, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    approved_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-week__starts_on', '-final_score', 'employee_id']
        constraints = [models.UniqueConstraint(fields=['week', 'employee'], name='one_weekly_evaluation'),
                       models.CheckConstraint(condition=Q(original_score__gte=0, original_score__lte=100, final_score__gte=0, final_score__lte=100), name='weekly_score_bounds')]


class WeeklyReward(models.Model):
    week = models.ForeignKey(EvaluationWeek, on_delete=models.PROTECT, related_name='rewards')
    place = models.PositiveSmallIntegerField()
    kind = models.CharField(max_length=20, choices=[('gift', 'Sovg‘a'), ('cash', 'Pul mukofoti'), ('recognition', 'E’tirof')])
    description = models.CharField(max_length=300)
    value = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, choices=CURRENCIES, default='UZS')
    status = models.CharField(max_length=20, default='draft', choices=[('draft', 'Qoralama'), ('approved', 'Tasdiqlangan'), ('issued', 'Topshirilgan')])
    employee = models.ForeignKey(USER, null=True, blank=True, on_delete=models.PROTECT)
    operation = models.OneToOneField(FinanceOperation, null=True, blank=True, on_delete=models.PROTECT)
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    updated_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['place']
        constraints = [models.UniqueConstraint(fields=['week', 'place'], name='one_weekly_reward'),
                       models.CheckConstraint(condition=Q(place__gte=1, place__lte=3, value__gte=0), name='weekly_reward_bounds')]


class ManagerWeeklyScore(models.Model):
    """Rahbar hafta davomida qo‘yadigan baho. Dushanba 00:00 da hafta yopilganda yakuniy ballga qo‘shiladi."""
    week_start = models.DateField()
    employee = models.ForeignKey(USER, on_delete=models.CASCADE, related_name='manager_weekly_scores')
    score = models.DecimalField(max_digits=5, decimal_places=2)
    comment = models.TextField()
    author = models.ForeignKey(USER, on_delete=models.PROTECT, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-week_start', 'employee_id']
        constraints = [models.UniqueConstraint(fields=['week_start', 'employee'], name='one_manager_weekly_score'),
                       models.CheckConstraint(condition=Q(score__gte=0, score__lte=100), name='manager_weekly_score_bounds')]


# Ishga kela olmaslik so‘rovlari alohida faylda saqlanadi.
from .absence_models import AbsenceRequest  # noqa: E402,F401
