-- The Risk site (owner, 15 Nov 2026): the saved answers to a group's questionnaire, and each assessment made from
-- them. Neither is ever edited or removed. A changed answer is a new row, and the newest row of a question is the
-- answer in use. Every Submit is a new assessment; all of them are kept.

CREATE TABLE risk_answer (
    id              bigserial PRIMARY KEY,
    at              timestamptz NOT NULL DEFAULT now(),
    group_id        text NOT NULL,
    question        text NOT NULL,
    answer          text NOT NULL,
    by              text NOT NULL,
    from_tech_risk  boolean NOT NULL DEFAULT false
);
CREATE INDEX risk_answer_group ON risk_answer (group_id, id);
COMMENT ON TABLE risk_answer IS 'One saved answer to one question for one group (owner, 15 Nov 2026). Never edited: a changed answer is a new row, and the newest row of a question is the answer in use.';
COMMENT ON COLUMN risk_answer.at IS 'When the answer was saved.';
COMMENT ON COLUMN risk_answer.group_id IS 'The group the form belongs to, as named in config/risk_groups.json.';
COMMENT ON COLUMN risk_answer.question IS 'The question, by the name its driver rule reads (RD01, RD14_pct).';
COMMENT ON COLUMN risk_answer.answer IS 'yes or no, or the number as typed. Empty means the answer was cleared.';
COMMENT ON COLUMN risk_answer.by IS 'Who saved it: the signed-in person, or the name typed while TRUST runs open.';
COMMENT ON COLUMN risk_answer.from_tech_risk IS 'True when a signed-in Tech Risk person saved it, so the form can say "from Tech Risk".';

CREATE TABLE risk_assessment (
    id        bigserial PRIMARY KEY,
    at        timestamptz NOT NULL DEFAULT now(),
    group_id  text NOT NULL,
    by        text NOT NULL,
    result    jsonb NOT NULL
);
CREATE INDEX risk_assessment_group ON risk_assessment (group_id, id);
COMMENT ON TABLE risk_assessment IS 'One assessment of a group, made when its form was submitted (owner, 15 Nov 2026). Kept forever; a later Submit makes a new one, and the trend compares the two.';
COMMENT ON COLUMN risk_assessment.at IS 'When the form was submitted.';
COMMENT ON COLUMN risk_assessment.group_id IS 'The group assessed, as named in config/risk_groups.json.';
COMMENT ON COLUMN risk_assessment.by IS 'Who submitted it.';
COMMENT ON COLUMN risk_assessment.result IS 'The answers used, the rating settings used, which drivers were on, off or not known, and each risk''s rating with the steps that led to it and its trend since the previous assessment.';
