# 21 — The Risk site, first slice (owner, 15 Nov 2026)

Status: **built, thin but real from end to end.** A person opens the Risk site, picks a group, answers the questionnaire, submits it, and sees that group's risks rated by the site itself. Rules of the rating: [19](19_risk_rating.md). Shared back end: [18](18_shared_core.md).

## What it does

1. The front page has three equal parts as tabs, each a table: Continue an assessment, Start a new assessment, View results (see "The front page" below). It shows no ratings or Elevated counts.
2. A group's questionnaire shows one section at a time, with Back and Next and a line such as "Section 2 of 4". Each question shows its driver code (RD01), and who last saved it and when. Every answer is saved the moment it is changed.
3. On the last section, Submit first lists any questions with no answer. You can go back and answer them, or submit anyway.
4. On Submit the site rates every risk for the group, from the saved answers and `config/risk_settings.json`, and keeps the result as an assessment.
5. The results page shows the count of Elevated risks, "Where to focus", then one row per risk: likelihood and impact (a word and four pips), an Elevated chip, the drivers that are on, and a closed "How this was rated" with the steps and the group's own numbers. Risks that don't apply are listed last. From the second assessment on, each risk shows better, worse or no change.

## Pages and routes

| Address | What |
|---|---|
| `/risk/` | The page (`frontend/risk/index.html`, its own `.js` and `.css`; it loads `/shared/site.css`, `/shared/shell.css` and `/shared/apps-menu.js`). Only `.js` and `.css` are served from the folder. |
| `#/` , `#/group/<id>`, `#/group/<id>/results` | Front page, questionnaire, results (inside the page) |
| `GET /api/risk/me` | TEST or not, who you are |
| `GET /api/risk/registers` | The risks, drivers and questions read from the risk files (read only) |
| `GET /api/risk/groups` | Groups you may see, with status |
| `GET /api/risk/groups/<id>` | The form, with each question's newest answer |
| `POST /api/risk/groups/<id>/answers` | Save one answer |
| `POST /api/risk/groups/<id>/submit` | Rate and keep an assessment (`confirm_unanswered: true` to submit with gaps) |
| `GET /api/risk/groups/<id>/assessment` | The newest assessment, or `?id=N`; lists the earlier ones |

Changes are POST requests with the header `X-TRUST: 1` and, while TRUST runs open, a typed name, as everywhere in TRUST.

## Where things are kept

Tables `risk_answer` and `risk_assessment` (migration 0015); without a database, `risk_answers.jsonl` and `risk_assessments.jsonl` in the store folder. Code: the end of `backend/trust/storage.py`.

- A saved answer holds: group, question, answer, who, when (and a mark when Tech Risk saved it). It is never edited: a changed answer is a new row and the newest stands.
- An assessment holds the answers used, the settings used, which drivers were on, off or not known, and each risk's rating, its steps and its trend. Every Submit makes a new one. Nothing is removed.
- Status is worked out, not stored: **Submitted** when the newest assessment was made from the answers the group has now; **Draft** when answers exist that haven't been submitted (or changed since); **Not started** otherwise.

## Where the code is

`backend/trust/risk/`: `questions.py` (the form and its answers), `groups.py` (groups, people, who may do what), `assess.py` (answers to ratings), `explain.py` (the steps in words), `blocks.py` (building block of each risk), `site.py` (routes). The rating itself stays in `drivers.py`, `expressions.py` and `rating.py`.

## The questions

The risk files don't yet carry question wording or sections, so the form is built from `driver_mapping.yaml`: one question for each questionnaire field; the text is the driver's rationale; yes/no when the rule is "is yes" or "is no", otherwise a number; the section is the domain of the first risk that lists the driver. **Yes always means the sentence is true for the group**, which is when the driver is on (for an "is no" driver the answer is turned around before the rule is read, in `questions.answers_by_field`). Drivers with no questionnaire field come from data: not available yet, shown as "not answered yet", never guessed.

## Groups and who may do what

**A Risk group is an L4 team, shown under its L3 team** (owner, 17 Nov 2026: questionnaires are filled in at the L4 level, metrics are available at L4, and an L3 team is its L4s together). An L4 team is one person at HR reporting level `l3_level` + 1 and everyone under them. Each L4 team fills in its own assessment and signs it off; the L3 team's page lists its L4 teams' results. The people are found by `linking.l4_teams` (the same chain logic as `linking.who_table`, so the TRUST L4 drill-down and the Risk site cut the firm the same way); `groups.py` only reads that from the mapped month. The group id is `<L3 team id>--<id made from the L4 team's name>` (stable and unique; `-<leader's SAM_ACCOUNT>` is added if two L4 teams under one L3 team share a name). The name is the leader's Supervisory Organization without "(Manager Name)", else the leader's name. The L3 team is the TRUST team the leader is placed with (the `team_grouping` setting decides whether that is a product family or a level-3 person's org). The L3 lead is in no L4 team, and an L3 team with no L4 team has no group. A leader whose L3 team is not mapped is listed under "Not yet mapped". Until TRUST holds L4 teams, the front page says so plainly. Nothing about a team is kept here: who signs off is worked out from the leader (see Sign-off). An assessment saved under an old group id (one that is no longer an L4 team, such as an old family id) is kept but not listed; opening it gives the plain "There is no such team" page, never an error.

An assessment saved under an old group id that is not a TRUST team (the made-up ones from before) is kept but no longer listed; its results page says "This group is no longer one of TRUST's teams."

- See: CTO and leadership, Tech Risk and auditors (everything); the L4 team's people; the managers above them; and the lead of the L3 team the group belongs to (read only, as lead of that L3 team).
- Answer: Tech Risk, the group's people, the managers above. Tech Risk's answers are marked "from Tech Risk" (only when TRUST is not running open).
- Submit: Tech Risk, the L4 leader, the managers above (this includes the L3 lead as a manager above, as before).
- While TRUST runs open, anyone can do everything and types their name.

Building blocks shown on each risk come from `config/risk_building_blocks.json` (display only; no TRUST score changes).

## Download in the engine's shape

`GET /api/risk/download` gives a .zip of the risks and drivers laid out like TRAC's `content/engine/` folder: `driver_mapping.yaml` and `risks/<risk id>.yaml` (one file per risk, with only the engine's own fields). Unzip it into TRAC's `content/engine/` (delete any old risk file the zip no longer has), run `check_engine`, then `sync_engine`. Anyone who may open the Risk site may download. The code is `backend/trust/risk/download.py`. A driver keeps the wording of its trigger from the drivers file while it still means the same rule.

## TRAC's controls on the results page

TRAC publishes `<TRAC_URL>/registers/controls.json` (each control: code, title, url, and `addresses`, the risk IDs it covers, empty until mapped). The Risk site fetches it with a short timeout, keeps the copy with the date it was fetched (table `risk_trac_controls`, migration 0017; a file in the store folder when there is no database), and always reads the kept copy, so the site works when TRAC is down. A first copy is fetched when there is none. Tech Risk can fetch a new one with `POST /api/risk/controls/refresh`. If TRAC can't be reached, the copy already kept stays in use. Each new assessment notes the fetched date of the copy in use (`controls_fetched_at` in its result); no rating changes. On the results page each risk card shows "Controls that address this risk" only when a control lists it. When no risk has a control, one line says it is Wanted. The copy's date shows small ("Controls as of 15 Nov 2026"). The code is `backend/trust/risk/trac_controls.py`.

## Rating with today's rules (owner, 17 Nov 2026)

A switch, `rate_with_current_rules`, in `config/risk_settings.json` (starts **true**; Tech Risk changes it at Edit, Rating settings, as Yes or No). It is for now, until more history has built up.

- **On:** every place that shows or uses a team's assessment works the result out again, from the answers kept with that assessment (the answers as they were at its Submit), with today's risks, driver rules, questions, rating settings and data drivers. It is the same function the Submit uses (`data_drivers.assess_with_data`). So a change to the questionnaire in November updates October's results without every team submitting again.
- **Off:** exactly as before. Every page shows the result kept at Submit.
- **Never changed:** the rows kept in `risk_assessment` are not edited or deleted. A new Submit still keeps its own result.
- **Where:** `backend/trust/risk/current_rules.py`. The Risk results page, the heat map, the team page's "Risks we have raised", the CTO markers, the sign-off box and the engine comparison read `current_rules.assessments()` instead of `storage.risk_assessments()`. The groups list and the form only need dates and answers, so they read the kept rows.
- **Speed:** the registers are loaded once and each assessment is worked out once for each page request (15 teams take well under a second).
- **On screen:** one short line where results show: "Rated with today's questions and rules (setting rate_with_current_rules is on)."
- **Sign-off:** a sign-off stays with the assessment it was given for. If today's rating is not the one kept at Submit, the sign-off box and the team page add "rated again with today's rules since sign-off". Nothing is blocked.

## Wanted next

- Answers pulled from data (RD22, RD44, RD63, RD64 and the like)
- The questions' own wording and sections from the real questionnaire, and editing questions, risks and drivers on the site
- The Rating settings page (Medium share, Elevated levels)
- Engine bridge: the side-by-side page (the download is done)
- Sign-off by the group's lead, and Sent back with a comment (status Signed off)
- Delegates who may submit for a lead
- Definitions from TRAC
- TRUST tie-in (family page reading these assessments)

## Risk heat map

Page `#/heat-map` on the Risk site (a "Risk heat map" link in the top bar; the old `#/matrix` sends people there). Owner's decision, 16 Nov 2026: each group's rating has its own page and is never combined with another's. Risks are raised so a treatment can be agreed, so inherent risk is not compared across teams. This page shows totals only. The code is `backend/trust/risk/matrix.py`, the route `GET /api/risk/matrix` in `matrix_routes.py`, the page `frontend/risk/risk-heatmap.js`. It reads each group's newest assessment and the one before it, and never rates anything again.

- **Who:** everyone who can open the Risk site, because it holds totals only.
- **Nothing per team:** the server adds everything up in Python. The answer has no group id, no group name and no per-group number (a test checks this), so nothing can be compared in the browser's developer tools.
- **Headline:** how many Elevated risks, of how many assessed risks (a risk counts once for each assessment it is in), and how many groups have assessed (a count only).
- **The grid:** 4 x 4, likelihood down (Critical at the top), impact across. Each box counts the risks in it across the newest assessment of every assessed group. Elevated boxes use the Elevated colors, from the rating settings (`elevated_likelihood_at_least`, `elevated_impact_at_least`). Picking a box lists its risks: name, id, building block, how many assessments, a plain description and example, and the controls TRAC lists for the risk (from the kept TRAC copy). Never which group.
- **Where to focus:** drawn only when something is Elevated. The Elevated risks, most serious first, each with its building block, how many assessments have it Elevated, its description and its controls. Worded as risks to agree a treatment for.
- **Since previous assessments:** totals only: "2 risks better, 1 worse", each assessment compared only with its own earlier one (`rating.trend()`).
- **Help to act:** a link to TRAC's guide "Choosing how to respond to a risk", drawn only when TRAC's address is set.
- **Building block filter:** narrows every total. There is no group filter.
- **Look:** boxes on one row carry comparable content and stretch to the same height. The picked box's risks get their own full-width row.
- A risk that applies but has no impact rating is never Elevated and is not placed on the grid. Elevated is shown as it was decided when the group submitted, so the totals agree with each group's results page; a later settings change shows from the next submit (the grid's shaded boxes follow the current settings).

## Engine bridge and side by side

The site rates the risks itself. The risk engine stays as a bridge so the two can be compared. The side-by-side page is the point: for each group it shows the engine's rating beside the site's, risk by risk, and lists every difference with the reason. The site's Critical and High must match the engine's rules exactly. Medium, Low and "does not apply" are new on the site, so they show as "Site only", not as differences.

**The engine's output (read).** One JSON per assessed group, `schema_version` "2.0": `active_drivers` (the RDxx that are on), `driver_details`, `assessment` (with `selected_scope`: business unit, processes), `risks` keyed by risk ID (`likelihood`, `impact`, `applicable`, `drivers` keyed RDxx with `name` and `commentary`) and `summary`. No real example exists yet, so `tools/test_risks/engine_output_example.json` is made up in that shape. Only `risks` is required. Level words can be any case. Anything missing or unreadable is noted in plain words on the page and the file still compares. A file that is not JSON, or has no `risks`, is refused with the reason.

**The engine's input (download).** `GET /api/risk/groups/<id>/engine-input` gives a JSON of the group's answers keyed by the driver rules' questionnaire fields (`RD01: true`, `RD12: 3`, `RD14_pct: 0.25`, as each rule reads it), plus the team's id and name. It uses the answers of the newest assessment, the one the comparison is made against. **Wanted: confirm this layout with the engine's owner.** The layout is built in one small function, `engine_input_layout` in `backend/trust/risk/engine_bridge.py`, so it is easy to change. The page says the same.

**The comparison.** Each upload is kept (who, when, file hash, what was read) in `risk_engine_run` (migration 0019; a file in the store folder when there is no database). The newest upload is compared with the group's newest site assessment, and the page says which one (its date). Per risk the result is:

- Same: both agree.
- Different: Critical or High on one side and something else on the other. The reason is in words: what each side says, then the site's own steps (read back from the assessment's explanation, not worked out again), then the drivers of that risk that are on in only one of the two.
- Site only: the site says Medium or Low (or does not apply) and the engine has no rating to match.
- Engine only: the engine rated a risk the site's risk files don't have.

Differences are listed first, then Engine only, the drivers that differ, Same, and Site only. A summary line gives the counts with units ("7 risks the same, 1 different, 2 site only"). Nothing here changes how a rating is worked out.

**Who and where.** Comparing with the engine is for Tech Risk only (owner, 16 Nov 2026), because it lists teams' results side by side: uploading, reading one team's comparison and the all-teams list. Anyone while TRUST runs open, with a typed name; header `X-TRUST: 1` and `by`. Routes: `GET/POST /api/risk/groups/<id>/engine-input|engine-output`, `GET /api/risk/groups/<id>/compare`, `GET /api/risk/compare` (every group with its last result). Pages: `#/compare` and `#/group/<id>/compare`; "Compare with the engine" links sit on the Groups page and each results page for Tech Risk. Code: `engine_bridge.py`, `engine_bridge_routes.py`, `frontend/risk/risk-compare.js`. Tests: `tests/test_risk_engine_bridge.py`.

## Sign-off

Owner's decisions, 15 Nov 2026; the rule for who signs changed on 16 Nov 2026 (whoever leads the unit being assessed signs off). After a group submits, the team's lead signs the assessment off, or sends it back. Code: `backend/trust/risk/signoff.py` and `signoff_routes.py`, the box in `frontend/risk/risk-signoff.js`, rows in `risk_signoff` (migration 0018).

- **Who signs off.** The L4 leader (owner, 17 Nov 2026): the one HR person at level `l3_level` + 1 the group is built around. Each L4 team signs off its own assessment. A leader may name a delegate. If no leader is found (not expected for an L4 team), Tech Risk signs off. Tech Risk may always sign off, and the page says all this in plain words ("Emery Rook leads this L4 team in HR, so Emery Rook signs this off."). The L3 lead does not sign off unless they are the delegate. The old "Sign-off approvers" editing list is retired; rows saved on it are ignored.
- **Delegate.** A lead (or Tech Risk) names a delegate with one SAM_ACCOUNT from HR, and can clear it. A delegate covers every team that lead leads, and may sign off and send back. Each change is a new row; the newest stands. Tech Risk naming one names it for every lead of the team.
- **Who answers and submits.** Unchanged: L3 and above can answer and submit. The lead and everyone under them answer; the lead submits; Tech Risk can answer and submit.
- **Status words.** Draft, Submitted, Signed off, Sent back. Sent back stays until the group submits again; the reason shows on the groups list and the results page. Changing an answer after a Submit or a sign-off makes the group a Draft again. Submitting again is a new assessment, as before; the earlier ones stay in the history.
- **Note.** Both a sign-off and a send-back need a short note (500 characters at most). For a send-back the note is the reason the team sees.
- **The flag.** If the person signing off also saved answers in the period that assessment covers (after the group's earlier assessment, up to this one), the sign-off is flagged: "Lee Moss also changed 2 answers in this assessment." It is shown on the results page and in the history. It never blocks a sign-off. A person is matched by SAM_ACCOUNT, or by the typed name while TRUST runs open.
- **Who sees it.** Everyone who can open the group sees who signed off, when, the flag and the note. A delegate who is not in the group's reporting line can open that group too, so they can see what they sign.
- **While TRUST runs open.** Anyone may sign off, with the name typed at the top. The page says so.
- **Routes.** `GET /api/risk/groups/<id>/signoff`; `POST .../signoff {"note"}`, `.../sendback {"reason"}`, `.../delegate {"delegate_sam"}` (all with `X-TRUST: 1`, and `by` while open). Only the newest assessment can be signed off, and only while it is Submitted.
- Nothing here changes how a risk is rated.

## A family's own risk results on its family page

Owner, 16 Nov 2026: risk results stay on each team's own page and are never compared across teams. TRUST draws them in one place only: the family's own page, in a section "Risks we have raised" (after the metrics table). Nothing about risks is on the CTO view, Firm position, the metric dictionary, any table of families or the watch list. The code is `backend/trust/risk/family_link.py`, the route `GET /api/risk/family/<family id>` (end of `site.py`), the section `inhPanel` in `frontend/pages/family.js`.

- **Which groups belong to an L3 team:** each L4 group carries its L3 team's id (`l3_id`, the family id on the page), so nothing is matched or guessed. The page lists every L4 group of the L3 team, in the site's order. An id that is not an L3 team, or an L3 team with no L4 team, has none.
- **What it shows:** for each L4 group of the L3 team, the Elevated risks of its newest assessment (as decided at submit; nothing is rated again), each line naming the L4 group, with its plain description, likelihood and impact, when it was assessed, the sign-off status, and a link to the group's results page. If nothing is Elevated, nothing is drawn. An L4 group not yet assessed is one plain line linking to the group on the Risk site.
- **Who sees it:** the family's own leads and members, Tech Risk, and the roles that see every family. Anyone else gets a refusal and nothing is drawn.
- **No score changes:** this only shows. The old "Inherent risk" table and the "Elevated for these families" line on metric cards (both from an uploaded CSV) are no longer drawn.

## Team results pages (owner, 17 Nov 2026)

One results page for every L4 team and every L3 team, open to **everyone who can open the Risk site**. This replaces the old "never compared" rule for these pages; the heat map is unchanged and still shows totals only. The code is `backend/trust/risk/team_results.py`; the routes are at the end of `site.py`.

**Decisions**
- An L4 team's page is its newest submitted assessment (read through `current_rules`, so the "rate with today's rules" switch still applies).
- An L3 team is its L4 teams **pooled**: a driver is on for the L3 team when it is on in any of its L4 teams' newest submitted assessments (a driver answered from data too). The L3 team is then rated once, as one team, with the same rating code (`rating.rate_group`). There is no second rating logic. An L3 team can therefore be rated higher than every one of its L4 teams.
- **No combined rating per risk.** A risk shows what the rating code already works out: likelihood, impact (the highest of financial, client and regulatory), the three impact dimensions, whether it is Elevated, and whether it applies.
- The pages show **what is on and why** (the answer and who gave it, or the TRUST figure and its month). They never show how drivers combine: no rating rules, thresholds, trigger text, or "switch off N to drop a level".
- A driver is **pervasive** when it reaches at least `pervasive_categories` risk categories (setting in `config/risk_settings.json`, starting value 3; editable with the other rating settings). A category is the risk's domain.
- Insights are 2 to 5 plain cards: how many risks are Elevated or have a Critical or High likelihood (and which); what drives them (the top three likelihood and impact drivers); up to two pervasive drivers; and, for an L3 team, a risk that is more serious together than for any L4 team on its own (with what each team brings) and the L4 team that clearly carries a category.
- Risks are ordered Elevated first, then likelihood (Critical to Low), then impact, then category; risks that don't apply come last.
- Download (.csv) is one row per risk and driver; Print is the browser's own.

**API** (all open to everyone who can open the Risk site; an unknown id is 404 `{"ok": false, "error": "There is no such team."}`)
- `GET /api/risk/teams`: every L3 team with its L4 teams (`status`, `assessed_on`, `counts`).
- `GET /api/risk/teams/<id>/results`: `team`, `assessed`, `message`, `counts` (`elevated`, `likelihood` by level, `doesnt_apply`), `insights`, `risks` (each with `likelihood`, `impact`, `impact_by_dimension`, `elevated`, `applies`, its drivers with a plain `source`, and `by_l4` for an L3 team), `drivers` (with `pervasive`, `where`, `teams`), `drivers_total`, `categories`. A team with nothing submitted gets `assessed: false` and a plain `message`.
- `GET /api/risk/teams/<id>/results.csv`: columns Team, Category, Risk ID, Risk, Elevated, Likelihood, Impact, Driver for, Driver, Driver name, Dimension, Where it came from, and L4 team (L3 only). Cells never start with `=`, `+`, `-` or `@`.
- Where a driver came from, for a data driver: "From TRUST data: <its figure> in <month>" (the figure, not the comparison with the median). For an L3 team: "Lending Engineering: Yes (Emery Rook) · Lending Operations: Yes (Val Zeller)".

## Elevated risk markers on the CTO view (automatic)

Owner, 16 Nov 2026: an exception to "risk results are never compared across teams". There are no switches (the owner removed the On and Off list the same day). The CTO view marks a team on a metric when the team's own newest risk assessment has an Elevated risk that the metric watches. No assessment, nothing Elevated, or a metric that watches no risk: nothing is shown. A marker points to a conversation. It never changes a score, status, threshold, cap, watch list or letter.

- **Which risks a metric watches.** The "Risks each metric watches" list (`editable.metric_risks`; it starts from `card.risks` in `config/metrics.json`). A metric that watches no risk marks nobody.
- **When a team is marked.** An L3 team is marked when any of its L4 groups' newest assessment has an Elevated risk the metric watches (as stored when the group submitted; nothing is rated again). The marker is on the L3 team, so its id is the family id; each risk is listed once.
- **Where the data comes from.** `GET /api/cto/risk-markers` (`backend/trust/risk/cto_markers.py`, route at the end of `site.py`). It returns only `{"ok", "markers"}`: team id, metric id and name, and the Elevated risk ids and names. Each person gets only the teams they may see. `data.json` is not touched.
- **What the CTO view draws.** A marked team gets a small purple pill with the metric's short name under its name in the grid, with a tip listing the Elevated risks. One line in the grid's key explains it, shown only when at least one marker is shown. Nothing else is drawn. Code: `frontend/pages/cto-view.js` (names start `cmk`), `frontend/pages/cto-view.css`.
- **Tests.** `tests/test_cto_risk_markers.py`: an Elevated watched risk marks the team with no switching; a metric watching nothing, or not Elevated, gives none; no assessment, no marker; a family lead sees only their own family; no score changes.

## Uploading the risk files

Owner, 16 Nov 2026: "I want to be able to upload that info in the format that we need to be ingested. Pick a structure and accept the uploads to seed the data from." And: "the questionnaire is a yaml file itself so we can just map that." The real files can't be shared yet, so everything is built against made-up ones (`tools/test_risks/`) and the readers are tolerant, the way TRUST's `config/column_maps.json` is for the provider's files: the real file is the layout. Case, spaces, dashes and underscores in names don't matter, a close spelling is matched, and an unknown key is a note, never a refusal. Something that can't be used is one plain problem sentence; that item is left out and the rest still loads.

**The page.** Page `#/upload` on the Risk site, for Tech Risk (anyone while TRUST runs open, with a typed name; the same rule as saving an editing list). It is linked from the Edit page ("Upload risk files"). Each of the three kinds goes the same way: choose the file, **Read and check**, see what was found and every problem, **See what would move** (which teams' newest ratings would change; saves nothing), then **Load**. Load is available once the page has shown what would move. Code: `backend/trust/risk/seed.py` (readers and checks), `seed_routes.py` (routes), `frontend/risk/risk-seed.js` (page). Tests: `tests/test_risk_seed.py`.

**The site becomes the golden source.** The same "first load from a file, then edited on the site, with history" rule as the editing lists.

- *Risks and drivers:* every load is one row in `risk_seed_upload` (migration 0020; a file in the store folder when there is no database) with who, when, the hash of the files, what was read, and every risk (or every driver rule) the site holds after it. A load adds new items and replaces changed ones; nothing is removed. `site.load_registers` reads the newest load of each kind before the risk files folder, so after the first load the folder is not read for that kind.
- *Questions:* a load goes into the "questions" editing list as rows (add, or edit for a question the list already has, with one "First load from the file" row first when the list was never saved), with who and why, so they show with their history on the Edit page. Questions already on the site that are not in the file stay as they are. The help text is kept with the question (the questions list has a Help text field) and shown under it on the form.

**What would move.** For questions it calls `editable.rating_moves`. For risks and drivers it does the same re-rating between the registers now and the registers with the load on (`seed.moves_for_registers`), because `rating_moves` can swap only one editing list. It lists each team's newest assessment's answers rated twice and shows the ratings that differ (applies, Elevated, likelihood, impact, and new risks). It changes no rating.

### 1. Risk files

The engine's own YAML shape. One or more files, or a `.zip` (a folder of them, as the Risk site's download gives, is fine). A file holds risks keyed by id, as `config.risks()` reads them; a file holding one risk takes its id from the file name. Files that are not YAML inside a zip are left out with a note; a `driver_mapping.yaml` among them is pointed to the drivers upload. Notes come from the existing risk checks (`files.check_risks`): a rule naming a driver the drivers don't have, a level the rules don't read, and so on.

```yaml
air.ops.02:
  domain: Operational
  category: Repeat incidents
  name: The same incident keeps happening
  likelihood_scoring: {critical: ">.80 and RD63 in ad and RD64 in ad", high: ">.60 and RD63 in ad"}
  likelihood_drivers: [RD63, RD64, RD12]
  impact_drivers: [RD54]
  impact_scoring:
    financial_impact: {critical: null, high: null, medium: "RD54 in ad", low: "dc >= 1"}
  description: Postmortem actions aren't finished, so the same incident happens again.
```

**The owner's real layout (16 Nov 2026).** The real files write each driver list as a block list in lowercase, while the rules write capitals, and the likelihood shares with `>=`:

```yaml
air.cyber.01:
  domain: cyber
  category: unauthorized access
  name: external data breach
  likelihood_scoring:
    critical: '>= 0.80 and (RD01 in ad or RD02 in ad or RD03 in ad)'
    high: '>= 0.60 and (RD01 in ad or RD02 in ad or RD03 in ad)'
  likelihood_drivers:
  - rd01
  - rd02
  impact_drivers:
  - rd01
  - rd02
  impact_scoring:
    financial_impact: {critical: null, high: RD50 in ad, medium: RD02 in ad, low: dc >= 1}
    client_impact: {critical: null, high: RD48 in ad, medium: RD25 in ad, low: dc >= 1}
    regulatory_impact: {critical: null, high: RD43 in ad, medium: RD51 in ad, low: dc >= 1}
  description: words here
  example: of the risk occurring
  framework_mappings:
    iso_25010:
    - characteristic: security
      sub-characteristic: Confidentiality
    nist_sp_800_30:
    - threat_source:
      threat_event:
```

Driver codes are read in any capitals (`rd01` = `RD01`), in the risk files and in `driver_mapping.yaml` (`config.driver_code`, `config.tidy_driver_lists`). A list may also be a block per driver (`- id: RD01 …` or `- RD01: {…}`) or a map keyed by code. An entry that isn't a code is one plain problem naming the risk, the field and what was found; the risk still loads with the codes that could be read. Any other surprise while reading an upload is a plain refusal (nothing saved), never a server error (`seed_routes.read_safely`). Tests: `tests/test_risk_driver_lists.py`.

### 2. Driver rules

`driver_mapping.yaml`: `risk_drivers:` keyed by the driver code (any capitals; read as `RD01`). A driver with no questionnaire field is answered from data and has no question. Other keys on a driver are listed as notes.

**The trigger language** (owner, 16-17 Nov 2026; `backend/trust/risk/trigger_language.py`). A trigger says when a driver is on. The owner's risk engine writes triggers as **Python-style expressions**, so TRUST reads them the same way: Python's own reader (`ast.parse`) turns the text into a tree, and TRUST walks that tree with a short allow-list. **Nothing is ever run as code**: there is no `eval`, `exec` or compile-to-run. Anything not on the list is a problem for that driver only, and the sentence says where it stops ("near character 14 ('Yes')"). Spaces and capitals don't matter, except inside quoted text, where capitals and end spaces are ignored when comparing.

Before reading, TRUST tidies only what Python can't read but the owner's files use: curly quotes become straight, `&&` `||` and a lone `!` become `and` `or` `not`, `AND` `OR` `NOT` (any capitals) become `and` `or` `not`, `TRUE` `true` `FALSE` `false` `NONE` `null` become `True` `False` `None` (only as bare words, never inside quotes), and a trailing `# comment` is dropped.

| Piece | Written as | Means | Example |
| --- | --- | --- | --- |
| Answer | `get('RD01')`, `get(RD01)`, `get('rd01')` | The team's answer to that code (capitals don't matter) | `get('RD01') == True` |
| Answer with a fallback | `get('RD70', 0)` | The answer, or this value when there is none | `get('RD70', 0) > 3` |
| Prevailing median | `prevailing('RD22')` or `prevailing_median('RD22')` | The prevailing median for a data field | `get('RD22') > 1.5 * prevailing('RD22')` |
| Number functions | `to_int` `to_float` `int` `float` `abs` `min` `max` `round` | Safe versions of our own. A missing answer stays "not known". Text that isn't a number makes the comparison false. It never crashes | `to_int(get('RD65')) >= 1` |
| Text functions | `str(x)` `len(x)` `bool(x)` | The answer as text, its length, yes or no | `len(get('RD70')) > 0` |
| Text methods | `.lower()` `.upper()` `.strip()` `.title()` `.startswith(x)` `.endswith(x)` | Only on text. On anything else the result is "not known" | `get('RD70').lower() == 'yes'` |
| Numbers | `3`, `0.5`, `.5`, `-2`, `1e3` | `25%` as an answer is read as 0.25 | `get('RD12') >= 3` |
| Text | `'...'` or `"..."` | Commas, spaces and the other kind of quote are part of the text | `get('RD35') == 'Broadly, yes'` |
| Yes / no / nothing | `True`, `False`, `None` | A yes, a no, or no answer | `get('RD01') is not None` |
| Compare | `==  !=  >=  <=  >  <`, chained | `3 <= x <= 10` means both | `3 <= get('RD70') <= 10` |
| Is | `is`, `is not` with `None`, `True` or `False` | | `get('RD01') is True` |
| One of these | `in`, `not in` with a list or tuple of constants | The answer is one of these | `get('RD01') in ['A', 'B']` |
| Option ticked | `'X' in get('RD40')`, `'X' not in get('RD40')` | See "tick-any" below | `'Option A' in get('RD40')` |
| And / or / not | `and` `or` `not`, and `&` `\|` between comparisons | `and` is worked out before `or` | `(get('A') == True) & (get('B') >= 2)` |
| Arithmetic | `+ - * / %`, unary `-`, brackets | Numbers only. Dividing by zero is "not known" | `get('RD70') / get('RD71') > 0.5` |

Not allowed (a plain-words problem, never run): other function names, attribute access other than the text methods above, `lambda`, loops and list building, f-strings, `[0]` lookups, `**`, `//`, `if ... else`, assignments, and any longer than 2,000 characters or nested more than 100 deep.

How a trigger is worked out:

- A comparison that needs a missing answer is "not known", which is never True. A driver whose answers are all missing is "not known", and is never counted as on. (An answer with a fallback, `get('RD70', 0)`, doesn't count as needed.)
- A trigger that is one simple comparison (`(get(RD12)>=3)`, `(get('RD01') == True)`, `get(RD22)>prevailing(RD22)`) keeps the simple rule the Rating settings and Questions pages edit. Any other trigger is kept as its tidy text, for example `(get('RD35') == 'Broadly used, across teams')`, and the driver is on exactly when it is true. The download writes it back the same way.
- A field compared with text (`==`, or `in [...]`) is a **choice question** on the form: the texts in the trigger are the choices, with Other for none of them. A field compared only with True or False is a yes or no question, and any other field is a number.
- **Tick-any** (owner, 17 Nov 2026). Some answers are several options ticked. `'X' in get(field)` is True when X is one of the ticked options (capitals and outer spaces don't matter). When the saved answer is a single text, it is True when the text equals X or X is one of its comma- or semicolon-separated items. It is never a part-word match: `'Yes' in 'Yes, partly'` is True because "Yes" is one of its items, `'es'` is not. A missing answer (or nothing ticked) is "not known". `get(field) == 'X'` on a list answer means X is among the ticked options. A field used as `'X' in get(field)` is a **tick-any question**: the form shows checkboxes, the options are every such X across all triggers (plus any the questionnaire file lists), and "None of these" comes last and clears the others. The answer is kept as a list of the ticked options and shown as "A; B". Older saved text answers still load. In the questionnaire file, `MultiSelect`, `Multi-select`, `Multiple choice`, `Checkbox`, `Checkboxes` and `List` mean tick-any (`config/risk_questionnaire_map.json`, `kind_words`); the options come from the file's `options` list, else from the triggers.
- A full trigger is edited as text on the Edit page, "Drivers with a full trigger". It is checked before it is saved, and the page says where it stops when it can't be read.

```yaml
risk_drivers:
  RD12:
    trigger: "(get(RD12)>=3)"
    questionnaire_fields: [RD12]
    rationale: "The team supports three or more critical business processes."
```

### 3. Questionnaire, and its mapping file

The owner's own YAML (layout below, owner 16 Nov 2026). Through `config/risk_questionnaire_map.json` says which key gives each part of a question. **The owner edits that file** (it opens with a `_how_to`); the page shows it under "Where the questionnaire's keys are named". Each part is a list of names, best first; to use a different key, put its name at the start of the list. Defaults that work with a plausible shape:

| Part | Map key | Default names | What it is |
| --- | --- | --- | --- |
| The question list | `question_list` | questions, questionnaire, items, form.questions, survey | A top-level key or a path (`form.questions`). The file itself may be the list; the list may be keyed by field; questions may sit inside sections that each hold a list. |
| The driver field the question feeds | `field` | field, driver_field, feeds, driver, driver_code, key, id, code | Matched to a driver by its questionnaire field, its rule field, or its code (any case). |
| Wording | `text` | text, question_text, question, wording, label, prompt | Required. |
| Section | `section` | section, group, category, topic, area, tags | A list (`tags`) gives its first item. If none, the section a driver's domain gives. |
| Order | `order` | order, position, sequence, number, sort | If none, file order (10, 20, 30). |
| Kind of answer | `kind` + `kind_words` | kind, input_type, type, answer_type, format | Yes or no, a number, a share (a part of the whole, like 25%), or text (a choice of answers; the choices come from the driver's trigger). If none, the driver's rule decides. |
| Which answer switches the driver on | `switches_on` | switches_on, turns_on, on_when, trigger_answer, trigger, threshold, at_least | Yes or no, or the number it must reach: `3`, `">= 3"`, `"at least 3"`, `"more than 40%"`. A share written 40 is read as 40%. If none, yes, or the driver's own rule. |
| Help text | `help` | help, help_text, hint, guidance, explanation, notes | Optional. |
| Asked or not | `enabled` | enabled, active, is_enabled, asked | `false` leaves the question out. If it is on the site, the load switches it off there (status "Switched off", kept in history); `true` again brings it back. No key means asked. |

**The owner's real layout** (16 Nov 2026), questions keyed by driver code; not every driver has a question:

```yaml
questions:
  RD01:
    driver: RD01
    description: Access to confidential data
    question_text: Do members of your team have access to confidential data, including client-provided data sets?
    input_type: Boolean
    enabled: true
    tags: [Data, Access]
    applicable_business_processes: all
```

`description` and `applicable_business_processes` are not used yet (listed as notes).

**The answers a question offers (owner, 17 Nov 2026).** Read from `options`, `input_options`, `choices`, `answers`, `answer_options`, `allowed_values`, `input_values`, `option_list` or `select_options`, given as a list (`- Broadly, yes`), a list of `{label, value}` pairs (the label is shown), or one line split on `;`, `|` or new lines (`'Broadly, yes; Partly; No'`; commas stay inside an answer). A bare `Yes`/`No` in the file (which YAML reads as true/false) is read back as the word. A **pick-one** question offers every answer the file lists, then any answer its trigger looks for that the file leaves out (with a note), then Other. A **tick-any** question offers the file's answers and the trigger's, then None of these. On the Edit page the same list is "Answers to choose from" (separated by `|`). Tests: `tests/test_risk_questionnaire_layout.py`.

**The questionnaire decides what is asked (owner, 16 Nov 2026).** Before a questionnaire is loaded, every driver with a questionnaire field gets an automatic question from the driver file. When a questionnaire with at least one readable question is loaded, every question on the site that the file doesn't have is **switched off** (retired, with the reason "Not in the questionnaire, so not asked."); its driver shows "not known" unless data answers it. A question the file has but can't read is never switched off for that; its problem is listed. "See what would move" shows any rating that changes before anything is saved. Tests: `tests/test_risk_questionnaire_layout.py`.

Keys in the file that the map doesn't name are listed as notes. A question whose field matches no driver (with a "did you mean" when one is close), a question with no wording, and a question for a driver answered from data are plain problems; each is left out. `tools/test_risks/questionnaire_example.yaml` is a made-up example in this shape:

```yaml
questionnaire:
  - field: RD31
    section: Change
    order: 30
    question: Do automated tests run before every release?
    type: yes/no
    switches_on: "no"
  - field: RD14_pct
    question: What share of the team works on legacy platforms?
    type: share
    switches_on: "more than 40%"
```

### Controls from TRAC

The same page has a "Refresh controls from TRAC" button for Tech Risk. It calls the existing `POST /api/risk/controls/refresh` and shows the kept copy's date and how many controls it holds.

### Routes

`GET /api/risk/seed` (what the site holds, the earlier uploads, the kept TRAC copy, the mapping), and `POST /api/risk/seed/<risks|drivers|questions>/check|preview|load`, each a form with one or more `file` fields and `by`, with `X-TRUST: 1`. Nothing here changes how a rating is worked out.


## The front page (owner, 16 Nov 2026; made easier to find your way, 17 Nov 2026)

The owner's words: "we need to know how to get to the answer questionnaire page." So the page now leads with that.

- **Four steps under the title:** 1 Find your team, 2 Answer the questions (saved as you go), 3 Submit, 4 The L4 leader signs off.
- **Top box, "Answer your team's questionnaire".** When TRUST knows the person's own team, it shows it as a big button: "Answer the questions for Lending Engineering", or "Continue answering for Lending Engineering (12 of 30 answered)" when a draft exists, or "View results for ..." when it is submitted and nothing is open (with a small "Start a new assessment" beside it). A team is the person's own when they are in that L4 team, or lead the L3 team it sits under (so an L3 lead sees their L4 teams). Managers above, Tech Risk, auditors and open access have no "own" team: the box says "Pick your team, then click Answer questions" and offers a "Find your team" search. Someone who has own teams gets a "Find another team" search above the tabs.
- **Search.** Typing a team, a leader or an L3 team name filters the table live and hides L3 headings with no rows left. Typing while on "Continue an assessment" moves to "Start a new assessment", which lists every team the person may answer for.
- **Buttons say what they do:** "Answer questions", "Continue answering", "View results".
- **Tables are grouped under a light heading row for each L3 team** (the All metrics page does the same), so there is no L3 column.
- **Tech Risk line.** "For Tech Risk: Download risks and drivers, Compare with the engine" sits in one small line at the bottom, shown only to Tech Risk (and while TRUST runs open).

Three equal tabs, with the count on each. It opens on "Continue" when something is in progress, otherwise "Start".

- **Continue an assessment.** One row per open assessment the person may answer: team, started (when, by whom), last saved (when, by whom), progress ("12 of 17 questions answered"), status (Draft, or Sent back with the reason) and a "Continue answering" button. Nothing open: one plain line.
- **Start a new assessment.** The teams the person may answer for (the lead, everyone under them, Tech Risk) with each team's last submitted date or "Never assessed". A team with an open assessment shows "Continue answering" instead of "Answer questions", so a team has one open assessment at a time. "Answer questions" opens the form pre-filled with the last submitted answers.
- **View results.** Teams the person may view that have submitted: last submitted, sign-off (Submitted, Signed off, Sent back) and a "View results" button. No ratings, Elevated counts or anything that compares teams.

**`mine`.** `GET /api/risk/groups` gives each team a `mine` flag (true when the person is in the team or leads its L3 team; always false while TRUST runs open). It changes nothing about who may see or do what. Tests: `tests/test_risk_home_mine.py`.

**What "open" means (`backend/trust/risk/home.py`).** Since the team's last Submit, any of: someone pressed Start, someone saved an answer, or the last assessment was sent back. Nothing new is kept for the answers: they are never removed, so the newest answer of each question is already what a new assessment is pre-filled with. Only Start is recorded, in a small table `risk_start` (migration 0021: group, who, when). Saving an answer without pressing Start still counts as open (the first answer saved is then "started"), so older data and the API keep working.

**Progress.** A first assessment counts the questions answered. Later ones are pre-filled, so they count the questions confirmed or changed since the last Submit ("3 of 17 questions confirmed or changed").

**On the form.** A carried-over answer says "Last confirmed <date> (<who>)" until it is changed or confirmed again. "Still true" saves the same answer again, which is what confirming means.

**Routes.** `GET /api/risk/groups` gains `open` (null or started, last_saved, answered, of, counted_as, status) and `results_status` for each team. `POST /api/risk/groups/<id>/start` (needs the right to answer; `X-TRUST: 1`, and `by` while open) records who and when, or returns the open one with `started: false`. Tests: `tests/test_risk_home.py`.


## Drivers answered from TRUST's data (owner, 16 Nov 2026)

A driver the questionnaire doesn't ask about is answered from data. Five are calculated, one calculation each, for every Risk group, which is an L4 team (since 17 Nov 2026; before that, a TRUST team). Every figure is worked out per L4 group, and the prevailing median is the median across the L4 groups that have a result. **How an item is placed with an L4 group:** a repo goes to the L4 group of its owner (the owner's work email, found in HR); a change, an incident or an action goes to the L4 group of each person named on it (`items_by_group` in `team_figures.py`, using the people TRUST keeps with the item); an item whose people are in no L4 group (for example the L3 lead) is counted for none. The code is `backend/trust/risk/data_drivers.py`; the starting values are in `config/risk_data_drivers.json` and on the editing page "Drivers answered from data". **All the numbers below are starting values for Tech Risk to tune**, and the pages say so.

| Driver | Calculation | ON when |
|---|---|---|
| RD21 Legacy application architecture | the languages of the L4 team's active repos, each repo placed with its owner's L4 team (repos file, new `Languages` column, like `Perl:1200; C:340`) | any repo uses Perl, C, C++ or PHP (the list is a setting) |
| RD15 Lack of formal change process | TCC adoption = the team's TCC changes / (TCC + Non-TCC changes) that month, counted the way the scorecard's TE-01 counts them (`measure.te01`), each change placed with the L4 team of the people named on it | below the prevailing median across teams |
| RD53 Inadequate team capacity | the people in the L4 team (`groups.members`, the same count the Risk site shows) | below a share (70%) of the prevailing median headcount. A big organization with many small teams is not flagged: the median is its own |
| RD11 Diversity of running process types | distinct languages across the team's active repos, leaving out markup and configuration (starting list: HTML, CSS, SCSS, Sass, Less, Markdown, Dockerfile, Makefile, HCL, Shell, Batchfile, PowerShell, Jupyter Notebook, TeX, Roff, Smarty) | above the prevailing median |
| RD25 Multiple teams contributing | the new `repo_contributors` file (Repository, Month, Contributor login, Contributor email, Commits): each contributor is matched to a person in HR **by email address only** (case and spaces ignored; the login is never used) and so to that person's L4 team. Counts the other L4 teams with commits in the team's repos that month | more than 2 other teams |

**The prevailing median is TRUST's own** (`score_month.thresholds_for`, used as it is, with the same fewest-teams rule `min_families_for_threshold`). One place per calculation.

**Never guessed.** A driver whose data isn't loaded, or whose team has none of it (no repos, nobody placed, no commits that month, too few teams for a median) is "not known", says why, and is never counted as on. A contributor whose email matches nobody in HR is listed in the sentence ("1 contributor couldn't be matched to a person in HR by email address, so is not counted") and not counted. A contributor in HR but in no L4 team (for example an L3 lead) is listed the same way. A repo whose owner is in no L4 team is placed with no L4 team, so it is counted for none.

**Which code.** The driver rules file marks a data-backed driver by giving it no `questionnaire_fields`. `config/risk_data_drivers.json` `calculations` maps each calculation to a driver code, so the owner can point a calculation at a new code if a code changes. A data driver with no calculation shows "not known: no calculation answers this driver yet".

**On the form** the "answered from data" box shows each data driver as ON, OFF or Not known, with its sentence, the file it came from and the day that file was loaded. **On Submit** each data driver's ON or OFF is given to the rating as the driver's answer (`data_drivers.assess_with_data`): the rating rules are not changed. The result keeps what each said (`result.data_drivers`: on, value, sentence, sources), so a past result still names its source; the results page names the source under each data driver that is on and in "How this was rated". Saved answers (`result.answers`) hold only what people typed, so the form's status is not affected.

**The editing page.** Each driver can be compared with the prevailing median, a share of it, a fixed number, or (RD21) a language list; RD11 also has its left-out list. Only the ways a calculation can use are offered. A saved change wins over the file, is kept with a reason, and removes the "starting value" label for that driver. Saved assessments don't change.

**TEST data.** `tools/make_test_data.py` writes made-up `Languages` and a `repo_contributors.csv`, so some teams show ON and some OFF. `tools/test_risks_data_drivers/` is a copy of the made-up risk files with the five drivers added (the plain `tools/test_risks/` stays at 21 drivers because tests pin it). Tests: `tests/test_risk_data_drivers.py`. The files are described in `docs/wiki/data-sources/repo_contributors.md`.

## Calculations you define (owner, 16 Nov 2026)

Tech Risk can answer a driver from data with no code. On the Risk site's edit page "Calculations you define", add one entry per driver: the driver code, a **team figure** TRUST already works out, a **test**, and a number or share when the test needs one. Save with a reason; the history is kept, an entry is retired rather than deleted, and the list can be downloaded, like every editing list. A brand-new figure still needs code.

| Team figure | What it counts | From |
|---|---|---|
| Changes released in the month (`releases`) | the TCC changes deployed that month, as TCC adoption counts them | the TCC file |
| Incidents in the month per 100 people (`incidents_per_100_people`) | the team's Critical and SWE incidents, counted as UN-01 counts them (`measure.un01`), divided by the people placed with the team, times 100 | the postmortems file and HR |
| Critical or High Checkmarx findings open longer than the age limit (`aged_critical_high_findings`) | the team's open Critical or High findings (SAST and SCA) older than `finding_age_days` (30, a setting in `config/risk_data_drivers.json`) at month end. **Not known today:** the Checkmarx files TRUST keeps carry no first-found date, only a count past the policy limit, so the figure says so and never guesses. It starts counting once Cyber adds the date | the Checkmarx SAST and SCA files |
| Postmortem actions past their due date (`overdue_postmortem_actions`) | the team's postmortem actions past their due date at month end, counted as UN-02 counts them (`measure.un02`: open actions on an incident in scope and rated) | the postmortem action items file |

| Test | ON when the team's figure | Needs |
|---|---|---|
| `above_median` / `below_median` | is above / below the prevailing median | nothing |
| `below_share_of_median` | is below a share of the prevailing median | a share, a part of one (0.70 = 70%) |
| `above_number` / `below_number` | is above / below a number | a number |

The prevailing median is the same one the five built-in calculations use (`score_month.thresholds_for`, with the same fewest-teams rule). A figure whose data isn't loaded is "not known" (never a guess), and a not-known driver is never counted as on. A defined driver reads like the built-in ones: ON, OFF or not known, a sentence ("5 releases in October; the prevailing median is 3 across 8 teams, so this is ON."), its source, and its code places (the figure's function and the test's function in `backend/trust/risk/team_figures.py`; the form shows both). The rating rules don't change.

Refused in plain words: a driver that doesn't exist, one that already has a calculation of its own (built-in or defined), one answered by a question on the form, a missing number, a share that isn't a part of one, a number given to a test that uses none. The starting entries (RD22 releases above the median; RD44 aged Critical or High findings above 0, not known until the files carry a first-found date; RD63 incidents per 100 people above the median; RD64 overdue postmortem actions above 0) are in `config/risk_data_drivers.json` under `defined_calculations`; a code that isn't in the drivers file in use is kept but marked "not used yet". The cache key includes the list, so a saved change shows the next time a form is opened. A driver a defined calculation answers is left off the "Drivers answered from data" list (it is not "not calculated"); retiring the calculation brings it back there. Code: `team_figures.py` (figures and tests), `data_drivers.defined_calculation`, `editable.LISTS["calculations"]`. Tests: `tests/test_risk_calculation_builder.py`.

## See the code (owner, 16 Nov 2026)

The Risk site shows where each calculation lives, like the TRUST metric cards. The results page ends with a closed "See the code" section listing the rules that rate a risk: whether it applies, likelihood, impact, the rating and Elevated. Each data driver also carries one small line, "Worked out in data_drivers.py · legacy_languages() lines a–b", on the form and on the results. All of it comes from `backend/trust/risk/code_places.py`, the one list of which functions to show, built with `codelinks.place()`, so line numbers are read from the running code and become links once `code_repo_url` is set. The results API sends `code_places`; each data driver carries `place`. `tests/test_risk_code_places.py` fails if a listed function is renamed.

## L4 teams: what changed in the data drivers and team figures (17 Nov 2026)

All five built-in drivers and the four team figures are now worked out per L4 group. Nothing is "not known" for being L4-only; each figure can be placed per L4 from what TRUST keeps. RD21 and RD11 (repos) and RD25 place a repo by its owner's email. RD15 and the figures `releases`, `incidents_per_100_people` and `overdue_postmortem_actions` place each item by the people named on it. RD53 and the headcount in `incidents_per_100_people` use the L4 team's people. `aged_critical_high_findings` is still not known (the Checkmarx files carry no first-found date). The prevailing median is taken across the L4 groups, so it moves from a median of a few L3 teams to a median of many L4 teams: expect different ON and OFF answers than the L3-level ones. The rating rules and TRUST's scores are not touched.

## Questionnaire answers in bulk (CSV) and Proposed results (owner, 17 Nov 2026)

- **Download** (Upload page, card 4; `GET /api/risk/answers.csv`, Tech Risk): one row per L4 team and question:
  `team_id, team, l3_team, l4_leader, question_code, section, question, answer_kind, choices, answer`, with each team's
  newest saved answer. Tick-any answers are written `A; B`. The file opens in Excel (a BOM is written; a cell that would
  start a formula is prefixed with `'`).
- **Upload** (`POST /api/risk/answers/check`, then `/load`, Tech Risk; anyone while TRUST runs open): only `team_id`,
  `question_code` and `answer` are read. Each answer is checked exactly as the form checks it. A blank answer leaves the
  saved one as it is; an answer equal to the saved one is skipped; a row the file can't use (unknown team, a question
  not on the form, an answer the question doesn't take, a team answering a question twice) is listed with its row number
  and the rest still count. Load saves each changed answer as a new answer row (who: "<name> (bulk upload)"), exactly
  like the form. **Nothing is submitted.** The upload is logged in the activity log. Code: `backend/trust/risk/bulk_answers.py`.
- **Proposed results:** a team whose saved answers are newer than its newest submit (or that never submitted) is rated
  from those answers on the Teams' results pages, marked **Proposed** (a chip by the name, a note under the header, the
  chip in the teams list), and an L3 team that includes such an L4 team says so. Nothing proposed is kept; it becomes
  the team's result when the form is submitted. TRUST's own pages (Risks we have raised, CTO markers), the heat map and
  sign-off still read submitted assessments only. Code: `team_results.has_newer_answers`, `proposed_snapshot`.

## Key insights on a team's results page (owner, 17 Nov 2026: "It's just strings put together")

Written on the server (`team_results.insights_for`) as `{"story", "focus"}`, from the same ratings and drivers as the
rest of the page; no rule, threshold or formula is named.

- **Story:** how many risks apply and how many are Elevated (plus any more with a Critical or High likelihood). When a
  single risk stands out, it is named here once and the points below say "it". The one or two drivers behind most of the
  risks that stand out ("All/Most/Several of them come back to …"), and, only when they don't cover all of them, how many
  they sit behind. For an L3 team: a risk that is higher for the team as a whole than for any L4 team on its own, and an
  L4 team that alone carries a category.
- **Where to focus:** up to three more drivers (never one already named in the story), each as its own sentence and
  code, then what it does: "It makes A and B more likely, and C more serious if it happens." For an L3 team, which L4
  teams it is on in; a driver from TRUST's data says so.
- A team with nothing that stands out gets the story alone.
