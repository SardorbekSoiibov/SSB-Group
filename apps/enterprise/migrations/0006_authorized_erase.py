from django.db import migrations

ALLOW = """IF current_setting('ssb.authorized_erase', true) = 'on' THEN
   IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
   RETURN NEW;
 END IF;"""

FORWARD = f"""
CREATE OR REPLACE FUNCTION ssb_immutable_row() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 {ALLOW}
 RAISE EXCEPTION 'Immutable history: append a correction, never update or delete';
END $$;
CREATE OR REPLACE FUNCTION ssb_operation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 {ALLOW}
 IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Financial requests cannot be deleted'; END IF;
 IF OLD.status <> 'pending' OR
    (to_jsonb(NEW) - ARRAY['status','finalized_at']) <> (to_jsonb(OLD) - ARRAY['status','finalized_at']) THEN
   RAISE EXCEPTION 'Financial intent is immutable';
 END IF;
 IF NEW.status NOT IN ('approved','rejected') OR NEW.finalized_at IS NULL THEN RAISE EXCEPTION 'Invalid final state'; END IF;
 RETURN NEW;
END $$;
"""

BACKWARD = """
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
"""

# Projects already removed through the page keep no file; their leftover rows go too, as removal is now complete.
PURGE_REMOVED = """
SELECT set_config('ssb.authorized_erase', 'on', true);
WITH gone AS (DELETE FROM enterprise_archiveremoval RETURNING archive_id)
DELETE FROM enterprise_projectarchive WHERE id IN (SELECT archive_id FROM gone);
SELECT set_config('ssb.authorized_erase', 'off', true);
"""


class Migration(migrations.Migration):
    dependencies = [('enterprise', '0005_archive_removal')]
    operations = [
        migrations.RunSQL(FORWARD, BACKWARD),
        migrations.RunSQL(PURGE_REMOVED, migrations.RunSQL.noop),
        migrations.DeleteModel(name='ArchiveRemoval'),
    ]
