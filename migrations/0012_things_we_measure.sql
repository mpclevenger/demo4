-- The things we measure and how they connect (owner, 15 Nov 2026): the first layer of the shared core that
-- the scorecard and the risk assessment both read. Written by every mapping run, for its own month only,
-- so every month still stands alone and a locked month (which refuses mapping) keeps its rows unchanged.

CREATE TABLE thing (
    month   text NOT NULL CHECK (month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    kind    text NOT NULL CHECK (kind IN ('person', 'team', 'application', 'itdr_application', 'repository')),
    key     text NOT NULL,
    name    text NOT NULL,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (month, kind, key)
);
COMMENT ON TABLE thing IS 'The people, teams, applications and repositories found in a month''s files. One row per thing per month, replaced whenever that month is mapped again.';
COMMENT ON COLUMN thing.month IS 'YYYY-MM the thing was found in.';
COMMENT ON COLUMN thing.kind IS 'person, team, application (app inventory), itdr_application (ITDR application file) or repository (GitHub).';
COMMENT ON COLUMN thing.key IS 'Its own reference: a person''s SAM_ACCOUNT, an app ID, an ITDR Ref, a repo''s full name. A team''s key starts with what kind of team it is: family:, department:, l3: or l4:.';
COMMENT ON COLUMN thing.name IS 'The name people read.';
COMMENT ON COLUMN thing.details IS 'A few facts about the thing (a person''s email and reporting level, an application''s status, a repository''s activity). Never the full source row.';

CREATE TABLE thing_link (
    month     text NOT NULL CHECK (month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    from_kind text NOT NULL,
    from_key  text NOT NULL,
    relation  text NOT NULL CHECK (relation IN ('reports_to', 'member_of', 'placed_with', 'owned_by', 'serves', 'same_as')),
    to_kind   text NOT NULL,
    to_key    text NOT NULL,
    how       text NOT NULL,
    score     numeric,
    PRIMARY KEY (month, from_kind, from_key, relation, to_kind, to_key)
);
CREATE INDEX thing_link_to ON thing_link (month, to_kind, to_key);
COMMENT ON TABLE thing_link IS 'How the month''s things connect, and how each connection was made. One row per connection per month, replaced whenever that month is mapped again.';
COMMENT ON COLUMN thing_link.relation IS 'reports_to (person to their manager), member_of (person to a team), placed_with (application or repository to a product family), owned_by (application or repository to a person), serves (repository to an application), same_as (ITDR application to an app inventory application).';
COMMENT ON COLUMN thing_link.how IS 'How the connection was made, in plain words: the HR reporting line, the repo owner, the app inventory, a close name match, an approved claim.';
COMMENT ON COLUMN thing_link.score IS 'For a connection made by a close name match: how close (0 to 1). Empty otherwise.';
