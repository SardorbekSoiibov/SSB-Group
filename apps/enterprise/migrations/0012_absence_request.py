import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('enterprise', '0011_payouts'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AbsenceRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_from', models.DateField(verbose_name='Qaysi kundan')),
                ('date_to', models.DateField(verbose_name='Qaysi kungacha')),
                ('reason', models.TextField(verbose_name='Sabab')),
                ('status', models.CharField(choices=[('pending', 'Ko‘rib chiqilmoqda'), ('approved', 'Tasdiqlandi'), ('rejected', 'Rad etildi')], db_index=True, default='pending', max_length=10)),
                ('decision_note', models.TextField(blank=True)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('decided_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='absence_requests', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddConstraint(
            model_name='absencerequest',
            constraint=models.CheckConstraint(condition=models.Q(('date_to__gte', models.F('date_from'))), name='enterprise_absence_range'),
        ),
    ]
