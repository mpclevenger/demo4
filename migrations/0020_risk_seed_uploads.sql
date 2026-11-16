-- The Risk site (owner, 16 Nov 2026): the risk files, driver rules and questionnaire that Tech Risk uploads to seed the
-- site. Every load keeps the file (who, when, hash, what was read). Risks and drivers read from the newest load of their
-- kind: after a load the site, not the files folder, is where they come from. Never edited or removed.

CREATE TABLE risk_seed_upload (
    id          bigserial PRIMARY KEY,
    at          timestamptz NOT NULL DEFAULT now(),
    by          text NOT NULL,
    kind        text NOT NULL,
    file_name   text NOT NULL,
    file_hash   text NOT NULL,
    read        jsonb NOT NULL,
    registers   jsonb NOT NULL
);
CREATE INDEX risk_seed_upload_kind ON risk_seed_upload (kind, id);
COMMENT ON TABLE risk_seed_upload IS 'One load of uploaded risk files, driver rules or questionnaire (Risk site, owner 16 Nov 2026). Never edited or removed.';
COMMENT ON COLUMN risk_seed_upload.by IS 'Who loaded it.';
COMMENT ON COLUMN risk_seed_upload.kind IS 'risks, drivers or questions.';
COMMENT ON COLUMN risk_seed_upload.file_name IS 'The uploaded file names, separated by commas.';
COMMENT ON COLUMN risk_seed_upload.file_hash IS 'SHA-256 of the uploaded files, so the same upload can be recognized.';
COMMENT ON COLUMN risk_seed_upload.read IS 'What was read: the items, the problems and the notes, in plain words.';
COMMENT ON COLUMN risk_seed_upload.registers IS 'What the site holds after this load: every risk (kind risks), every driver rule (drivers) or the questions loaded (questions).';
