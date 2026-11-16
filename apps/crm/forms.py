from apps.core.currencies import SUPPORTED_CURRENCIES
from django import forms

from apps.accounts.models import User
from apps.core.forms import CommaListField, DateInput, StyledFormMixin
from apps.core.models import WorkspaceSettings
from apps.core.uploads import IMAGE_VALIDATORS, validate_attachment

from . import policies
from .models import (Announcement, Client, Equipment, Inquiry, InquiryNote, Milestone, Partner, Project, Task,
                     TaskAssignment, TaskReview)


class EquipmentForm(StyledFormMixin, forms.ModelForm):
    holder = forms.ModelChoiceField(
        label="Mas’ul xodim", required=False, empty_label="— Hech kimga (omborda) —",
        queryset=User.objects.filter(is_active=True).order_by("first_name", "last_name", "username"),
        help_text="Biriktirilgan xodim jihozning butligi va to‘g‘ri ishlatilishiga javobgar bo‘ladi.",
    )

    class Meta:
        model = Equipment
        fields = ["name", "category", "inventory_number", "serial_number", "specs", "photo", "condition",
                  "location", "purchase_date", "price", "currency", "warranty_until", "note"]
        widgets = {
            "purchase_date": DateInput(), "warranty_until": DateInput(),
            "note": forms.Textarea(attrs={"rows": 3}),
            "photo": forms.FileInput(attrs={"accept": "image/png,image/jpeg,image/webp"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["holder"].label_from_instance = lambda u: f"{u.display_name} — {u.job_title or u.role or 'Xodim'}"
        if not self.instance.pk:
            # Yangi jihozda mas'ulni darhol tanlash mumkin; keyin esa "Biriktirish" tugmasi orqali.
            self.order_fields(["name", "category", "holder"])
        else:
            del self.fields["holder"]

    def clean_inventory_number(self):
        value = (self.cleaned_data.get("inventory_number") or "").strip().upper()
        if value and Equipment.objects.filter(inventory_number=value).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Bu inventar raqami boshqa jihozda bor.")
        return value


class EquipmentAssignForm(StyledFormMixin, forms.Form):
    holder = forms.ModelChoiceField(
        label="Kimga biriktiriladi", required=False, empty_label="— Qaytarib olish (omborga) —",
        queryset=User.objects.filter(is_active=True).order_by("first_name", "last_name", "username"),
    )
    condition = forms.ChoiceField(label="Topshirilayotgandagi ahvoli", choices=Equipment.Condition.choices)
    note = forms.CharField(label="Izoh", required=False, max_length=300,
                           widget=forms.TextInput(attrs={"placeholder": "Masalan: zaryadlovchi va sumka bilan"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["holder"].label_from_instance = lambda u: f"{u.display_name} — {u.job_title or u.role or 'Xodim'}"


class EquipmentStatusForm(StyledFormMixin, forms.Form):
    status = forms.ChoiceField(label="Holati", choices=Equipment.Status.choices)
    note = forms.CharField(label="Izoh", required=False, max_length=300)


class PartnerForm(forms.ModelForm):
    """Yangi hamkorda logo va shartnoma majburiy; tahrirlashda faqat almashtirish uchun."""

    class Meta:
        model = Partner
        fields = ["name", "logo", "contract", "signed_on", "website", "note", "show_on_badge"]
        widgets = {"signed_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["logo"].required = False
            self.fields["contract"].required = False
        self.fields["logo"].widget = forms.FileInput(attrs={"accept": "image/png,image/jpeg,image/webp"})
        self.fields["contract"].widget = forms.FileInput(attrs={"accept": ".pdf,.doc,.docx,image/png,image/jpeg,image/webp"})

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if logo and not getattr(logo, "_committed", False):
            from PIL import Image
            try:
                logo.seek(0)
                Image.open(logo).verify()
                logo.seek(0)
            except Exception:
                raise forms.ValidationError("Logotip fayli ochilmadi. PNG, JPG yoki WEBP rasm yuklang.")
        return logo

    def save(self, commit=True):
        item = super().save(commit=False)
        upload = self.files.get("contract")
        if upload:
            item.contract_name = upload.name[:200]
        if commit:
            item.save()
        return item


def active_users():
    return User.objects.filter(status=User.Status.ACTIVE).select_related("role", "department")


def posted_responsibilities(data):
    """{user id: text} from the people picker's responsibility_<id> inputs."""
    found = {}
    for key, value in data.items():
        name, _, pk = key.partition("_")
        if name == "responsibility" and pk.isdigit():
            found[int(pk)] = value.strip()[:200]
    return found


def people_field(field, mode, responsibility=False):
    """Renders the field with components/people_picker.html instead of a plain select."""
    field.people_picker = mode
    field.with_responsibility = responsibility


def picker_rows(bound):
    """Everything the assignment picker shows: photo, name, position and current workload."""
    value = bound.value()
    chosen = {str(item) for item in (value if isinstance(value, (list, tuple, set)) else [value]) if item not in (None, "")}
    people = list(bound.field.queryset)
    load = {}
    closed = [Project.Status.COMPLETED, Project.Status.ARCHIVED, Project.Status.CANCELLED]
    active = Project.objects.exclude(status__in=closed)
    for pk in active.filter(manager__in=people).values_list("manager", flat=True):
        load[pk] = load.get(pk, 0) + 1
    for pk in active.filter(members__in=people).values_list("members", flat=True):
        load[pk] = load.get(pk, 0) + 1
    texts = getattr(bound.form, "responsibility_values", {})
    rows = [{
        "person": person, "checked": str(person.pk) in chosen, "load": load.get(person.pk, 0),
        "position": person.job_title or ("Asoschi" if person.is_owner else "Xodim"), "responsibility": texts.get(person.pk, ""),
    } for person in people]
    return {"rows": rows, "positions": sorted({row["position"] for row in rows}), "none_chosen": not chosen}


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Validated against the workspace upload policy (extension + size)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        kwargs.setdefault("required", False)
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else ([data] if data else [])
        workspace = WorkspaceSettings.load()
        cleaned = []
        for f in files:
            f = super().clean(f, initial)
            validate_attachment(f, workspace)
            cleaned.append(f)
        if len(cleaned) > 10:
            raise forms.ValidationError("Bir martada 10 tadan ortiq fayl yuklab bo'lmaydi.")
        return cleaned


def team_responsibilities(form):
    """What the picker shows: the posted text after a failed save, otherwise what is stored."""
    if form.is_bound:
        return posted_responsibilities(form.data)
    if not form.instance.pk:
        return {}
    return dict(form.instance.assignments.values_list("user_id", "responsibility"))


class ProjectForm(StyledFormMixin, forms.ModelForm):
    currency = forms.ChoiceField(label="Valyuta", choices=SUPPORTED_CURRENCIES)
    files = MultipleFileField(label="Ma'lumot fayllari", help_text="Jamoa uchun namunalar va hujjatlar. Bir martada 10 tagacha.")

    class Meta:
        model = Project
        fields = [
            "name", "description", "objectives", "client", "cover", "manager", "members", "department",
            "start_date", "deadline", "priority", "budget", "currency", "internal_notes",
        ]
        widgets = {"start_date": DateInput(), "deadline": DateInput()}

    def __init__(self, *args, actor, can_assign=True, show_budget=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:self.initial.setdefault('currency',WorkspaceSettings.load().default_currency if WorkspaceSettings.load().default_currency in dict(SUPPORTED_CURRENCIES) else 'UZS')
        if self.instance.pk and self.instance.currency not in dict(SUPPORTED_CURRENCIES):
            self.fields['currency'] = forms.CharField(label='Valyuta (tarixiy)', disabled=True, initial=self.instance.currency)
        self.fields["manager"].queryset = active_users()
        self.fields["manager"].label = "Mas’ul xodim"
        self.fields["manager"].help_text = "Loyihani tayyorlab ishga tushiradigan xodim. Asoschi jarayonni nazorat qiladi."
        self.fields["members"].queryset = active_users()
        people_field(self.fields["manager"], "single")
        people_field(self.fields["members"], "multi", responsibility=True)
        self.responsibility_values = team_responsibilities(self)
        if not can_assign:
            del self.fields["members"]
            del self.fields["manager"]
        if not show_budget:
            del self.fields["budget"]
            del self.fields["currency"]

    SECTIONS = [
        ("Asosiy ma’lumot", "Loyiha nima va nimaga erishishi kerak.", ["name", "description", "objectives"]),
        ("Mas’ul xodim va jamoa", "Kim tayyorlab ishga tushiradi va kimlar yordam beradi.", ["manager", "members"]),
        ("Muddat va tartib", "Qachon boshlanadi, qachon tugaydi va qanchalik muhim.", ["start_date", "deadline", "priority", "department", "client"]),
        ("Qo‘shimcha", "Muqova, fayllar, byudjet va ichki izohlar.", ["cover", "files", "budget", "currency", "internal_notes"]),
    ]

    def sections(self):
        """The form split into clear groups; fields the actor may not use are simply absent."""
        result = []
        for title, hint, names in self.SECTIONS:
            fields = [self[name] for name in names if name in self.fields]
            if fields:
                result.append({"title": title, "hint": hint, "fields": fields})
        return result

    def clean(self):
        data = super().clean()
        if data.get("start_date") and data.get("deadline") and data["deadline"] < data["start_date"]:
            self.add_error("deadline", "Muddat boshlanish sanasidan oldin bo'lishi mumkin emas.")
        return data


class MembersForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Project
        fields = ["manager", "members"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["manager"].queryset = active_users()
        self.fields["manager"].label = "Mas’ul xodim"
        self.fields["manager"].help_text = "Loyihani tayyorlab ishga tushiradigan xodim. Asoschi jarayonni nazorat qiladi."
        self.fields["members"].queryset = active_users()
        people_field(self.fields["manager"], "single")
        people_field(self.fields["members"], "multi", responsibility=True)
        self.responsibility_values = team_responsibilities(self)


class MilestoneForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Milestone
        fields = ["title", "due_date"]
        widgets = {"due_date": DateInput()}


class TaskForm(StyledFormMixin, forms.ModelForm):
    collaborators = forms.ModelMultipleChoiceField(
        label="Hamkor ijrochilar", queryset=User.objects.none(), required=False,
        help_text="Mas'ul ijrochi bitta bo'ladi. Hamkorlar o'z qismini bajaradi, vazifa esa bir marta hisoblanadi.",
    )
    files = MultipleFileField(label="Ma'lumot fayllari", help_text="Ijrochi uchun namunalar va ko'rsatmalar.")

    class Meta:
        model = Task
        fields = [
            "project", "parent", "milestone", "title", "description", "acceptance_criteria",
            "assignee", "priority", "start_date", "deadline", "depends_on",
        ]
        widgets = {"start_date": DateInput(), "deadline": DateInput(), "depends_on": forms.SelectMultiple(attrs={"size": 4})}

    def __init__(self, *args, projects, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.anyone = actor is not None and policies.can_assign_anyone(actor)
        self.fields["project"].queryset = projects
        project = self.instance.project if self.instance.pk else None
        if project is None:
            pid = self.data.get("project") or self.initial.get("project")
            if pid:
                try:
                    project_id = self.fields["project"].to_python(pid).pk
                except forms.ValidationError:
                    project = None
                else:
                    project = projects.filter(pk=project_id).first()
        if self.instance.pk:
            self.fields["project"].disabled = True
        tasks = Task.objects.filter(project=project).exclude(pk=self.instance.pk) if project else Task.objects.none()
        self.fields["parent"].queryset = tasks.filter(parent__isnull=True)
        self.fields["depends_on"].queryset = tasks
        self.fields["milestone"].queryset = project.milestones.all() if project else Milestone.objects.none()
        team = project.team() if project else []
        people = active_users().filter(pk__in=[u.pk for u in team]) if project and not self.anyone else active_users()
        self.fields["assignee"].queryset = people
        self.fields["collaborators"].queryset = people
        if self.anyone:
            self.fields["assignee"].help_text = "Jamoada bo'lmagan xodim tanlansa, u loyihaga avtomatik qo'shiladi."
        elif project:
            self.fields["assignee"].help_text = "Faqat loyiha jamoasi a'zolari."
        people_field(self.fields["assignee"], "single")
        people_field(self.fields["collaborators"], "multi", responsibility=True)
        self.responsibility_values = {}
        if self.is_bound:
            self.responsibility_values = posted_responsibilities(self.data)
        elif self.instance.pk:
            rows = list(self.instance.assignments.values_list("user_id", "responsibility"))
            self.responsibility_values = dict(rows)
            self.initial["collaborators"] = [pk for pk, _ in rows]

    def clean(self):
        data = super().clean()
        project, parent = data.get("project"), data.get("parent")
        if parent and project and parent.project_id != project.pk:
            self.add_error("parent", "Asosiy vazifa shu loyihadan bo'lishi kerak.")
        if data.get("start_date") and data.get("deadline") and data["deadline"] < data["start_date"]:
            self.add_error("deadline", "Muddat boshlanish sanasidan oldin bo'lishi mumkin emas.")
        assignee = data.get("assignee")
        if assignee and project and not self.anyone and assignee not in project.team():
            self.add_error("assignee", "Ijrochi loyiha jamoasida bo'lishi kerak.")
        collaborators = [person for person in data.get("collaborators", []) if person != assignee]
        if collaborators and not assignee:
            self.add_error("assignee", "Hamkorlar bo'lsa, mas'ul ijrochini ham tanlang.")
        data["collaborators"] = collaborators
        return data


class CommentForm(StyledFormMixin, forms.Form):
    body = forms.CharField(label="Izoh", widget=forms.Textarea(attrs={"rows": 3}), max_length=5000)
    is_clarification = forms.BooleanField(label="Bu aniqlik kiritish so'rovi", required=False)


class ProjectCommentForm(StyledFormMixin, forms.Form):
    body = forms.CharField(label="Izoh", widget=forms.Textarea(attrs={"rows": 3}), max_length=5000)
    is_announcement = forms.BooleanField(label="Jamoaga e'lon sifatida yuborish", required=False)


class AttachmentForm(StyledFormMixin, forms.Form):
    files = MultipleFileField(label="Fayllar", required=True)


class SubmitForm(StyledFormMixin, forms.Form):
    note = forms.CharField(label="Nima qilindi", widget=forms.Textarea(attrs={"rows": 3}), required=False, max_length=5000)
    files = MultipleFileField(label="Natija fayllari")


class ReviewForm(StyledFormMixin, forms.Form):
    decision = forms.ChoiceField(label="Qaror", choices=TaskReview.Decision.choices, widget=forms.RadioSelect)
    comment = forms.CharField(label="Izoh", widget=forms.Textarea(attrs={"rows": 3}), required=False, max_length=5000)


class ClientForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Client
        fields = ["name", "company", "email", "phone", "telegram", "account_manager", "notes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account_manager"].queryset = active_users()


class InquiryUpdateForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Inquiry
        fields = ["stage", "assigned_to", "client", "follow_up_on", "source"]
        widgets = {"follow_up_on": DateInput()}

    def __init__(self, *args, can_assign=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = active_users()
        self.fields["stage"].choices = [c for c in Inquiry.Stage.choices if c[0] != Inquiry.Stage.CONVERTED]
        if self.instance.stage == Inquiry.Stage.CONVERTED:
            self.fields["stage"].disabled = True
            self.fields["stage"].choices = Inquiry.Stage.choices
        if not can_assign:
            del self.fields["assigned_to"]


class InquiryNoteForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = InquiryNote
        fields = ["body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 3})}


class MultipleImageInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    """Bir nechta rasm (soni cheklanmagan). Har biri alohida tekshiriladi: JPG/PNG/WebP, 8 MB gacha."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleImageInput(attrs={"accept": "image/jpeg,image/png,image/webp", "multiple": True}))
        kwargs.setdefault("validators", IMAGE_VALIDATORS)
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(item, initial) for item in data if item]
        return [single(data, initial)] if data else []


class AnnouncementForm(StyledFormMixin, forms.ModelForm):
    images = MultipleImageField(label="Rasmlar", required=False)
    telegram = forms.BooleanField(label="Telegram kanallarga ham yuborish", required=False)

    class Meta:
        model = Announcement
        fields = ["title", "body", "event_date", "registration_deadline", "location", "prize", "link_label", "link_url", "pinned"]
        widgets = {
            "title": forms.TextInput(attrs={
                "placeholder": "Masalan: AI Hackaton 2026",
                "autocomplete": "off",
            }),
            "body": forms.Textarea(attrs={
                "rows": 6,
                "placeholder": "Hackaton mavzusi, kimlar qatnasha oladi, jamoa tarkibi, shartlar…",
            }),
            "event_date": DateInput(),
            "registration_deadline": DateInput(),
            "location": forms.TextInput(attrs={"placeholder": "Masalan: IT Park, Toshkent yoki Onlayn", "autocomplete": "off"}),
            "prize": forms.TextInput(attrs={"placeholder": "Masalan: 10 000 000 so‘m", "autocomplete": "off"}),
            "link_label": forms.TextInput(attrs={"placeholder": "Masalan: Ro‘yxatdan o‘tish", "autocomplete": "off"}),
            "link_url": forms.URLInput(attrs={"placeholder": "https://…", "autocomplete": "off", "inputmode": "url"}),
        }
        help_texts = {
            "title": "Hackaton nomi — jamoa bir qarashda tushunsin.",
            "body": "Mavzu, shartlar va kerakli harakatni yozing.",
            "pinned": "Yoqilsa, e’lon ro‘yxatning yuqorisida turadi.",
        }

    def clean_registration_deadline(self):
        deadline = self.cleaned_data.get("registration_deadline")
        event = self.cleaned_data.get("event_date")
        if deadline and event and deadline > event:
            raise forms.ValidationError("Ro‘yxatdan o‘tish hackaton kunidan keyin tugashi mumkin emas.")
        return deadline

    def clean_link_url(self):
        url = (self.cleaned_data.get("link_url") or "").strip()
        if url and not url.lower().startswith(("http://", "https://")):
            raise forms.ValidationError("Havola http:// yoki https:// bilan boshlanishi kerak.")
        return url

    def clean(self):
        data = super().clean()
        if (data.get("link_label") or "").strip() and not data.get("link_url") and "link_url" not in self.errors:
            self.add_error("link_url", "Tugma uchun havola kiriting.")
        return data


class WorkspaceSettingsForm(StyledFormMixin, forms.ModelForm):
    default_currency = forms.ChoiceField(label="Asosiy valyuta", choices=SUPPORTED_CURRENCIES)
    allowed_extensions = CommaListField(label="Ruxsat etilgan fayl turlari")

    class Meta:
        model = WorkspaceSettings
        fields = ["company_name","default_currency","date_format","company_share_percent","archive_max_mb","upload_max_mb", "allowed_extensions", "reminder_days_before", "require_project_start_approval"]

    def clean_allowed_extensions(self):
        exts = [e.lower().lstrip(".") for e in self.cleaned_data["allowed_extensions"]]
        blocked = {"exe", "bat", "cmd", "sh", "js", "html", "htm", "php", "msi", "dll", "ps1"}
        bad = sorted(set(exts) & blocked)
        if bad:
            raise forms.ValidationError("Xavfli fayl turlariga ruxsat berib bo'lmaydi: " + ", ".join(bad))
        return exts
