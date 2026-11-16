# The one way to edit things (15 Nov 2026)

Every list a person edits on the TRUST and Risk sites works the same way. It is built once, in
`backend/trust/editable.py` (the rules) and `frontend/shared/editable.js` (the screen). A new list is a short
description in `LISTS`, not a new screen.

## What every list has
- A table of its entries, with a search box when the list is long.
- Add, edit and retire. Nothing is ever deleted: a retired entry is greyed, stays in the history, and can be restored.
- A reason on every change. The site refuses to save without one, and while TRUST runs open it needs a typed name.
- A history of every change, for everyone who can see the page: who, when, old value, new value, why.
- "See what would move" before saving, where a change can move a rating: each group's newest assessment is rated
  again with the proposed values, and every rating that would change is listed, old and new. Saved assessments
  never change. A group's next Submit uses the new values.
- A download of the current list (CSV or JSON), with retired entries marked.

## How a list is kept
Every change is one row in the `list_change` table (migration 0016), never edited or removed. The entries of a list
now are worked out from the rows, oldest first.
- A list that can grow (questions, building blocks) is read from its file **once**. The first save writes one
  "load" row holding every entry from the file. After that the site is the source, and the file is not read again.
- A list with a fixed set of entries (rating settings, drivers answered from data) is the file's values with the site's
  changes on top, the way the scoring settings are kept.
- The Scoring settings page and its `setting_change` table are not touched.

## Who may save
Tech Risk, for every list, for now (`access.may_act_as_tech_risk`). While TRUST runs open (access not set up) everyone may, and a typed name is required. Everyone who can open the
site can read a list and its history.

## The lists
1. **Rating settings** (3 values from `config/risk_settings.json`). Moves ratings: yes. The rating rules don't change.
2. *(Retired 16 Nov 2026: Sign-off approvers. The team's own lead signs off, by `team_grouping`; nobody found means Tech Risk. Saved rows are ignored.)*
3. **Questions** (built from the risk files): driver it feeds, section, order, wording, kind of answer, and which answer
   (or which number) switches the driver on. Moves ratings: yes. A question is named by the field its driver's rule reads.
   The saved test and number are put on the driver's rule as data; how a rule is read is not changed.
4. **Each risk's building block** (`config/risk_building_blocks.json`): by risk or by domain. Display only.
5. **Drivers answered from data**: each calculation's settings and which driver code it answers (`data_drivers.py`).
6. *(Retired 16 Nov 2026: CTO view risk markers. The On and Off switches are gone: the markers follow the risk assessments by themselves. Rows saved earlier stay in the database, harmless and unread. No migration was needed.)*
7. **Risks each metric watches**: risk IDs per metric, drives the CTO markers and is read by the metric dictionary card.

## Where it plugs in
- `editable.with_saved_changes(loaded)` is called by the Risk site's `load_registers` and puts the saved settings,
  questions and building blocks on top of what the files said (`from_files` keeps what the files alone said).
- `groups.load()` gives TRUST's teams (and how they were grouped, which decides who signs off).
- The Risk site shows an Edit link in the top bar to Tech Risk (to everyone while TRUST runs open): `#/edit` and
  `#/edit/<list>`. TRUST can use the same screen by calling `editList(mount, slug, api)`.

## Risks each metric watches (16 Nov 2026)
One entry for every metric (Measured, In progress and Wanted). The metric's id and name are read-only; the one field is
the risk IDs it watches, separated by commas. Each ID must be one of the Risk site's current risks (the uploaded ones once
Tech Risk has uploaded the risk file); an unknown or repeated ID is refused with a plain reason. Metrics are not added
or retired here. A reason is needed on every change, and the history and download work as for every list.
- The metrics file's `card.risks` is the starting point. A saved change wins over it.
- One place reads it: `editable.metric_risks(metric_id)` (and `editable.all_metric_risks()`). The CTO view's Elevated risk
  markers (`risk/cto_markers.py`) and the metric dictionary card (`score_month.dictionary_card`) both use it.
- The dictionary card is built when the page's data is read (`publish.with_current_definitions`), not when a month is
  published, so a saved change shows on the card at once, with no re-publish.
- Display only: no score, status, threshold or watch list changes.
