from django.db import migrations

SQL = """
CREATE OR REPLACE FUNCTION ssb_immutable_row() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Immutable history: append a correction, never update or delete'; END $$;
CREATE OR REPLACE FUNCTION ssb_operation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Financial requests cannot be deleted'; END IF;
 IF OLD.status <> 'pending' OR
    (to_jsonb(NEW) - ARRAY['status','finalized_at']) <> (to_jsonb(OLD) - ARRAY['status','finalized_at']) THEN
   RAISE EXCEPTION 'Financial intent is immutable';
 END IF;
 IF NEW.status NOT IN ('approved','rejected') OR NEW.finalized_at IS NULL THEN RAISE EXCEPTION 'Invalid final state'; END IF;
 RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION ssb_ledger_posted() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM enterprise_financeoperation WHERE id = NEW.operation_id AND status = 'approved') THEN
   RAISE EXCEPTION 'Ledger entry requires an approved operation';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER operation_guard BEFORE UPDATE OR DELETE ON enterprise_financeoperation FOR EACH ROW EXECUTE FUNCTION ssb_operation_guard();
CREATE CONSTRAINT TRIGGER ledger_posted AFTER INSERT ON enterprise_ledgerentry DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ssb_ledger_posted();
CREATE OR REPLACE FUNCTION ssb_one_cofounder_user() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM pg_advisory_xact_lock(73910235);
 IF EXISTS(SELECT 1 FROM accounts_role WHERE id=NEW.role_id AND dashboard='cofounder') AND
 EXISTS(SELECT 1 FROM accounts_user u JOIN accounts_role r ON u.role_id=r.id WHERE r.dashboard='cofounder' AND u.id<>NEW.id) THEN
 RAISE EXCEPTION 'Only one Co-Founder account is allowed';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER one_cofounder BEFORE INSERT OR UPDATE OF role_id ON accounts_user FOR EACH ROW EXECUTE FUNCTION ssb_one_cofounder_user();
CREATE OR REPLACE FUNCTION ssb_cofounder_role_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM pg_advisory_xact_lock(73910235);
 IF NEW.is_owner AND NOT NEW.is_active THEN RAISE EXCEPTION 'Founder role cannot be disabled'; END IF;
 IF NEW.dashboard='cofounder' AND
 (SELECT count(*) FROM accounts_user u JOIN accounts_role r ON u.role_id=r.id WHERE r.dashboard='cofounder' OR u.role_id=NEW.id)>1 THEN
 RAISE EXCEPTION 'Role change would create multiple Co-Founders'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER cofounder_role_guard BEFORE UPDATE ON accounts_role FOR EACH ROW EXECUTE FUNCTION ssb_cofounder_role_guard();
"""
TABLES = ['ledgerentry','agreementsnapshot','approvaldecision','projectarchive','performancereview','reviewapproval']
for table in TABLES:
    SQL += f'CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON enterprise_{table} FOR EACH ROW EXECUTE FUNCTION ssb_immutable_row();\n'

REVERSE = """
DROP TRIGGER IF EXISTS cofounder_role_guard ON accounts_role;
DROP TRIGGER IF EXISTS one_cofounder ON accounts_user;
DROP FUNCTION IF EXISTS ssb_one_cofounder_user();
DROP FUNCTION IF EXISTS ssb_cofounder_role_guard();
DROP TRIGGER IF EXISTS operation_guard ON enterprise_financeoperation;
DROP TRIGGER IF EXISTS ledger_posted ON enterprise_ledgerentry;
DROP FUNCTION IF EXISTS ssb_operation_guard();
DROP FUNCTION IF EXISTS ssb_ledger_posted();
"""
for table in TABLES:
    REVERSE += f'DROP TRIGGER IF EXISTS immutable_history ON enterprise_{table};\n'
REVERSE += 'DROP FUNCTION IF EXISTS ssb_immutable_row();'


def grant_defaults(apps, schema_editor):
    Role = apps.get_model('accounts','Role')
    extra = ['finance.view','finance.manage','finance.approve','finance.distribute','archive.manage','schedule.manage','performance.view','performance.manage','dashboard.customize']
    for role in Role.objects.filter(name__in=['Direktor','Hammuassis','Bosh direktor']):
        role.capabilities=sorted(set(role.capabilities or []) | set(extra) | ({'employees.manage','roles.manage'} if role.name=='Direktor' else set()))
        role.save(update_fields=['capabilities'])


class Migration(migrations.Migration):
    dependencies=[('enterprise','0001_initial'),('accounts','0005_role_is_active_alter_role_capabilities')]
    operations=[migrations.RunSQL(SQL,REVERSE),migrations.RunPython(grant_defaults,migrations.RunPython.noop)]
