-- The lists edited on the Risk site (owner, 15 Nov 2026): rating settings, risk groups, questions, each risk's
-- building block, and the drivers answered from data. Every add, edit, retire and restore is one row here and is
-- never edited or removed (a retired entry stays in the history). The entries of a list now are worked out from
-- its rows, oldest first. A list that can grow is read from its file once: that first load is one row.

CREATE TABLE list_change (
    id          bigserial PRIMARY KEY,
    at          timestamptz NOT NULL DEFAULT now(),
    by          text NOT NULL,
    list_name   text NOT NULL,
    entry_key   text NOT NULL,
    action      text NOT NULL,
    before      jsonb,
    after       jsonb,
    reason      text NOT NULL
);
CREATE INDEX list_change_list ON list_change (list_name, id);
COMMENT ON TABLE list_change IS 'The history of every editable list on the Risk site: one row per change to one entry, never edited or removed. The entries of a list now are worked out from its rows, oldest first.';
COMMENT ON COLUMN list_change.at IS 'When the change was saved.';
COMMENT ON COLUMN list_change.by IS 'Who saved it: the signed-in person, or the name typed while TRUST runs open.';
COMMENT ON COLUMN list_change.list_name IS 'Which list: rating-settings, risk-groups, questions, building-blocks or data-drivers.';
COMMENT ON COLUMN list_change.entry_key IS 'Which entry of the list (a group id, a question field such as RD12). * for the first load of the whole list.';
COMMENT ON COLUMN list_change.action IS 'load (the first load from the file), add, edit, retire or restore.';
COMMENT ON COLUMN list_change.before IS 'The entry before the change (its values and whether it was retired). Empty for an add and for the first load.';
COMMENT ON COLUMN list_change.after IS 'The entry after the change. For the first load, every entry read from the file.';
COMMENT ON COLUMN list_change.reason IS 'Why, in the words of the person who saved it.';
