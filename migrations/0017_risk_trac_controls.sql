-- The Risk site (owner, 15 Nov 2026): a copy of TRAC's published list of controls, so the results page can show
-- which controls address a risk, and still works when TRAC is down. Every copy is kept; the newest is in use.
-- Which copy an assessment used is kept inside the assessment's result (controls_fetched_at), so no rating changes.

CREATE TABLE risk_trac_controls (
    id            bigserial PRIMARY KEY,
    fetched_at    timestamptz NOT NULL DEFAULT now(),
    published_at  text,
    controls      jsonb NOT NULL
);
COMMENT ON TABLE risk_trac_controls IS 'A copy of the list of controls TRAC publishes (owner, 15 Nov 2026). Never edited: a refresh is a new row, and the newest row is the copy in use.';
COMMENT ON COLUMN risk_trac_controls.fetched_at IS 'When the Risk site fetched this copy.';
COMMENT ON COLUMN risk_trac_controls.published_at IS 'The date TRAC says it published the list, as TRAC wrote it.';
COMMENT ON COLUMN risk_trac_controls.controls IS 'The controls: code, title, url and the risk IDs each addresses.';
