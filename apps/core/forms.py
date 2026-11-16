from django import forms

INPUT = (
    "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink "
    "placeholder:text-mute focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/25"
)
CHECK = "h-4 w-4 rounded border-line text-cobalt focus:ring-cobalt"


class StyledFormMixin:
    """Applies the design-system classes to every widget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {"Email": "Elektron pochta", "Email address": "Elektron pochta", "Dashboard turi": "Bosh sahifa turi", "Hero sarlavhasi": "Asosiy sarlavha", "Hero matni": "Asosiy matn", "Footer matni": "Sahifa pastidagi matn", "Vizyon": "Kelajak maqsadi"}
        for field in self.fields.values():
            field.label = labels.get(field.label, field.label)
            w = field.widget
            if isinstance(w, (forms.CheckboxInput,)):
                w.attrs.setdefault("class", CHECK)
            elif isinstance(w, forms.CheckboxSelectMultiple):
                w.attrs.setdefault("class", CHECK)
            elif isinstance(w, forms.ClearableFileInput):
                w.attrs.setdefault("class", "block w-full text-sm text-mute file:mr-3 file:rounded-lg file:border-0 file:bg-cobalt/10 file:px-3 file:py-2 file:text-cobalt")
            else:
                w.attrs.setdefault("class", INPUT)
            if isinstance(w, forms.Textarea):
                w.attrs.setdefault("rows", 4)


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%d", **kwargs)


class DateTimeInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%dT%H:%M", **kwargs)


class CommaListField(forms.CharField):
    """Edits an ArrayField of short strings as a comma-separated line."""

    def prepare_value(self, value):
        if isinstance(value, (list, tuple)):
            return ", ".join(value)
        return value

    def to_python(self, value):
        value = super().to_python(value)
        return [v.strip() for v in value.split(",") if v.strip()]
