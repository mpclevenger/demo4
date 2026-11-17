# How a month works

TRUST turns provider files into one scorecard each month. This page follows one month from the first file to the published page, and to an update if something changes.
The picture is [month-flow](diagrams/month-flow.svg) ([source](diagrams/month-flow.mmd)); the diagrams are kept outside this repo.

![One month, from files to the official record](diagrams/month-flow.svg)

Words in *italics* are explained in the glossary (kept outside this repo). Rules are in [scoring rules](scoring-rules.md). The jobs, in order, are in the [runbook](runbook.md). The tables are listed in [doc 11](../design/11_data_model_v2.md).

**Every file and every month stands alone (owner decision, 2 Nov 2026).** Each file uploads on its own with no other file present, and upload only keeps the file. Files are read and joined by mapping (steps 2 and 3), which can be re-run at any time. A month can be loaded and scored on its own, in any order, with whatever files have arrived. Earlier months only add change arrows and trends.

**There is no month lock (owner, 17 Nov 2026).** Every month is always open: files can be uploaded, mapped, scored, updated and published for any month, at any time. To change a month, upload the corrected file if there is one and **Update the scorecard**: the update re-reads the month's newest files with the settings as they are now. There is no seal, no reopen and no "official" copy to protect. Warnings from the checks are still shown and acknowledged, but they stop nothing.

## The steps

| # | Step | Who | What happens | Where it lives |
|---|---|---|---|---|
| 1 | **Upload** | Tech Risk | A provider's file is uploaded for a month (Data sources page, or `python manage.py upload`), in any order. The file is checked **on its own** at once: junk (unreadable, the wrong file, every row unusable) is refused and not stored; anything else is kept, with its warnings shown (owner, 3 Nov 2026). What is kept is the file **cut down to the columns TRUST uses** (the HR file also to the CTO's line), with the SHA-256 fingerprint of the file as received, its name, size, who uploaded it, when, and the SharePoint link (owner, 2 Nov 2026). | `backend/trust/store.py`, `checks.py`; tables `submission`, `kept_file`; the ITDR application and DR tests files also go into `itdr_application` and `dr_test` |
| 2 | **Map** | Tech Risk, any time | Reading the kept files with the current column map and settings. Re-run it after fixing a column name, loading HR, or changing a setting; nothing is uploaded again. TRUST reads the provider's file as it is, through the feed's column map, written from the real file ([doc 17 §3](../design/17_intake_architecture.md)). A row without its own key is **set aside** and listed with its reason. A field a metric needs that is not in the file means that metric shows No data. Checks that need two files (an action's incident in the postmortem file, people and apps found) run here, only when both files are loaded, as warnings. | `backend/trust/mapping.py`, `intake/`; table `month_result` (kind `mapped`) |
| 3 | **Place with teams** | part of mapping | Done fresh every time mapping runs, from whatever files are loaded. Every item is placed with a person or an app, then an L3 team. Anything that cannot be placed, including when HR or the inventory has not been uploaded yet, is **Not yet mapped**. It is counted and shown on the Firm position page, never dropped (D-73). | `backend/trust/linking.py`, `mapping.py` |
| 4 | **Score** | Tech Risk | Adds the items up per family and metric (`measure.py`), sets each status, then building blocks, family TRUST, firm figures (the firm is scored from its pooled results, owner 4 Nov 2026) and changes (when the previous month is scored). Each run is saved and never edited, with the git commit and a hash of the settings it used. Uploading a file does **not** re-score the month. Nine metrics are measured today (see [scoring rules](scoring-rules.md)). | `backend/trust/score_month.py`, `scoring.py`; table `month_result` (kind `scored`) |
| 5 | **Publish** | with the update | Puts every scored month into the page's data, with change arrows, trends and the *watch list* worked out from the neighbouring months. The website builds its page from this on every visit. | `backend/trust/publish.py`; table `published_file` |
| 6 | **Review** | families, Tech Risk | Steps 2 to 5 together are **Update the scorecard** on This month. It runs in the background, one update per month at a time. Family leads read their own page, add explanations and raise data queries. Tech Risk answers queries, and **acknowledges** each warning from the checks. Comments never change a score. | `backend/trust/jobs.py`, `month_warnings.py`; tables `comment`, `warning_ack`, `event_log` |
| 7 | **Printing** | anyone, any time | **TRUST makes no PDFs** (owner, 2 Nov 2026; replaces the PDFs at lock in D-102, which caused bad problems). The CTO view and each family page have a **Print view** button that lays the page out for paper with every section expanded; people then use their browser's own Print (Ctrl+P, or Cmd+P on a Mac) to print or save. Printing any page with the browser also opens every collapsed section first. A table sorted on screen (by clicking a column head) prints in that order, with the sorted column marked. The month's record is its data in TRUST. | `frontend/index.html` (Print view, print styles) |

Once a month is older than 24 months, **retention** removes it and drops older runs of newer months. The scheduler add-on runs it monthly ([deployment](deployment.md#retention)).

## Items no team could be placed with

Some items can't be placed with an L3 team by any source file, for example a change made by someone who isn't in HR, or a repo with no owner. They count only in the firm's figures and show as **Not yet mapped**, with their share on the Firm position page and on Validation checks. There is no page for claiming them (the Lost and found page was removed on 17 Nov 2026, owner). To place one, fix the source: add the person to HR, or give the repo an owner, then Update the scorecard.

## The timeline

Providers usually send in the first week after month end, families review their page the week after, and Tech Risk updates the scorecard as the last files arrive. The CTO view is then the pre-read for the leadership meeting. This is a guide for the current month, not a gate: TRUST has no business calendar and enforces no dates, and historical months can be loaded at any time.

A provider that sends nothing has its metrics shown as **No data**: nothing is carried over from last month (D-76). TRUST does not mark files as late; see the [runbook](runbook.md#when-a-file-is-missing-or-late) for what to do.

## Data contracts

Once a feed's data contract is approved on the Data dictionary page (formal = approved; owner, 4 Nov 2026), two things hold every month: the upload check compares the file's columns with the contract and warns on any difference (acknowledged like any other warning), and the scoring step uses the file only for the metrics the contract lists; any other metric that reads it shows No data with the reason. A new contract version, approved by Tech Risk, lifts both. Contracts are kept in the table `data_contract`.

## What can go wrong, and what TRUST does

| Situation | What TRUST does |
|---|---|
| The provider's file has its own column names, order or date format | That is normal: the file is the layout. TRUST reads it through the feed's column map, written from the real file. |
| A field a metric needs is not in the file | The file loads. Only that metric shows **No data** this month, with a note naming the field. |
| Some rows cannot be read | The file is accepted; those rows are set aside with a reason; the warning is shown on This month, to be acknowledged. If **every** row is unusable, the file is refused at upload. |
| The file is junk (unreadable, the wrong file) | Refused at upload with the reasons, and not stored. The attempt is in the activity log. |
| The same file is uploaded again | Same bytes: "already received", no change. A different file for the same feed and month replaces the accepted one at once, with no approval; both are kept and the replacement is noted (D-92). |
| A file is uploaded with no other files loaded (e.g. SCA alone) | It loads. Upload never looks at other files. Its rows show as Not yet mapped until HR, the inventory and the repo list are loaded and the month is updated again. |
| No earlier month is loaded | The month is scored on its own. Change arrows, trends and Chronic Red appear once earlier months are scored. |
| HR or the inventory is replaced | Update the scorecard again; every file is re-placed with the new ones. Nothing needs re-uploading. |
| A column name or a setting is changed | A column name: fix it in the column map and **upload the file again** (TRUST only kept the columns it found), then update. A setting: update the scorecard; for the HR file's CTO setting, upload HR again. |
| A file arrives late, or a setting changes, after the month was shown | Upload the file (if any) and **Update the scorecard**. The month is never closed: the update re-reads its newest files with the current settings. |
| The original on SharePoint is edited after upload | The fingerprint recorded at upload no longer matches the original. Get the original back, or upload the edited file as the new version. |

## "Data as of" in the page header

"Data as of" in the header is the **oldest** data date across the month's sources, so the page never says the data is newer than it is. Click it to open a list of every source with its own date. A file that states its own date uses it; a file that states none uses the last day of its month, or the day it was uploaded if that came first (`score_month.data_as_of` and `own_date_of`).

## Where to go next

- The rules behind steps 3 and 4: [scoring rules](scoring-rules.md), [data sources](data-sources/README.md).
- The tables behind each step: [doc 11](../design/11_data_model_v2.md) and [deployment](deployment.md#the-tables).
- The jobs, in order: [runbook](runbook.md).

**Words for a team (owner, 17 Nov 2026).** The scored team is an **L3 team** (the only way teams are made since 17 Nov 2026; the product family owners file and the `team_grouping` setting are gone): everyone who reports up to one level-3 leader in HR. It is named after the leader's HR Department when no other L3 leader has it, else the leader's Supervisory Organization when that is theirs alone, else the Department with the leader's name (owner, 17 Nov 2026); the leader shows under the name as the accountable lead. The team's id doesn't change with its name. `python manage.py levels YYYY-MM` lists each L3 team with its leader's Department and Supervisory Organization. Where this page says "family", the screens say "L3 team". L3 teams have no band, so the CTO view has no band column.

## L3 teams and the L4 split (owner, 17 Nov 2026)

TRUST reports on **L3 teams** for every month: each person at HR reporting level `l3_level` (setting, 3) leads a team made of everyone under them, named as above. An **L4 team** is a person at the next level down and everyone under them; it is the building block, and an L3 team is its L4 teams together. On an L3 team's page, opening a metric's row shows that metric **by L4 leader** first: one row per L4 leader (the owner) and one row "Not under an L4" (owned by the L3 leader), with that row's percentage and count ("100.0% · 4 of 4 scanned repos"; pass/fail metrics show the count alone). A **Show the items** button under it opens the item table (Print view shows both). **No status, colour or letter for an L4, and nothing about an L4 changes a score** (the percentage is for the L4's own follow-up; owner, 17 Nov 2026). An item with people under two L4 leaders counts once for each. A metric whose count belongs to the whole team (Critical and SWE incidents: its apps) is not split; its row says so, with the reason. The Risk site's assessments are filled in per L4 team (doc 21). Code: `backend/trust/l4_split.py`, `frontend/pages/team-l4.js`; L4 from `linking.who_table` and `linking.l4_teams`.

The **All metrics** page (Scorecard, after Firm position) puts every measured metric side by side, one row per L3 team (results as the team page shows them, with a Firmwide row) or, with the switch set to L4 teams, one row per L4 leader under each L3 team. L4 rows are counts only and never scored, and the page is open to every role: its numbers are the same `by_l4` counts as the team pages, sent in `data.json` as `all_metrics`.


**The CTO view's Where to focus (owner, 17 Nov 2026).** It lists only the Red metrics that sit in a Red building block, since those are what drive an L3 team's overall Red. A Red metric inside an Amber or Green block still shows on its team's own page (its Where to focus and the metrics table), and on the watch list. Sharp drops and items needing leadership are listed as before. Display only: no status, score or watch-list rule changes (`ctoDrivesRed` in `frontend/pages/cto-view.js`).
