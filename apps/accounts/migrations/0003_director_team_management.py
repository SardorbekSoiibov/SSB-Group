from django.db import migrations


def grant_team_management(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    for role in Role.objects.filter(name='Direktor'):
        caps = list(role.capabilities or [])
        if 'team.manage' not in caps:
            role.capabilities = [*caps, 'team.manage']
            role.save(update_fields=['capabilities'])


def revoke_team_management(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    for role in Role.objects.filter(name='Direktor'):
        role.capabilities = [cap for cap in (role.capabilities or []) if cap != 'team.manage']
        role.save(update_fields=['capabilities'])


class Migration(migrations.Migration):
    dependencies = [('accounts', '0002_remove_user_theme')]
    operations = [migrations.RunPython(grant_team_management, revoke_team_management)]
