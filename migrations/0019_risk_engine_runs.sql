-- The Risk site, engine bridge (R8): every engine output file uploaded for a group, kept so the site's own rating
-- can be set beside the engine's. Never edited or removed; the newest run of a group is the one compared.

CREATE TABLE risk_engine_run (
    id         bigserial PRIMARY KEY,
    at         timestamptz NOT NULL DEFAULT now(),
    group_id   text NOT NULL,
    by         text NOT NULL,
    file_hash  text NOT NULL,
    parsed     jsonb NOT NULL
);
CREATE INDEX risk_engine_run_group ON risk_engine_run (group_id, id);
COMMENT ON TABLE risk_engine_run IS 'One engine output file uploaded for one group (Risk site, engine bridge). Never edited or removed.';
COMMENT ON COLUMN risk_engine_run.at IS 'When the file was uploaded.';
COMMENT ON COLUMN risk_engine_run.group_id IS 'The group the file was uploaded for, as named in config/risk_groups.json.';
COMMENT ON COLUMN risk_engine_run.by IS 'Who uploaded it.';
COMMENT ON COLUMN risk_engine_run.file_hash IS 'SHA-256 of the uploaded file, so the same file can be recognized.';
COMMENT ON COLUMN risk_engine_run.parsed IS 'What the site read from the file: schema version, active drivers, scope, each risk''s engine likelihood, impact and applicable, and any problems noted while reading.';
