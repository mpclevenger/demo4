-- Comments only (owner, 16 Nov 2026): the Risk site's groups are TRUST's teams, and config/risk_groups.json is gone.
-- No table or column changes.

COMMENT ON COLUMN risk_answer.group_id IS 'The team the form belongs to: its id in TRUST (the product family id, or in level-3 mode the id made from the lead''s name).';
COMMENT ON COLUMN risk_assessment.group_id IS 'The team assessed: its id in TRUST.';
COMMENT ON COLUMN risk_engine_run.group_id IS 'The team the file was uploaded for: its id in TRUST.';
COMMENT ON COLUMN list_change.list_name IS 'Which list: rating-settings, sign-off-approvers, questions, building-blocks, data-drivers, cto-risk-markers or metric-risks.';
COMMENT ON COLUMN list_change.entry_key IS 'Which entry of the list (a team id, a question field such as RD12). * for the first load of the whole list.';
