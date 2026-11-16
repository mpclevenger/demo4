# Working notes

## Current goal (Nov 15, 2026): guide people instead of listing things

Audience: engineers building systems and control owners. The site should ask what the visitor is
working on and lead them to what applies, instead of offering three ways to browse the same content.

Status: streams A, B and C, the Slate blue palette and the calendar additions are built and reviewed (Nov 15, 2026).

## Decisions

- The front page no longer shows tool cards. TRUST, the initiative tracker and the SOX control schedule
  are not linked from the front page (owner's call). The tool cards, tool "About" pages and their code go.
  The Apps menu in the top bar (driven by `TRUST_URL` and friends) is left as it is.
- The SOX control execution schedule idea is dropped for now. A risk and control calendar replaces it.
- Top menu, in this order: Start, My system, Controls, Guides, Calendar, Help. Tech Risk also sees
  Risks and controls and Review queue. "Controls" is the existing Library page. "Help" is the FAQ page.
- Guide sections keep their keys; only the labels change: build = "Build a system", run = "Run a control",
  audit_prep = "Get through a review", best_practice = "Reference".
- "Ready" and "In progress": on a visitor's path, a risk area is Ready when every platform they picked
  has published guidance for that risk area; otherwise it shows In progress. A guide shows In progress
  when its file says `in_progress: yes`.
- Keep it simple: no new dependencies, nothing loaded from the internet, vanilla JavaScript, plain-English
  docstrings, no dead code (auditors read this code). Wording editable by a non-developer lives in `content/`.

## Work streams

### A. Start page, menu, guide labels (owner of: `content/home/`, `apps/core/home_files.py`, the home and
tool views and templates, `PRIMARY_NAV`, `apps/wiki/`, the Library "start" box)

1. Start page (`/`): heading "What are you working on?", two doors, then shortcuts.
   - Door 1 "I'm building or changing a system" -> My system (`pathfinder:index`). If that route does not
     exist yet, fall back to the Library.
   - Door 2 "I own or run a control" -> a search box that submits to the existing site search.
   - Shortcuts: "A control review is coming up", "Auditors found an exception", and the six "Start from
     what you're working on" links moved here from the Library page (remove them from the Library),
     plus "Browse everything" -> Library.
   - Wording stays editable in `content/home/` and is covered by `check_home`.
2. Remove the tool cards, `content/home/tools/`, the tool page, its URL, template, code and tests.
3. `PRIMARY_NAV` as decided above (`pathfinder:index`, `riskcal:index`; missing routes are already left out).
4. Guide section labels as decided above; move `key-terms` to Reference. Help = FAQ page with a link to Key terms.
5. Guides: optional `in_progress: yes` line in a guide file -> an "In progress" badge on the guide page
   and in guide lists. Carried through check, sync, export and the site's edit form.

### B. My system (new app `apps/pathfinder`, address `/my-system/`; also owner of `templates/base.html`)

1. Questions page: pick platforms (active platforms from the site), a few yes/no questions, SOX in scope
   (yes / no / not sure), BCP tier (0 or 1, 2, 3 or higher).
   - The yes/no questions live in one small file, `content/my-system/questions.yaml`: each has the question
     text and the risk areas (aspect labels from the catalog) it switches on. Risk areas no question names
     always apply. Checked by `check_content`.
2. Path page: the risk areas that apply, in catalog order. Each row: name, one line saying why it applies,
   Ready / In progress, the controls for that risk area that fit the picked platforms' categories, and
   links to the platform specifics on the Library category page. SOX-only items show when SOX is yes or
   not sure. Tier shows the matching recommended timelines.
3. Answers are kept in the visitor's session (no login needed, nothing stored in the database).
4. A slim bar under the top bar on every page when answers exist: "Showing guidance for: ... Change".
   Library category pages open with the visitor's platforms switched on.
5. Control pages reached from the path end with "Next: <next control or risk area on your path>".

### C. Risk and control calendar (new app `apps/riskcal`, address `/calendar/`)

1. Month grid (Sunday first), previous / next / today, loaded in place with HTMX and working without it.
2. Events come from one file, `content/calendar/events.yaml`, read when the site starts (like the front
   page files, not stored in the database). Each event: title, date, optional end date, type, details,
   optional link (a TRAC page or https), optional `repeats` (monthly, quarterly, annual) and `until`.
   Event types (key, label) are listed at the top of the same file.
3. Click or press Enter on an event -> a pop-up with its details and link. A day with more events than fit
   shows "+N more", which opens the day's list. Filter chips by event type.
4. The file ships with no real events (the owner supplies them); the comments at the top show the format.
   `check_calendar` gives plain-word messages and runs as part of `check_content`.

## Checks

- Baseline before any change: full `pytest` run passed (Postgres 16, Python 3.13).
- After streams A, B and C: 1387 tests passed; `manage.py check`, `makemigrations --check`, `check_home`,
  `check_calendar` and `check_my_system` clean. Start page, My system, the path and the calendar were
  looked at in a browser at 1280px as a visitor and as Tech Risk.

## Remaining work and risks

- Calendar: SOX working group is loaded (Dec 3, 2026, then the second Thursday monthly from Jan 14, 2027).
  Waiting on the owner's `control-dates.csv` and the auditors' walkthrough periods (name, start, end).
  Pulling due dates from the Optro API is an idea for later; the CSV has the same shape.
- Signed in as Tech Risk, the top bar wraps to two rows below about 1450px wide (eight menu items).
- trac18 (15 Nov 2026, owner): the Apps menu links only TRUST and Risk. The Initiatives and SOX schedule links and their settings are removed; the calendar here is the one calendar.
- trac18 (15 Nov 2026, owner): one set of words in all three apps. **Wanted** = we want it and it isn't there yet. **In progress** = being built. "Guidance coming soon" now reads "Guidance wanted". trac19: the comment status "Planned" is now "In progress" (New, In progress, Done, Declined); migration `wiki/0005` converts existing comments and can be undone.
- The path lists up to 12 risk areas; only an explicit No removes one. Watch whether that is still too long.
- "Ready" depends on platform guidance being filled in; none of the 37 controls is tagged to a platform.

## What the three streams decided (details in MAINTAINING.md)

- Front page wording: `content/home/index.md`, `doors.md`, `shortcuts.md`.
- My system: questions in `content/my-system/questions.yaml` (5 questions, optional `because` line). The
  Ready rule is one function, `is_ready` in `apps/pathfinder/paths.py`. Answers live in the session.
- Calendar: `content/calendar/events.yaml`, up to 8 event types, months limited to 2 years back and 5 ahead.
- Guides: `in_progress: yes` in a guide file (new `PageVersion.in_progress` field, wiki migration 0004).

## Palette and calendar additions (Nov 15, 2026)

- Slate blue palette: tokens in the `:root` block of `static/css/trac.css`; the five rules are in
  MAINTAINING.md (colors). Inter replaces Public Sans (bundled in `static/vendor/fonts/inter/`), body 14px.
  No pure white, shadows or gradients; `apps/ui/tests/test_colors.py` pins the palette and checks contrast.
  The Jobs category color moved from #9a6b1f to #946519 to keep AA contrast on the new surface.
- Calendar: `repeats: monthly` with `on: second thursday` (first to fourth or last, any weekday). Optional
  `content/calendar/control-dates.csv` (control_id, period, due_date, note) adds "MA-04 due (Q1 2027)" events
  that link to the site search.
- Checks: 1466 tests passed; `manage.py check`, `makemigrations --check` and `check_calendar` clean; Start
  page, path, a control page and the calendar looked at in a browser with the new palette.

## Content overhaul (started Nov 15, 2026)

Owner's verdict after a full content review: the content is not ready to share. Review findings: advice
defers to "your team's written procedure" (about 60 times in controls, 25 in the Library), no queries or
commands anywhere, the Jobs risk area has no Library guidance, Reports only for Databricks, no platform
team / your team split, placeholder links for the retention schedule and incident reporting, few worked
examples. Work order: 1 timings, 2 "how to check it" per platform, 3 fill gaps, 4 worked examples,
5 platform team vs your team labels, 6 fix and verify accuracy flags.

### Step 1 decisions: timings (owner, Nov 15, 2026)

- Tech Risk does NOT recommend or set timing. TRAC says which timings and alerts a team needs to decide
  and what to weigh; the number comes from firm policy or from the team.
- Access timing is never stated by TRAC: it links to the firm's Access Control Policy
  (placeholder link `#todo-access-control-policy` until the owner supplies the address).
- All timing figures Tech Risk had written are removed (the old "Recommended timelines by BCP tier" guide
  and any figures inside controls and Library text). The guide becomes "Timings your team sets".
- Every control gets a `timings` list, shown as its own card "Timings your team sets" on the control page:

      timings:
        - set: How quickly a failed job is fixed
          consider:
            - When the next job or report needs this data
            - Who is affected downstream
          policy: "[Access Control Policy](#todo-access-control-policy)"   # optional, only where a firm policy sets it

  Each entry needs `set` and at least one of `consider` or `policy`.
- Wording elsewhere in a control: "on the schedule set in your team's written procedure" becomes
  "on the schedule your team has set"; "within the time set in your procedure" becomes "within the time
  your team has set"; for access controls, "the Access Control Policy sets". No "our recommendation is in" lines.
- The five questions for any timing: what is the worst that happens in the gap; how exposed is the system;
  how fast would you notice by other means; what limits the damage meanwhile; what does faster cost.
  Plus: auditors test against what your procedure says, so write down a timing you can meet every time.
- Open: the structured `frequency` pill on each control (monthly, quarterly, ...) still states a frequency.
  Left alone until the owner decides. Open: other firm policy names and links; the Tech Risk email address.

### Step 1 result (Nov 15, 2026)

- Controls: 32 timings across the controls (cut from 60 after the owner said they were too granular). Rule:
  a control lists a timing only for how often the control itself runs, how fast someone responds when
  something goes wrong, or an alert that should exist. Access controls have one entry each, set by the
  Access Control Policy. MC-07, MC-08, CD-01, LA-01, LA-05, PI-01, VM-03, MC-01 and MC-03 have none.
- Owner rejected a timing for logs reaching Splunk; LA-03 is titled "Alerts are triaged within a defined
  timeframe"; TP-01 is titled "Vendor SOC reports are reviewed" (check both titles against the RCM).
- Guide "Timings your team sets" replaces the old timelines guide (old address redirects). Its area lists
  match the controls. Owner kept two figures as fair: "at least two runs of a quarterly control before
  year-end" and "review at least yearly" for procedures and system documentation.
- Code: `timings` on controls end to end (model, migration rcm 0007, files, edit form, card, search).
- Checks: 1507 tests passed; `manage.py check`, `makemigrations --check` and `check_content` clean; OP-02,
  MA-04 and the new guide looked at in a browser.
- Still open: the Frequency pill and the "checked every day / yearly" part labels on control pages still
  state a frequency; "[shared location — to be confirmed]" and "[retention period — to be confirmed]"
  lines; Access Control Policy link; other policy links; Tech Risk email address.

## Control page redesign (owner approved the shape, Nov 15, 2026)

Why: "What good looks like" was a long checklist nobody would read; pages described a finished control
instead of the order to build it in. The owner wants each control to read as a logical build sequence.

### The page

1. Header: ID, title, and only two pills: Preventive or Detective, and "Key" when the level is key.
   Every other field (method, frequency, level, owner, performer and reviewer roles, categories, platforms,
   stage or theme) STAYS in the data so filtering, the explorer, the SOX view and My system keep working,
   but is not shown on the control page.
2. Card "Why you'd want this control": the benefit in two or three sentences (`why`), then
   "It fits when:" and the `applies_when` statements. (Replaces "Why this control exists" and "Do I need this?")
3. Card "How to build it": numbered `steps` in the order a team would do them. Each step:
   - `do`: a short imperative title ("List your jobs.")
   - `how`: one to three plain sentences on doing it and why it matters
   - `weigh` (optional): things to consider when the step sets a threshold or a timing; shown under
     "Consider these when setting your thresholds:" (never "TRAC doesn't set these")
   - `policy` (optional): the firm policy that sets it; shown as "Set by: ..."
   - `evidence` (optional): `keep` (the thing to save, one line) and `shows` (the attributes it must
     have: for example the date it was pulled, the system it came from, the period it covers, a record
     count, who pulled it). Shown as "Evidence to keep: ..." and "It should show: ..."
   - `commands` (optional): the actual query or command when we know it, one entry per platform:
     `platform` (name exactly as on the site), `code`, optional `note`. Shown as a code block per
     platform; the visitor's My system platforms open first.
4. Card "Choosing who performs and who reviews" (`choosing_people`): `performer` (list), `reviewer` (list),
   `small_team` (one line), plus the fixed line "Name a backup for both."
5. One link at the foot of "How to build it": "What good evidence looks like" (/guides/what-good-evidence-looks-like/).

Removed from control pages and from the control format: `criteria` (and "For SOX apps" flags), the
`timings` list (folded into steps as `weigh` / `policy`), step `who` and `part`, the generic evidence
groups ("Before you send evidence", "A complete review record", "Where evidence lives and how long
it's kept"), the Performed by / Reviewed by line, and the pills other than the two above.
"Review it regularly" is the wording for a review step: no frequency is stated.

### Reference control (the pattern every control follows)

    - id: OP-02
      title: Job failures are monitored, investigated and resolved
      why: >-
        A failed or missed job can leave a report short of data with no visible error. This control
        turns a silent gap into a problem someone fixes.
      applies_when:
        - Jobs process, move or load data that feeds financial reporting or another control.
      steps:
        - do: List your jobs.
          how: >-
            Pull every scheduled job and data transfer from the scheduler itself, so the list is
            complete. For each, note where it runs, who owns it and what it feeds.
          evidence:
            keep: The job inventory
            shows:
              - The date it was pulled and the scheduler it came from
              - Every job, including disabled ones, with its owner and what it feeds
          commands:
            - platform: SQL Server
              note: Lists every SQL Server Agent job on the instance.
              code: |
                SELECT name, enabled, date_created, date_modified
                FROM msdb.dbo.sysjobs
                ORDER BY name;
        - do: Rank them, and write down why.
          how: >-
            Decide which jobs matter most: what breaks downstream, who relies on the output and how
            soon they would notice. The reason for each ranking is what lets someone else agree with it later.
          evidence:
            keep: The job inventory with a priority and a reason against each job
            shows:
              - Who agreed the ranking and when
        - do: Make failures visible.
          how: >-
            Each job raises an alert when it fails, doesn't start or runs long. The alert goes to a
            queue someone watches, with cover when they're away.
          evidence:
            keep: The alert settings and the list of jobs they cover
            shows:
              - The date, and that every job in the inventory is covered or has a reason it isn't
        - do: Set how fast each priority gets fixed.
          how: Write the response time for each priority in your procedure.
          weigh:
            - When the next job or report needs this data
            - Who is affected downstream, and whether they can be told early
            - Who is available to fix it out of hours
            - What the system's BCP tier implies for how late its data can be
        - do: Record every failure.
          how: Each failure becomes a ticket with the cause, the fix and the date it was resolved.
          evidence:
            keep: The list of failed runs for the period, and the ticket for each
            shows:
              - The period covered and a count that matches the scheduler's own history
              - For each failure, the cause, the fix and when it was resolved
          commands:
            - platform: SQL Server
              note: Failed job runs since a date (run_status 0 is failed; step_id 0 is the job outcome).
              code: |
                SELECT j.name, h.run_date, h.run_time, h.message
                FROM msdb.dbo.sysjobhistory AS h
                JOIN msdb.dbo.sysjobs AS j ON j.job_id = h.job_id
                WHERE h.step_id = 0 AND h.run_status = 0
                  AND h.run_date >= 20270101
                ORDER BY h.run_date, h.run_time;
        - do: Review it regularly.
          how: >-
            Someone other than the operator checks that every failure was handled in time, new jobs
            were added to monitoring, the rankings still hold and repeat failures got a root cause.
          evidence:
            keep: The dated review, with notes on anything that slipped
            shows:
              - Who reviewed it, when, and the period they looked at
      choosing_people:
        performer:
          - Sees the alerts as part of their daily work
          - Has the access to rerun a job
          - Knows the jobs well enough to tell a real failure from noise
        reviewer:
          - Doesn't operate the jobs
          - Understands them well enough to question a closed ticket
          - Has the standing to get a fix prioritized
        small_team: If no one is independent, have someone from another team look at a sample, and write that into your procedure.

### Writing rules for control content

- Four to seven steps, in the order a team would actually do them: usually know your population, decide
  what matters and why, put the mechanism in place, set thresholds, record what happens, review regularly.
- Evidence is specific: name the thing and the attributes it must have. Period evidence needs the period
  and a completeness check (a count that ties back to the source); point-in-time evidence needs the date
  and the system. No lines about where to save evidence or how long to keep it.
- Commands only when we are confident they are right for the platform as the firm runs it (SQL Server,
  Windows Server, Active Directory, Entra ID, AWS, Azure, Databricks, Kubernetes, GitHub Enterprise
  Server, Splunk). Nothing for the in-house job scheduler or VPN (we don't know them): describe in words.
  Every command added is listed for a platform owner to confirm before the page is marked official.
- No timing figures or frequencies. Access timing: `policy: "[Access Control Policy](#todo-access-control-policy)"`
  on the step, no `weigh`. No SOX flags. No "your team's written procedure" as a way of deferring.
- Plain, friendly, US English. Banned in content: "standard", "reach out", "tell tech risk",
  "agree it with tech risk", "route", "through tech risk", "agreed channel".

### Paused Nov 15, 2026 — where to pick up

- Content done, NOT yet checked by the site: all 37 controls in the new step format, and the guide
  `what-good-evidence-looks-like.md`. `apps/wiki/starter_guides.py` now renders ordinary ``` code blocks.
- Code for the new control format and page (apps/rcm and related) was still being written when work
  paused; the working tree may be mid-change. The last fully tested state is the commit
  "Timings your team sets" (zip trac14-timings.zip).
- Next: finish or verify the code, run `check_content` and the full tests, sync into a preview database,
  look at OP-02, MA-04 and MC-07 in a browser, then give the owner the full command list for platform
  owners and the list of dropped lines.
- Open with the owner: does the Access Control Policy cover reviewing administrator activity (MA-03);
  OP-01 "fits when" was narrowed to jobs feeding financial reporting or another control; policy links,
  evidence location, Tech Risk email address; walkthrough period dates; control-dates.csv.

### Control page redesign: result (Nov 15, 2026)

- All 37 controls are in the build-step format; the control page shows two pills and three cards.
  Evidence rules feature removed (rcm migration 0008 drops its tables and old criteria/timings).
- Guide "What good evidence looks like" added; guides can now show ordinary ``` code blocks.
- `docs/COMMANDS_TO_CONFIRM.md` lists every command on a control page by platform, for platform owners.
- Checks: 1519 tests passed; `manage.py check`, `makemigrations --check`, `check_content` clean; MA-04
  looked at in a browser after syncing the new content.
- Removed a mention of a named benchmark and of Tech Risk as a reviewer from the baseline control (PI-01)
  to satisfy the wording check.
- Open with the owner: "Applies to" platform chips still show in the control header; MA-03 administrator
  activity review points at the Access Control Policy; OP-01 "fits when" was narrowed; the Library and
  guides still need "how to check it", the Jobs area, worked examples and platform team / your team labels.

### TRAC's own control codes (owner decision, Nov 15, 2026)

- TRAC's guidance controls are different controls from the firm's SOX controls, so they no longer share
  codes. TRAC: change is CM, access is AM, operations and jobs is MO (risks R-CM-, R-AM-, R-MO-). The firm's
  SOX ids stay MC, MA, OP and are used only in the calendar's control due dates.
- rcm migration 0009 renames existing rows in place; old page addresses redirect; a test stops old codes
  returning to content. Checks: full test suite passed; `check_content` clean.
- Also done: platform chips removed from the control header; MA-03 (now AM-03) activity review is not set by
  the Access Control Policy; OP-01 (now MO-01) fits any scheduled jobs and has a ranking step; MC-04 (now
  CM-04) uses the periodic review of changes instead of a release sample.
- Wanted next: the firm's RCM control list (id and title), to build a SOX id to TRAC lookup.
- From here on TRAC is coordinated with the TRUST scorecard and the risk assessment site.

### MO-02 rewritten around a job inventory (Nov 15, 2026)

- MO-02 (job failures) now fits all scheduled jobs, like MO-01. The heart is a job inventory with eight
  recommended attributes to track, and a High, Medium, Low rating. A higher rating means a failure is noticed
  and addressed sooner; no times are stated, the team writes its own. No post-mortem anywhere on the page.
- Steps are now: inventory, rate, make failures visible, write down times, keep a record of failures and
  fixes, review. SQL Server commands kept; none added. `docs/COMMANDS_TO_CONFIRM.md` step titles and the
  example in `content/controls/README.md` follow. Wording is the owner's to approve.

## Calendar: In progress list (trac26, Nov 16, 2026)

- Owner chose layout option A: the month stays; an "In progress" list sits
  beside it. Boxes have their topic's color (border), matched by the go-live marker on the month; the TRAC code is always printed.
- Statuses: Wanted, In progress, Live. Filters: Status, Topic, Team (they narrow the list and the markers; month links keep them).
- Anyone may propose an item or a change; Tech Risk approves each in the Review queue (that's the spot check). `riskcal:item_new`
  and `riskcal:item_edit` are listed in `ANYONE_MAY_PROPOSE` in `apps/core/tests/test_url_access.py` (the one exception to
  "every *_new and *_edit page is Tech Risk only").
- Live items leave the list after 2 runs without an issue, reported by the owning team (owner: 2 executions of the control;
  fiscal year starts Sept 1). Date history is kept in the item's versions, not shown on the page.
- Files: `apps/riskcal/models.py` (WorkItem), `work_items.py`, `forms.py` (ItemForm), `services.py`, `views.py`, `urls.py`,
  migration 0002, templates `_work_panel.html`, `_work_card.html`, `_adding_choice.html`, `item_*.html`, `static/css/riskcal.css`,
  tests `apps/riskcal/tests/test_work_items.py`.
- "Live" agreed as a shared word (owner, 16 Nov): a control or guide that is in use; Measured stays the word for TRUST
  metrics. Wanted, In progress and Live are in the Key terms guide (`content/guides/key-terms.md`).

## Service account exclusions guide (Nov 16, 2026)

- The guide `service-account-exclusions-database-change-review` now names the control it supports, CM-09, in its
  opening lines. The owner chose TRAC's own code over the firm's SOX ID (MC-07). Firm IDs are not used on the site:
  `/rcm/controls/MC-07/` redirects to CM-07, an old TRAC code for a different control.
- Script and template stay off the site and are linked through `svcacct_exclusion_evidence_script` (owner: link).
- Checked against the owner's v2.0 workbook and notes: criteria, steps, evidence of record and limitations match.
- Checks: `check_content` all OK; the full test run passed.
