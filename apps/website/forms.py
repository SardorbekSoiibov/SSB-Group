import time

from django import forms
from django.core import signing

from apps.core.forms import DateInput, StyledFormMixin
from apps.crm.models import Inquiry

from .models import (
    Highlight, PortfolioCategory, PortfolioImage, PortfolioProject, Service, SiteSettings,
    TeamMember, Technology, Testimonial,
)

PUBLIC_INPUT = "input"

MIN_FILL_SECONDS = 3
FORM_SALT = "inquiry-form"


class InquiryForm(forms.ModelForm):
    """Public project request. Spam protection: honeypot + signed render time + rate limit (in the view)."""

    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))
    issued = forms.CharField(widget=forms.HiddenInput)

    class Meta:
        model = Inquiry
        fields = ["name", "contact", "preferred_method", "service", "description", "budget"]
        labels = {
            "name": "Ismingiz",
            "contact": "Telefon, Telegram yoki elektron pochta",
            "preferred_method": "Qanday bog'lanaylik?",
            "service": "Qaysi xizmat kerak?",
            "description": "Loyiha haqida",
            "budget": "Taxminiy byudjet",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5, "placeholder": "Nima qurmoqchisiz, kimlar uchun va qachongacha?"}),
            "name": forms.TextInput(attrs={"autocomplete": "name"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = Service.objects.published()
        self.fields["service"].empty_label = "Hali aniq emas"
        self.fields["service"].widget = forms.RadioSelect(choices=self.fields["service"].choices)
        self.fields["budget"].required = False
        self.fields["budget"].widget = forms.RadioSelect(choices=self.fields["budget"].choices)
        self.fields["preferred_method"].choices = Inquiry.ContactMethod.choices
        self.fields["preferred_method"].widget = forms.RadioSelect(choices=Inquiry.ContactMethod.choices)
        if not self.is_bound:
            self.initial["issued"] = signing.dumps(time.time(), salt=FORM_SALT)
        for name, field in self.fields.items():
            if name not in ("website", "issued"):
                field.widget.attrs.setdefault("class", PUBLIC_INPUT)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if len(name) < 2:
            raise forms.ValidationError("Ismingizni kiriting.")
        return name

    def clean_contact(self):
        contact = self.cleaned_data["contact"].strip()
        if len(contact) < 5:
            raise forms.ValidationError("Siz bilan bog'lanish uchun telefon, Telegram yoki elektron pochta yozing.")
        return contact

    def clean_description(self):
        text = self.cleaned_data["description"].strip()
        if len(text) < 20:
            raise forms.ValidationError("Loyihani bir-ikki jumlada tasvirlab bering (kamida 20 belgi).")
        if text.lower().count("http") > 3:
            raise forms.ValidationError("Havolalar juda ko'p. Loyihani so'z bilan tasvirlab bering.")
        return text

    def is_spam(self):
        if self.data.get("website"):
            return True
        try:
            issued = signing.loads(self.data.get("issued", ""), salt=FORM_SALT, max_age=60 * 60 * 6)
        except signing.BadSignature:
            return True
        return time.time() - float(issued) < MIN_FILL_SECONDS


# ------------------------------------------------------------------ CMS forms
# Publication status is never edited through these forms; it changes only through
# the publish/unpublish/archive actions, which require cms.publish.


class SiteSettingsForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = "__all__"
        widgets = {
            "hero_text": forms.Textarea(attrs={"rows": 3}),
            "privacy_text": forms.Textarea(attrs={"rows": 10}),
        }


class ServiceForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Service
        fields = ["title", "summary", "description", "icon", "image", "benefits", "technologies", "order", "seo_description"]
        widgets = {"technologies": forms.CheckboxSelectMultiple, "description": forms.Textarea(attrs={"rows": 6})}


class PortfolioForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = PortfolioProject
        fields = [
            "title", "category", "cover", "summary", "description", "case_study", "services", "technologies",
            "client_name", "show_client", "project_state", "completed_on", "live_url", "featured", "order",
            "seo_description",
        ]
        widgets = {
            "completed_on": DateInput(),
            "technologies": forms.CheckboxSelectMultiple,
            "services": forms.CheckboxSelectMultiple,
            "description": forms.Textarea(attrs={"rows": 6}),
            "case_study": forms.Textarea(attrs={"rows": 8}),
        }


class PortfolioImageForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = PortfolioImage
        fields = ["image", "caption", "order"]


class TeamMemberForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = TeamMember
        fields = ["user", "name", "public_title", "bio", "photo", "skills", "linkedin", "github", "telegram", "website", "order"]


class TestimonialForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Testimonial
        fields = ["author", "author_title", "company", "quote", "project", "order"]


class HighlightForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Highlight
        fields = ["kind", "title", "body", "date_label", "order"]


class CategoryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = PortfolioCategory
        fields = ["name", "order"]


class TechnologyForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Technology
        fields = ["name"]
