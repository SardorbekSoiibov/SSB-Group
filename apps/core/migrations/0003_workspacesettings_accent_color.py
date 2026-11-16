import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_workspacesettings_archive_max_mb_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='workspacesettings',
            name='accent_color',
            field=models.CharField(
                default='#007aff', max_length=7,
                help_text='Butun kompaniya uchun bitta. Faqat direktor (Asoschi) o‘zgartira oladi.',
                validators=[django.core.validators.RegexValidator('^#[0-9a-f]{6}$', 'Rang #RRGGBB ko‘rinishida bo‘lishi kerak.')],
                verbose_name='Boshqaruv paneli asosiy rangi',
            ),
        ),
    ]
