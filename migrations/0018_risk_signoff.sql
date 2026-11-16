-- The Risk site (owner, 15 Nov 2026): sign-off. After a group submits, the L3 over the group's lead (or the person
-- they name, the group's approver, or Tech Risk) signs the assessment off or sends it back. Each decision, and each time
-- an L3 names or clears a delegate, is one row. Rows are never edited or removed; the newest decision on an assessment
-- is the one in use, and the newest delegate row of an L3 is that L3's delegate.

CREATE TABLE risk_signoff (
    id                bigserial PRIMARY KEY,
    at                timestamptz NOT NULL DEFAULT now(),
    kind              text NOT NULL CHECK (kind IN ('signoff', 'sendback', 'delegate')),
    group_id          text,
    assessment_id     bigint,
    by                text NOT NULL,
    signer_sam        text,
    note              text,
    l3_sam            text,
    delegate_sam      text,
    also_changed      boolean NOT NULL DEFAULT false,
    changed_answers   integer NOT NULL DEFAULT 0
);
CREATE INDEX risk_signoff_group ON risk_signoff (group_id, id);
COMMENT ON TABLE risk_signoff IS 'Sign-offs, send-backs and delegates of the Risk site (owner, 15 Nov 2026). Never edited or removed.';
COMMENT ON COLUMN risk_signoff.kind IS 'signoff or sendback (of the assessment named), or delegate (an L3 names or clears who signs off for them).';
COMMENT ON COLUMN risk_signoff.note IS 'The note with a sign-off, or the reason for a send-back.';
COMMENT ON COLUMN risk_signoff.l3_sam IS 'For a delegate row: the L3 who named the delegate. A delegate covers every group of that L3.';
COMMENT ON COLUMN risk_signoff.delegate_sam IS 'For a delegate row: the person named. Empty means the delegate was cleared.';
COMMENT ON COLUMN risk_signoff.also_changed IS 'True when the person signing off also changed answers in this assessment (a flag, never a block).';
COMMENT ON COLUMN risk_signoff.changed_answers IS 'How many answers that person saved for this assessment.';
