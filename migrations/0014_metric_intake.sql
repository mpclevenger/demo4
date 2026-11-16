-- Metric intake (owner, 15 Nov 2026): a record for every metric a team wants on the scorecard, the standard layout
-- teams send their numbers in, and what was received. A metric starts as Wanted and counts in no score.
-- Nothing here is scored and nothing reaches the scorecard. Records are changed in place, but every change also
-- adds a row to metric_intake_history, which is never edited; every send is a row that is never edited.

CREATE SEQUENCE metric_intake_number;

CREATE TABLE metric_intake (
    code        text PRIMARY KEY,
    stage       text NOT NULL CHECK (stage IN ('Wanted', 'In progress', 'Measured')),
    fields      jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    created_by  text NOT NULL,
    changed_at  timestamptz NOT NULL DEFAULT now(),
    changed_by  text NOT NULL
);
COMMENT ON TABLE metric_intake IS 'One record per metric a team wants on the scorecard (MI-001, MI-002, ...), at one of three stages: Wanted, In progress, Measured. Tech Risk fills it in. It does not create a metric and changes no score.';
COMMENT ON COLUMN metric_intake.code IS 'The short ID, MI-001 and so on.';
COMMENT ON COLUMN metric_intake.stage IS 'Wanted (we want it and it is not there yet), In progress (agreed and being built) or Measured (set by hand by Tech Risk after the usual metric approval).';
COMMENT ON COLUMN metric_intake.fields IS 'The record''s details: name, what it tells leadership, building block, provider team, contact, system, and for In progress the data contract (what is counted, measured against, unit, direction, what ties a row to a team, shape, how often, how it arrives, service account, who approved and when).';
COMMENT ON COLUMN metric_intake.created_at IS 'When the record was first added.';
COMMENT ON COLUMN metric_intake.created_by IS 'Who added it.';
COMMENT ON COLUMN metric_intake.changed_at IS 'When the record last changed.';
COMMENT ON COLUMN metric_intake.changed_by IS 'Who last changed it.';

CREATE TABLE metric_intake_history (
    id      bigserial PRIMARY KEY,
    code    text NOT NULL,
    at      timestamptz NOT NULL DEFAULT now(),
    by      text NOT NULL,
    action  text NOT NULL,
    note    text NOT NULL DEFAULT '',
    before  jsonb,
    after   jsonb
);
CREATE INDEX metric_intake_history_code ON metric_intake_history (code, id);
COMMENT ON TABLE metric_intake_history IS 'Every change to every metric intake record: one row per change, never edited or removed.';
COMMENT ON COLUMN metric_intake_history.code IS 'The record changed (MI-001).';
COMMENT ON COLUMN metric_intake_history.at IS 'When the change was made.';
COMMENT ON COLUMN metric_intake_history.by IS 'Who made it: the signed-in person, or the name typed while TRUST runs open.';
COMMENT ON COLUMN metric_intake_history.action IS 'added, changed or moved.';
COMMENT ON COLUMN metric_intake_history.note IS 'Why, in the words of the person who made the change (optional).';
COMMENT ON COLUMN metric_intake_history.before IS 'The fields that changed, as they were (and the stage, for a move).';
COMMENT ON COLUMN metric_intake_history.after IS 'The fields that changed, as they are now (and the stage, for a move).';

CREATE TABLE metric_value_send (
    id               bigserial PRIMARY KEY,
    intake_id        text NOT NULL,
    month            text NOT NULL,
    shape            text NOT NULL CHECK (shape IN ('totals', 'items')),
    at               timestamptz NOT NULL DEFAULT now(),
    by               text NOT NULL,
    kept_count       integer NOT NULL,
    set_aside_count  integer NOT NULL,
    rows_kept        jsonb NOT NULL,
    rows_set_aside   jsonb NOT NULL,
    totals           jsonb NOT NULL
);
CREATE INDEX metric_value_send_record ON metric_value_send (intake_id, month, id);
COMMENT ON TABLE metric_value_send IS 'Every send of numbers for a metric intake record, in the standard layout. The newest send for a record and month is the one shown; earlier ones are kept. Nothing here is scored.';
COMMENT ON COLUMN metric_value_send.intake_id IS 'Which record the numbers are for (MI-001).';
COMMENT ON COLUMN metric_value_send.month IS 'The month the numbers count for (YYYY-MM).';
COMMENT ON COLUMN metric_value_send.shape IS 'totals (one row per team) or items (one row per item).';
COMMENT ON COLUMN metric_value_send.at IS 'When the numbers were received.';
COMMENT ON COLUMN metric_value_send.by IS 'Who sent them: the service account, or the person while TRUST runs open.';
COMMENT ON COLUMN metric_value_send.kept_count IS 'How many rows passed the checks.';
COMMENT ON COLUMN metric_value_send.set_aside_count IS 'How many rows failed a check and were set aside.';
COMMENT ON COLUMN metric_value_send.rows_kept IS 'The rows that passed the checks.';
COMMENT ON COLUMN metric_value_send.rows_set_aside IS 'The rows that failed, each with its position in the send, the row as sent and the reason.';
COMMENT ON COLUMN metric_value_send.totals IS 'The count and total per team: as sent (Totals) or worked out from the items (Items).';
