# 18 — The shared core (owner, 15 Nov 2026)

Status: **direction agreed by the owner, 15 Nov 2026. Layer 1 is built; the rest is planned.**

## Why

TRUST grew one piece at a time. Each month was one big saved result, each metric its own hand-written count, and results existed per product family only. The risk assessment needs the same data by other groups, and other teams are about to send their own metrics. So the middle is rebuilt as a shared core. Intake, data contracts and the screens stay.

## The four layers

| Layer | What it holds | Status |
|---|---|---|
| 1. Things we measure | People, teams, applications and repositories, and how they connect, with how each connection was made (`thing`, `thing_link`; `backend/trust/things.py`) | **Built** (migration 0012) |
| 2. Records | Each file's rows kept once, with only the key details, pointing at a person, application or repository | Planned |
| 3. Metric values | One table for every result: metric, group, month, both counts, the value. Counted by TRUST, or sent ready-made by another team | Planned |
| (screens) | The single page split into `frontend/shared/` and one file per page in `frontend/pages/` | **Built** (15 Nov 2026) |
| 4. Readers | The scorecard (tolerance thresholds, building blocks, TRUST) and the risk assessment (questions, drivers, risks, controls) | Scorecard exists; risk planned |

## Decisions (owner, 15 Nov 2026)

- **One codebase and one database, two deployments** (TRUST and the risk assessment).
- **The site is the golden source** for questions, risks, risk drivers, controls and the links between them. The engine's YAML files are uploaded once for the first load; after that they are edited on the site, and a download writes the files in the engine's shape. Every edit is logged (who, when, before, after).
- **Tolerance thresholds and caps are changed on the site by Tech Risk** (built: `backend/trust/tolerances.py`, table `setting_change`). `config/thresholds.json` holds the starting values; the page shows every score a change would move before it is saved, and each change is kept with who, when, before, after and why.
- **The engine is left out for now.** The risk assessment collects answers and writes the engine's input file; results used to come back through the risk assessments upload. Retired 16 Nov 2026: risk results come from the Risk site.
- **A question is retired, never deleted**, so earlier answers stay readable.
- **Other teams send data through a service account** that goes through the access add-on: the same files as the upload page, or ready-made metric values, with the same checks.
- **Only what TRUST uses is kept from each file** (unchanged; owner confirmed 15 Nov 2026), also for files sent through the API.
- **Views by product family, L3, L4 or department; each grouping gets its own prevailing medians** (L4s are compared with L4s).
- **The tests run before every deploy goes live** (`python manage.py release`).
- **The audit trail is kept 24 months** like everything else; the newest row of each setting always stays.
- **Old and new counts run side by side** while each metric moves to the new layers, and every difference is listed. This is a temporary check for the move.

## Layer 1 as built

Every mapping run finishes by writing the month's things and links from the mapped month (`things.save`). Nothing new is decided there: each row is what mapping placed. `tests/test_things.py` checks that placing by the links gives exactly the families the mapped month gives, for people, repositories, applications and ITDR applications.

- Teams have four kinds, told apart by the start of their key: `family:` (product family), `department:` (HR Department), `l3:` and `l4:` (the manager at that level and everyone under them). A person has a `member_of` link to each.
- Every month has its own rows, replaced when that month is mapped again and removed with the month by retention. There is no month lock (owner, 17 Nov 2026), so any month can be mapped again.
- Nothing reads these tables yet, so no page and no score has changed.
