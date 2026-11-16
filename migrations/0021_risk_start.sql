-- The Risk site (owner, 16 Nov 2026): starting an assessment. A team's lead (or anyone who may answer for it) presses
-- "Start" and the site keeps who and when, so the "Continue an assessment" table can say when it was started and by
-- whom. One row per start. Rows are never edited or removed. An assessment is open from the newest start until the
-- team's next Submit.

CREATE TABLE risk_start (
    id          bigserial PRIMARY KEY,
    at          timestamptz NOT NULL DEFAULT now(),
    group_id    text NOT NULL,
    by          text NOT NULL
);
CREATE INDEX risk_start_group ON risk_start (group_id, id);
COMMENT ON TABLE risk_start IS 'Each time someone started a new assessment for a team (owner, 16 Nov 2026). Never edited or removed.';
COMMENT ON COLUMN risk_start.group_id IS 'The team (a TRUST team id) the assessment was started for.';
COMMENT ON COLUMN risk_start.by IS 'Who pressed Start: the signed-in person, or the name typed while TRUST runs open.';
