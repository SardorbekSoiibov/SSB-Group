"""Har bir xodimga alohida huquqlar; vazifalar olib tashlandi.

* Eski lavozim rollari (Hammuassis, Direktor va hokazo) o'chiriladi.
* Asoschidan boshqa har bir xodimga shaxsiy rol beriladi — huquqlari bo'sh.
  Kabinetda nima ko'rinishini endi Asoschi xodim sahifasida belgilaydi.
* Barcha vazifalar (va ularning izohlari, fayl yozuvlari, tarixi) bazadan o'chiriladi.
"""
import django.contrib.postgres.fields
from django.db import migrations, models

PREFIX = "Xodim · "


def forwards(apps, schema_editor):
    Task = apps.get_model("crm", "Task")
    Role = apps.get_model("accounts", "Role")
    User = apps.get_model("accounts", "User")

    Task.objects.all().delete()

    for user in User.objects.select_related("role"):
        if user.is_superuser or (user.role_id and user.role.is_owner):
            continue
        name = (PREFIX + user.username)[:80]
        role, _ = Role.objects.get_or_create(name=name, defaults={
            "rank": 100, "dashboard": "employee", "scope": "company", "capabilities": [],
            "description": "Shaxsiy huquqlar", "is_active": True,
        })
        role.capabilities = []
        role.save(update_fields=["capabilities"])
        User.objects.filter(pk=user.pk).update(role=role)

    Role.objects.filter(is_owner=False).exclude(name__startswith=PREFIX).filter(users__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_capability_labels"),
        ("crm", "0004_task_project_workspace"),
    ]

    operations = [
        migrations.AlterField(
            model_name="role",
            name="capabilities",
            field=django.contrib.postgres.fields.ArrayField(base_field=models.CharField(choices=[('projects.own', "O'ziga biriktirilgan loyihalarni ko'rish va yuritish"), ('projects.views', "Loyihalar doskasi, taqvimi va bandligini ko'rish"), ('schedule.view', "Ish jadvalini ko'rish"), ('performance.self', "O'z baholash va reytingini ko'rish"), ('chat.use', 'Xodimlar chatidan foydalanish'), ('finance.balance', "Shaxsiy hisob (balans) ni ko'rish"), ('announcements.view', "E'lonlarni ko'rish"), ('archive.use', 'Xavfsiz arxivdan foydalanish'), ('dashboard.executive', "Kompaniya ko'rsatkichlarini ko'rish"), ('employees.view', "Xodimlar katalogini ko'rish"), ('employees.manage', "Xodimlarni qo'shish va boshqarish"), ('roles.manage', "Rollar, bo'limlar va huquqlarni boshqarish"), ('projects.view_all', "Barcha loyihalarni ko'rish"), ('projects.create', 'Loyiha yaratish'), ('projects.edit', 'Loyihalarni tahrirlash'), ('projects.assign', 'Loyihaga xodim biriktirish'), ('projects.approve', 'Loyihalarni tasdiqlash'), ('projects.archive', 'Loyihalarni arxivlash'), ('projects.budget', "Loyiha byudjetini ko'rish"), ('clients.view', "Mijozlarni ko'rish"), ('clients.manage', 'Mijozlarni boshqarish'), ('inquiries.manage', 'Murojaatlarni boshqarish'), ('finance.view', "Kompaniya moliyasini ko'rish"), ('finance.manage', 'Moliyaviy amal yaratish'), ('finance.approve', 'Moliyaviy amallarni tasdiqlash'), ('finance.distribute', 'Loyiha ulushlarini belgilash'), ('finance.rules', 'Moliyaviy tasdiqlash qoidalari'), ('archive.manage', 'Loyiha arxivlari va kodlari'), ('schedule.manage', 'Ish jadvalini boshqarish'), ('performance.view', "Jamoa faoliyatini ko'rish"), ('performance.manage', 'Faoliyatni baholash'), ('dashboard.customize', 'Dashboard vidjetlarini sozlash'), ('team.manage', 'Saytdagi jamoani boshqarish'), ('cms.edit', 'Sayt kontentini tahrirlash'), ('cms.publish', 'Sayt kontentini nashr qilish'), ('announcements.manage', "E'lonlar yuborish"), ('reports.view', "Hisobotlarni ko'rish"), ('settings.manage', "Tizim sozlamalarini o'zgartirish"), ('audit.view', "Audit jurnalini ko'rish")], max_length=40), blank=True, default=list, size=None, verbose_name="Huquqlar"),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
