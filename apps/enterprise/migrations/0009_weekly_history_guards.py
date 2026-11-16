from django.db import migrations


SQL = """
CREATE FUNCTION ssb_weekly_history_guard() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
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
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER weekly_week_history BEFORE UPDATE OR DELETE ON enterprise_evaluationweek FOR EACH ROW EXECUTE FUNCTION ssb_weekly_history_guard();
CREATE TRIGGER weekly_evaluation_history BEFORE INSERT OR UPDATE OR DELETE ON enterprise_weeklyevaluation FOR EACH ROW EXECUTE FUNCTION ssb_weekly_history_guard();
CREATE TRIGGER weekly_reward_history BEFORE UPDATE OR DELETE ON enterprise_weeklyreward FOR EACH ROW EXECUTE FUNCTION ssb_weekly_history_guard();
"""

REVERSE = """
DROP TRIGGER IF EXISTS weekly_reward_history ON enterprise_weeklyreward;
DROP TRIGGER IF EXISTS weekly_evaluation_history ON enterprise_weeklyevaluation;
DROP TRIGGER IF EXISTS weekly_week_history ON enterprise_evaluationweek;
DROP FUNCTION IF EXISTS ssb_weekly_history_guard();
"""


class Migration(migrations.Migration):
    dependencies = [('enterprise', '0008_unified_weekly_performance')]
    operations = [migrations.RunSQL(SQL, REVERSE)]
