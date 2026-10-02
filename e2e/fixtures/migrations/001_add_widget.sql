-- E2E fixture migration (test only, never applied to a real database).
ALTER TABLE widgets ADD COLUMN status text DEFAULT 'active';
CREATE INDEX CONCURRENTLY idx_widgets_status ON widgets (status);
