from django.conf import settings
from apps.core.models import WorkspaceSettings
from apps.core.currencies import SUPPORTED_CURRENCIES as CURRENCIES
import uuid
from decimal import Decimal, ROUND_DOWN
from django import forms
from django.utils import timezone
from apps.accounts.models import User
from apps.accounts.policies import visible_employees
from apps.core.forms import StyledFormMixin, DateTimeInput, DateInput
from apps.crm.models import Project
from apps.crm.policies import visible_projects
from .models import OperationKind, ApprovalRule


class OperationForm(StyledFormMixin, forms.Form):
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    kind = forms.ChoiceField(label="Amal turi", choices=OperationKind.manual())
    amount = forms.DecimalField(label="Summa / kelishuv narxi", max_digits=20, decimal_places=2, min_value=Decimal('.01'))
    currency = forms.ChoiceField(label="Valyuta", choices=CURRENCIES)
    employee = forms.ModelChoiceField(label="Xodim", queryset=User.objects.none(), required=False)
    project = forms.ModelChoiceField(label="Loyiha", queryset=Project.objects.none(), required=False)
    description = forms.CharField(label="Sabab va manba (to‘lov hujjati / izoh)", min_length=5, widget=forms.Textarea(attrs={"rows": 3}))
    company_percent = forms.DecimalField(label="Kompaniya ulushi (%)", max_digits=7, decimal_places=4, min_value=0, max_value=100, initial=30, required=False)
    eligible = forms.ModelMultipleChoiceField(label="Kelishuvdagi xodimlar (teng taqsimlash)", queryset=User.objects.none(), required=False)
    distribution = forms.JSONField(label="Ixtiyoriy aniq ulushlar (JSON)", required=False, widget=forms.Textarea(attrs={"rows": 2, "placeholder": '[{"employee": 2, "percent": "70"}]'}))
    correction_entry = forms.UUIDField(label="Tuzatiladigan reyestr ID (faqat tuzatish uchun)", required=False)

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.core.models import WorkspaceSettings
        defaults=WorkspaceSettings.load()
        self.initial.setdefault('company_percent',defaults.company_share_percent)
        self.initial.setdefault('currency',defaults.default_currency if defaults.default_currency in dict(CURRENCIES) else 'UZS')
        employees = visible_employees(actor)
        self.fields['employee'].queryset = employees
        self.fields['employee'].label_from_instance=lambda user:f'{user.display_name} · @{user.username}'+(' · faol emas' if not user.is_active else '')
        self.fields['eligible'].queryset = employees.filter(is_active=True)
        self.fields['project'].queryset = visible_projects(actor)
        if not actor.has_cap('finance.distribute'):
            self.fields['kind'].choices = [(key, label) for key, label in OperationKind.manual() if key != OperationKind.AGREEMENT]

    def clean(self):
        data = super().clean()
        if data.get('kind') == OperationKind.AGREEMENT:
            if data.get('company_percent') is None:
                self.add_error('company_percent', 'Kompaniya ulushini kiriting.')
            if not data.get('distribution') and not data.get('eligible') and data.get('company_percent') != 100:
                self.add_error('eligible', 'Xodimlarni yoki aniq ulushlarni kiriting.')
        return data

    def payload(self):
        data = self.cleaned_data
        if data['kind'] == OperationKind.AGREEMENT:
            shares = data.get('distribution')
            if not shares:
                people = list(data.get('eligible') or [])
                pool = Decimal(100) - data['company_percent']
                each = (pool / len(people)).quantize(Decimal('.0001'), rounding=ROUND_DOWN) if people else 0
                shares = [{"employee": user.pk, "percent": str(each if i < len(people) - 1 else pool - each * i)} for i, user in enumerate(people)]
            return {"shares": shares, "company_percent": str(data['company_percent'])}
        if data['kind'] == OperationKind.CORRECTION:
            return {"entry_id": str(data.get('correction_entry') or '')}
        return {}


PROOF_TYPES = ('.pdf', '.jpg', '.jpeg', '.png', '.webp', '.heic')


class PayoutForm(StyledFormMixin, forms.Form):
    """Founder's record of money actually handed over. The amount is checked against the payable on the server."""
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    employee = forms.ModelChoiceField(label="Xodim", queryset=User.objects.none())
    project = forms.ModelChoiceField(label="Loyiha", queryset=Project.objects.none(), required=False,
                                     empty_label="Loyihaga bog‘lanmagan (umumiy qarzdan)")
    amount = forms.DecimalField(label="To‘lanayotgan summa", max_digits=20, decimal_places=2, min_value=Decimal('.01'))
    currency = forms.ChoiceField(label="Valyuta", choices=CURRENCIES)
    paid_on = forms.DateField(label="To‘lov sanasi", widget=DateInput)
    method = forms.ChoiceField(label="To‘lov usuli")
    description = forms.CharField(label="Izoh", min_length=5, max_length=500, widget=forms.Textarea(attrs={"rows": 2}))
    reference = forms.CharField(label="To‘lov raqami / havola (ixtiyoriy)", max_length=120, required=False)
    proof = forms.FileField(label="Tasdiqlovchi hujjat yoki chek (ixtiyoriy)", required=False,
                            widget=forms.ClearableFileInput(attrs={'accept': ','.join(PROOF_TYPES)}))

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import PayoutMethod
        defaults = WorkspaceSettings.load()
        self.initial.setdefault('currency', defaults.default_currency if defaults.default_currency in dict(CURRENCIES) else 'UZS')
        self.initial.setdefault('paid_on', timezone.localdate())
        self.fields['method'].choices = PayoutMethod.choices
        self.fields['employee'].queryset = visible_employees(actor).order_by('first_name', 'last_name')
        self.fields['employee'].label_from_instance = lambda user: f'{user.display_name} · @{user.username}' + (' · faol emas' if not user.is_active else '')
        self.fields['project'].queryset = visible_projects(actor)

    def clean_paid_on(self):
        value = self.cleaned_data['paid_on']
        if value > timezone.localdate():
            raise forms.ValidationError("Kelajakdagi sana bilan to‘lov qayd etilmaydi.")
        return value

    def clean_proof(self):
        proof = self.cleaned_data.get('proof')
        if proof:
            if not proof.name.lower().endswith(PROOF_TYPES):
                raise forms.ValidationError("Faqat PDF yoki rasm (JPG, PNG, WEBP, HEIC) yuklang.")
            if proof.size > 10 * 1024 * 1024:
                raise forms.ValidationError("Fayl hajmi 10 MB dan oshmasin.")
        return proof


class RuleForm(StyledFormMixin, forms.ModelForm):
    currency = forms.ChoiceField(label="Valyuta", choices=CURRENCIES)
    class Meta:
        model = ApprovalRule
        fields = ['kind', 'currency', 'threshold', 'approvals', 'capability']
        labels = {'kind':'Amal turi','currency':'Valyuta','threshold':'Tasdiq talab qilinadigan summa','approvals':'Mustaqil tasdiqlar soni','capability':'Tasdiqlash huquqi'}

    def clean_capability(self):
        capability = self.cleaned_data['capability']
        if capability != 'finance.approve':
            raise forms.ValidationError('Tasdiqlovchi uchun finance.approve huquqini tanlang.')
        return capability


class ShiftForm(StyledFormMixin, forms.Form):
    employee = forms.ModelChoiceField(label="Xodim", queryset=User.objects.none())
    starts_at = forms.DateTimeField(label="Boshlanish", widget=DateTimeInput())
    ends_at = forms.DateTimeField(label="Tugash", widget=DateTimeInput())
    location = forms.CharField(label="Ish joyi", max_length=180, widget=forms.TextInput(attrs={'placeholder':'Masalan: Ofis'}))
    notes = forms.CharField(label="Izoh", required=False, widget=forms.Textarea(attrs={'rows': 2,'placeholder':'Ixtiyoriy'}))
    # Takrorlash: bir xil vaqt bilan haftaning tanlangan kunlariga va keyingi haftalarga ham qo'yiladi.
    days = forms.TypedMultipleChoiceField(label="Haftaning qaysi kunlari", required=False, coerce=int,
        choices=[(0,'Du'),(1,'Se'),(2,'Cho'),(3,'Pa'),(4,'Ju'),(5,'Sha'),(6,'Ya')], widget=forms.CheckboxSelectMultiple,
        help_text="Belgilanmasa — faqat boshlanish sanasidagi kun. Masalan, Du–Ju belgilansa, har biriga shu vaqtda smena qo‘yiladi.")
    repeat = forms.TypedChoiceField(label="Takrorlash", coerce=int, initial=1, required=False, empty_value=1,
        choices=[(1,'Faqat shu hafta'),(4,'4 hafta'),(8,'8 hafta'),(12,'12 hafta (3 oy)'),(26,'26 hafta (yarim yil)')],
        help_text="Keyingi haftalarga ham xuddi shunday qo‘yiladi. Band vaqtlar o‘tkazib yuboriladi.")

    def __init__(self, *args, actor, editing=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].queryset = visible_employees(actor).filter(is_active=True)
        if editing:  # mavjud smenani tahrirlashda takrorlash yo'q
            del self.fields['days']
            del self.fields['repeat']


class ArchiveForm(StyledFormMixin, forms.Form):
    project_name = forms.CharField(label="Loyiha nomi", min_length=2, max_length=200,
        widget=forms.TextInput(attrs={'placeholder':'Masalan: Mehmonxona boshqaruv tizimi'}))
    file = forms.FileField(label="Loyiha arxivi (RAR yoki ZIP)", widget=forms.ClearableFileInput(attrs={'accept':'.rar,.zip'}))
    upload_key = forms.UUIDField(widget=forms.HiddenInput)

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:self.initial['upload_key']=uuid.uuid4()
        limit=min(settings.ARCHIVE_MAX_MB,WorkspaceSettings.load().archive_max_mb)
        self.fields['file'].help_text=f'RAR yoki ZIP, {limit} MB gacha'


class ArchiveUnlockForm(StyledFormMixin, forms.Form):
    code = forms.CharField(label='Arxivga kirish kodi',max_length=128,
        widget=forms.PasswordInput(attrs={'autocomplete':'off','placeholder':'Asoschi bergan kodni kiriting'}))


class ArchiveCodeForm(StyledFormMixin, forms.Form):
    code = forms.CharField(label='Yangi umumiy kod',min_length=8,max_length=128,
        widget=forms.PasswordInput(attrs={'autocomplete':'new-password'}))
    confirm_code = forms.CharField(label='Yangi kodni takrorlang',min_length=8,max_length=128,
        widget=forms.PasswordInput(attrs={'autocomplete':'new-password'}))

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('auto_id', 'archive_new_%s')
        super().__init__(*args, **kwargs)

    def clean(self):
        data=super().clean()
        if data.get('code') and data.get('confirm_code') and data['code']!=data['confirm_code']:
            self.add_error('confirm_code','Kiritilgan kodlar bir xil bo‘lishi kerak.')
        return data


class ReviewForm(StyledFormMixin, forms.Form):
    employee = forms.ModelChoiceField(label="Xodim", queryset=User.objects.none())
    period_start = forms.DateField(label="Davr boshi", widget=DateInput())
    period_end = forms.DateField(label="Davr oxiri", widget=DateInput())
    quality_score = forms.DecimalField(label="Ish sifati (ixtiyoriy)", min_value=0, max_value=100, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={'placeholder': '0–100', 'step': 'any'}))
    director_score = forms.DecimalField(label="Rahbar bahosi (ixtiyoriy)", min_value=0, max_value=100, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={'placeholder': '0–100', 'step': 'any'}))
    feedback = forms.CharField(label="Rahbar izohi", min_length=10, error_messages={'min_length': 'Izoh kamida 10 ta belgidan iborat bo‘lsin.'},
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Ish sifati, hissasi va tavsiyalaringiz'}))

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].queryset = visible_employees(actor).filter(is_active=True).exclude(pk=actor.pk)
        today = timezone.localdate()
        self.initial.setdefault('period_start', today.replace(day=1))
        self.initial.setdefault('period_end', today)

    def clean(self):
        data=super().clean()
        start,end=data.get('period_start'),data.get('period_end')
        if start and end:
            if end<start:self.add_error('period_end','Davr oxiri boshlanish sanasidan oldin bo‘lishi mumkin emas.')
            elif (end-start).days>366:self.add_error('period_end','Davr 1 yildan oshmasligi kerak.')
        if (data.get('quality_score') is None)!=(data.get('director_score') is None):
            raise forms.ValidationError('Qo‘shimcha baholash uchun sifat va rahbar bahosini birga kiriting yoki ikkalasini ham bo‘sh qoldiring.')
        return data
