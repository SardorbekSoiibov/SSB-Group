"""Financial report inputs. Invalid filters must never silently change the calculation."""
from django import forms
from django.utils import timezone
from apps.core.currencies import SUPPORTED_CURRENCIES

REPORTS = [
    ('daily', 'Kunlik tushum'), ('weekly', 'Haftalik tushum'), ('monthly', 'Oylik tushum'),
    ('annual', 'Yillik tushum'), ('expenses', 'Xarajatlar'), ('earnings', 'Xodim daromadi'),
    ('bonuses', 'Mukofotlar'), ('profitability', 'Loyiha rentabelligi'),
    ('outstanding', 'To‘lanmagan daromad'), ('performance', 'Xodim faoliyati'),
    ('departments', 'Bo‘limlar daromadi'), ('payouts', 'Haqiqiy xodim to‘lovlari'),
    ('profit', 'Kompaniya foydasi'),
]


class ReportFilters(forms.Form):
    report = forms.ChoiceField(label='Hisobot turi', choices=REPORTS)
    dan = forms.DateField(label='Boshlanish', input_formats=['%Y-%m-%d'], widget=forms.DateInput(attrs={'type':'date'}),
                          error_messages={'invalid':'Sana YYYY-MM-DD ko‘rinishida bo‘lishi kerak.'})
    gacha = forms.DateField(label='Tugash', input_formats=['%Y-%m-%d'], widget=forms.DateInput(attrs={'type':'date'}),
                            error_messages={'invalid':'Sana YYYY-MM-DD ko‘rinishida bo‘lishi kerak.'})
    currency = forms.ChoiceField(label='Valyuta', choices=SUPPORTED_CURRENCIES)
    export = forms.ChoiceField(choices=[('', 'Sahifa'), ('csv','CSV'), ('xlsx','Excel'), ('pdf','PDF')], required=False)

    def __init__(self, params, *, actor, currency):
        data = params.copy()
        today = timezone.localdate()
        for name, value in {'report':'monthly','dan':today.replace(day=1).isoformat(),
                            'gacha':today.isoformat(),'currency':currency}.items():
            if name not in data:
                data[name] = value
        super().__init__(data)
        for field in self.fields.values():
            field.error_messages['required'] = 'Bu maydonni to‘ldiring.'
            if isinstance(field, forms.ChoiceField):
                field.error_messages['invalid_choice'] = 'Ro‘yxatdagi qiymatlardan birini tanlang.'
        if not actor.has_cap('performance.view'):
            self.fields['report'].choices = [item for item in REPORTS if item[0] != 'performance']

    def clean(self):
        data = super().clean()
        if data.get('dan') and data.get('gacha') and data['dan'] > data['gacha'] and data.get('report') not in ['outstanding','profitability']:
            self.add_error('gacha', 'Tugash sanasi boshlanish sanasidan oldin bo‘lmasligi kerak.')
        return data
