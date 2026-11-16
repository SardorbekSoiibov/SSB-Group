from django.db import migrations


class Migration(migrations.Migration):
    dependencies=[('enterprise','0002_integrity'),('audit','0001_initial')]
    operations=[migrations.RunSQL(
        'CREATE TRIGGER immutable_audit_history BEFORE UPDATE OR DELETE ON audit_auditevent FOR EACH ROW EXECUTE FUNCTION ssb_immutable_row();',
        'DROP TRIGGER IF EXISTS immutable_audit_history ON audit_auditevent;'
    )]
