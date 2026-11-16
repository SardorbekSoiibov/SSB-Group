from django import forms
from django.contrib.auth import forms as auth_forms
from django.db.models import Q

from apps.core.forms import CommaListField, DateInput, StyledFormMixin
from apps.notifications.models import Notification

from . import policies
from .models import CAPABILITY_GROUPS, Capability, Department, Role, User


class LoginForm(StyledFormMixin, auth_forms.AuthenticationForm):
    error_messages = {
        "invalid_login": "Login yoki parol noto'g'ri.",
        "inactive": "Bu hisob faol emas. Rahbaringizga murojaat qiling.",
    }

    def confirm_login_allowed(self,user):
        super().confirm_login_allowed(user)
        if user.role_id and not user.role.is_active:
            raise forms.ValidationError('Lavozimingiz to‘xtatilgan. Rahbaringizga murojaat qiling.',code='inactive')


PASSWORD_MESSAGES = {
    "password_incorrect": "Joriy parol noto‘g‘ri.",
    "password_mismatch": "Ikkala yangi parol bir xil emas.",
    "password_too_short": "Parol kamida 10 ta belgidan iborat bo‘lsin.",
    "password_too_common": "Bu parol juda oddiy, boshqasini tanlang.",
    "password_too_similar": "Parol shaxsiy ma’lumotlaringizga juda o‘xshash.",
    "password_entirely_numeric": "Parol faqat raqamlardan iborat bo‘lmasin.",
}


class UzbekPasswordMixin:
    """Shows password fields and the validators' messages in Uzbek."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {"old_password": ("Joriy parol", "current-password"), "new_password1": ("Yangi parol", "new-password"),
                  "new_password2": ("Yangi parolni takrorlang", "new-password")}
        for name, (label, autocomplete) in labels.items():
            if name in self.fields:
                field = self.fields[name]
                field.label, field.help_text = label, ""
                field.widget.attrs["autocomplete"] = autocomplete
                field.widget.attrs.pop("autofocus", None)
        if "new_password1" in self.fields:
            self.fields["new_password1"].help_text = "Oddiy yoki ismingizga o‘xshash parol qabul qilinmaydi."

    def _post_clean(self):
        super()._post_clean()
        for errors in self._errors.values():
            errors.data = [forms.ValidationError(PASSWORD_MESSAGES[item.code], code=item.code)
                           if item.code in PASSWORD_MESSAGES else item for item in errors.as_data()]


class PasswordChangeForm(UzbekPasswordMixin, StyledFormMixin, auth_forms.PasswordChangeForm):
    pass


class SetPasswordForm(UzbekPasswordMixin, StyledFormMixin, auth_forms.SetPasswordForm):
    pass


class PasswordResetForm(StyledFormMixin, auth_forms.PasswordResetForm):
    pass


class EmployeeForm(StyledFormMixin, forms.ModelForm):
    """Used by the founder (or anyone the founder lets manage employees).

    Only the founder decides which functions appear in an employee's cabinet: nothing is shown
    unless it is ticked here.
    """

    skills = CommaListField(label="Ko'nikmalar", required=False)
    remove_contract = forms.BooleanField(label="Shartnomani olib tashlash", required=False)
    capabilities = forms.MultipleChoiceField(
        label="Kabinetdagi funksiyalar", choices=Capability.choices, required=False, widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = User
        fields = [
            "first_name", "last_name", "username", "email", "phone", "telegram", "photo",
            "job_title", "department", "manager", "joined_on", "skills", "allow_screenshots",
            "contract", "contract_number", "contract_signed_on", "contract_ends_on",
        ]
        labels = {"first_name": "Ism", "last_name": "Familiya", "username": "Login", "email": "Elektron pochta"}
        widgets = {
            "joined_on": DateInput(), "photo": forms.FileInput, "contract_signed_on": DateInput(), "contract_ends_on": DateInput(),
            "contract": forms.FileInput(attrs={"accept": ".pdf,.doc,.docx,.jpg,.jpeg,.png"}),
        }

    CONTRACT_FIELDS = ("contract", "contract_number", "contract_signed_on", "contract_ends_on")

    def main_fields(self):
        return [f for f in self if f.name not in self.CONTRACT_FIELDS and f.name not in ("capabilities", "remove_contract")]

    def save(self, commit=True):
        old = ""
        if self.instance.pk:
            old = User.objects.filter(pk=self.instance.pk).values_list("contract", flat=True).first() or ""
        if self.cleaned_data.get("remove_contract"):
            self.instance.contract = ""
        user = super().save(commit)
        if commit and old and old != (user.contract.name or ""):
            # Almashtirilgan yoki olib tashlangan eski shartnoma fayli diskda qolmasin.
            from django.db import transaction
            storage = user._meta.get_field("contract").storage
            transaction.on_commit(lambda: storage.delete(old))
        return user

    def contract_fields(self):
        return [self[name] for name in self.CONTRACT_FIELDS]

    def clean(self):
        data = super().clean()
        signed, ends = data.get("contract_signed_on"), data.get("contract_ends_on")
        if signed and ends and ends < signed:
            self.add_error("contract_ends_on", "Amal qilish muddati imzolangan sanadan oldin bo‘lishi mumkin emas.")
        if self.cleaned_data.get("remove_contract") and data.get("contract") and data["contract"] != self.instance.contract:
            self.add_error("contract", "Yangi fayl yuklayapsiz — “Shartnomani olib tashlash” belgisini olib tashlang.")
        return data

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["manager"].queryset = User.objects.filter(status=User.Status.ACTIVE).exclude(pk=self.instance.pk)
        if not actor.company_scope:
            self.fields["department"].queryset = Department.objects.filter(pk=actor.department_id)
            self.fields["department"].required = True
        if actor.is_owner:
            if self.instance.pk and self.instance.role_id and not self.instance.role.is_owner:
                self.fields["capabilities"].initial = list(self.instance.role.capabilities)
        else:
            # Huquqlarni faqat Asoschi belgilaydi.
            del self.fields["capabilities"]

    @property
    def can_set_capabilities(self):
        return "capabilities" in self.fields

    def grouped_capabilities(self):
        if not self.can_set_capabilities:
            return []
        field = self["capabilities"]
        by_value = {w.data["value"]: w for w in field}
        return [(title, [by_value[c] for c in caps if c in by_value]) for title, caps in CAPABILITY_GROUPS]

    def apply_capabilities(self, user):
        """Gives the saved employee a personal role and, for the founder, the ticked functions."""
        if user.is_owner:
            return
        user.personal_role()
        if self.can_set_capabilities:
            user.set_capabilities(self.cleaned_data.get("capabilities") or [])


class ProfileForm(StyledFormMixin, forms.ModelForm):
    """Fields an employee may change about themselves. No security fields."""

    skills = CommaListField(label="Ko'nikmalar", required=False)
    muted_notifications = forms.MultipleChoiceField(
        label="Qaysi bildirishnomalarni olmaslik", choices=Notification.Kind.choices,
        required=False, widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone", "telegram", "skills", "muted_notifications"]
        labels = {"first_name": "Ism", "last_name": "Familiya", "email": "Elektron pochta"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hints = {"first_name": ("Ismingiz", "given-name"), "last_name": ("Familiyangiz", "family-name"),
                 "email": ("nom@example.com", "email"), "phone": ("+998 90 123 45 67", "tel"),
                 "telegram": ("@username", "off"), "skills": ("Masalan: dizayn, Python", "off")}
        for name, (placeholder, autocomplete) in hints.items():
            self.fields[name].widget.attrs.update(placeholder=placeholder, autocomplete=autocomplete)
        self.fields["phone"].widget.input_type = "tel"
        self.fields["skills"].help_text = "Vergul bilan ajrating."


class ProfilePhotoForm(forms.ModelForm):
    """A person's own photo; the image itself is checked, not only its name."""

    class Meta:
        model = User
        fields = ["photo"]
        error_messages = {"photo": {
            "required": "Rasm tanlang.",
            "invalid_image": "Bu fayl rasm emas yoki buzilgan.",
            "invalid_extension": "Faqat JPG, PNG yoki WEBP rasm yuklang.",
        }}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["photo"].required = True


class RoleForm(StyledFormMixin, forms.ModelForm):
    capabilities = forms.MultipleChoiceField(
        label="Huquqlar", choices=Capability.choices, required=False, widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Role
        fields = ["name", "rank", "dashboard", "scope", "description", "capabilities"]

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        allowed = policies.grantable_capabilities(actor)
        self.fields["capabilities"].choices = [c for c in Capability.choices if c[0] in allowed and c[0] != "reports.view"]
        # Executive dashboards are configured by the owner only.
        if not actor.is_owner:
            self.fields["dashboard"].choices = [
                c for c in Role.Dashboard.choices if c[0] in (Role.Dashboard.MANAGEMENT, Role.Dashboard.EMPLOYEE)
            ]

    def clean_rank(self):
        rank = self.cleaned_data["rank"]
        if not self.actor.is_owner and rank <= self.actor.rank:
            raise forms.ValidationError("Daraja o'zingiznikidan past (raqami katta) bo'lishi kerak.")
        if rank == 0:
            raise forms.ValidationError("0-daraja faqat asoschi uchun.")
        return rank

    def clean_capabilities(self):
        caps = set(self.cleaned_data["capabilities"])
        if not caps <= self.actor.caps():
            raise forms.ValidationError("O'zingizda yo'q huquqni bera olmaysiz.")
        return sorted(caps)

    def grouped_capabilities(self):
        field = self["capabilities"]
        by_value = {w.data["value"]: w for w in field}
        return [(title, [by_value[c] for c in caps if c in by_value]) for title, caps in CAPABILITY_GROUPS]

    def clean_dashboard(self):
        value = self.cleaned_data['dashboard']
        if value == Role.Dashboard.COFOUNDER and self.instance.pk:
            count = User.objects.filter(Q(role_id=self.instance.pk) | Q(role__dashboard=value)).count()
            if count > 1:
                raise forms.ValidationError('Hammuassis lavozimiga faqat bitta hisob biriktirilishi mumkin.')
        return value


class DepartmentForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Department
        fields = ["name", "head"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["head"].queryset = User.objects.filter(status=User.Status.ACTIVE).select_related("role", "department")
        self.fields["name"].label = "Bo‘lim nomi"
        self.fields["name"].widget.attrs.update(placeholder="Masalan: Dizayn bo‘limi", autocomplete="off")
        self.fields["head"].label = "Bo‘lim rahbari"
        self.fields["head"].help_text = "Ixtiyoriy. Rahbar bo‘lim xodimlarini kuzatib boradi."
        self.fields["head"].people_picker = "single"
        self.fields["head"].with_responsibility = False
