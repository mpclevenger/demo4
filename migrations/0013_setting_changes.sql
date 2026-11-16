-- Tolerance thresholds and caps edited on the site (owner, 15 Nov 2026). Tech Risk changes them on the
-- Scoring settings page; every change is one row here and is never edited or removed. The newest row for
-- a setting is its value in use; a setting with no row uses the value in config/thresholds.json.

CREATE TABLE setting_change (
    id      bigserial PRIMARY KEY,
    at      timestamptz NOT NULL DEFAULT now(),
    by      text NOT NULL,
    path    text NOT NULL,
    before  jsonb,
    after   jsonb,
    reason  text NOT NULL
);
CREATE INDEX setting_change_path ON setting_change (path, id);
COMMENT ON TABLE setting_change IS 'The audit trail of every tolerance threshold and cap changed on the site: one row per setting per change, never edited. The newest row for a setting is the value in use.';
COMMENT ON COLUMN setting_change.at IS 'When the change was saved.';
COMMENT ON COLUMN setting_change.by IS 'Who saved it: the signed-in person, or the name typed while TRUST runs open.';
COMMENT ON COLUMN setting_change.path IS 'Which setting, as it is named in config/thresholds.json: caps.red_metric_block, metrics.TE-02.green, min_families_for_threshold.';
COMMENT ON COLUMN setting_change.before IS 'The value in use before the change.';
COMMENT ON COLUMN setting_change.after IS 'The value from this change on. Empty means the setting has no value of its own (a metric''s own Amber band minimum, for example).';
COMMENT ON COLUMN setting_change.reason IS 'Why, in the words of the person who saved it.';
