from django.db import migrations

ALLOW = """IF current_setting('ssb.authorized_erase', true) = 'on' THEN
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;
"""

GUARD = """  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Weekly performance history cannot be deleted';
  END IF;
  IF TG_TABLE_NAME = 'enterprise_evaluationweek' THEN
    IF OLD.published_at IS NOT NULL OR NEW.starts_on IS DISTINCT FROM OLD.starts_on
       OR NEW.weights IS DISTINCT FROM OLD.weights OR NEW.created_by_id IS DISTINCT FROM OLD.created_by_id THEN
      RAISE EXCEPTION 'Weekly cohort and published ranking are immutable';
    END IF;
    IF NEW.published_at IS NOT NULL AND (NOT EXISTS (SELECT 1 FROM enterprise_weeklyevaluation WHERE week_id=OLD.id)
       OR EXISTS (SELECT 1 FROM enterprise_weeklyevaluation WHERE week_id=OLD.id AND status <> 'approved')) THEN
      RAISE EXCEPTION 'Every evaluation must be approved';
    END IF;
  ELSIF TG_TABLE_NAME = 'enterprise_weeklyevaluation' THEN
    IF TG_OP = 'INSERT' THEN
      IF EXISTS (SELECT 1 FROM enterprise_evaluationweek WHERE id=NEW.week_id AND published_at IS NOT NULL) THEN
        RAISE EXCEPTION 'Published cohort cannot be extended';
      END IF;
      RETURN NEW;
    END IF;
    IF OLD.status = 'approved' OR NEW.employee_id IS DISTINCT FROM OLD.employee_id OR NEW.week_id IS DISTINCT FROM OLD.week_id
       OR NEW.original_score IS DISTINCT FROM OLD.original_score OR NEW.original_criteria IS DISTINCT FROM OLD.original_criteria
       OR NEW.evidence IS DISTINCT FROM OLD.evidence OR NEW.analysis IS DISTINCT FROM OLD.analysis OR NEW.source IS DISTINCT FROM OLD.source
       OR EXISTS (SELECT 1 FROM enterprise_evaluationweek WHERE id=OLD.week_id AND published_at IS NOT NULL) THEN
      RAISE EXCEPTION 'Original evidence and approved evaluation are immutable';
    END IF;
  ELSIF TG_TABLE_NAME = 'enterprise_weeklyreward' AND OLD.status <> 'draft' THEN
    IF NOT (OLD.status = 'approved' AND NEW.status = 'issued' AND OLD.kind <> 'cash'
      AND NEW.week_id = OLD.week_id AND NEW.place = OLD.place AND NEW.kind = OLD.kind
      AND NEW.description = OLD.description AND NEW.value = OLD.value AND NEW.currency = OLD.currency
      AND NEW.employee_id IS NOT DISTINCT FROM OLD.employee_id AND NEW.operation_id IS NOT DISTINCT FROM OLD.operation_id
      AND NEW.idempotency_key = OLD.idempotency_key) THEN
      RAISE EXCEPTION 'Approved reward intent is immutable';
    END IF;
  END IF;
  RETURN NEW;
"""


def guard(body):
    return f'CREATE OR REPLACE FUNCTION ssb_weekly_history_guard() RETURNS trigger AS $$\nBEGIN\n{body}END;\n$$ LANGUAGE plpgsql;'


class Migration(migrations.Migration):
    """The weekly guard was added after 0006 without its erase switch, so erasing an evaluated employee was refused."""
    dependencies = [('enterprise', '0009_weekly_history_guards')]
    operations = [migrations.RunSQL(guard('  ' + ALLOW + GUARD), guard(GUARD))]
