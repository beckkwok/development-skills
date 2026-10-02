-- E2E fixture rollback (test only).
DROP INDEX IF EXISTS idx_widgets_status;
ALTER TABLE widgets DROP COLUMN IF EXISTS status;
