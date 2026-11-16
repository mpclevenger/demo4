# Maintaining TRAC

This guide is for whoever looks after TRAC day to day. It is written for someone comfortable with the site and a little bit of code, not a full-time developer. New to how the pieces fit? Read [docs/HOW_TRAC_WORKS.md](docs/HOW_TRAC_WORKS.md) first.

Most upkeep happens **in the site itself**, with no code. Part 1 covers that. Part 2 covers the few things that need a small file change, and Part 3 says how to check nothing broke.

---

## Part 1: Updating content in the site (no code)

Everything below needs the **Tech Risk** role. Every change is a proposal: you save a draft, submit it, and a *second* Tech Risk person approves and publishes it. You can't approve your own change, unless single-approver mode is on (see "Before SSO is set up"). Nobody outside Tech Risk sees a draft until it's published.

| I want to… | Where |
|---|---|
| Add or edit a guide | Guides → **New page**, or **Edit** on the page |
| Add or edit an FAQ | Help → **New question** |
| Add or edit a control or risk | Risks and controls → **New control / New risk**, or open the item → **Edit** |
| Change a risk driver, or see the engine's risks | Drivers and engine risks come from the risk engine's files, not the site. See "Refresh from the risk engine" in Part 2 |
| Write the guidance for a category or platform | Open the category page → **Edit guidance**; for a platform, switch on its pill and use **Edit <platform> guidance** in its box |
| Add a platform, or put it in another category | Manage → Platforms |
| Add a topic, or change its stages and themes | Manage → Topics |
| Change the front page words or its shortcuts | Edit the files in `content/home/` (see "The front page" in Part 2) |
| Change the "risk area" questions used on category pages | Manage → Aspect questions |
| See the key controls for SOX in-scope apps | Open `/rcm/sox/` (linked from the Library). It lists every published key control; set a control's **Level** to the first level in `content/controls/levels.yaml` (Key) and it appears there |
| Change the control levels (add one, rename one, choose which are shown by default) | Edit `content/controls/levels.yaml`: to add a level, add an entry; to show a level by default, set `open: true`. Then run the check |
| Retire a guide, FAQ, control, risk or driver | Open it → **Retire**, give a reason. A second Tech Risk member approves it in the usual way |
| Hide a topic or platform without deleting it | Manage → switch it to inactive |
| Answer a comment someone left | Review queue |
| See who changed what | **View history** on any page, or Manage → Recent changes |

Tips:
- Pasting from Word is fine. The editor tidies the formatting, and the site removes anything unsafe when the page is shown.
- A page can hold up to 200,000 characters. If you hit that, split it into two pages.
- Each main heading (Heading 2 in the editor) becomes a collapsible card. Pages with five or more of them open with every card closed, so readers see a list first.
- A guide that is still being written can show an "In progress" badge: tick **This guide is still being written** on its edit form. In a content file, add the header line `in_progress: yes` (see `content/README.md`). Untick it or remove the line when the guide is finished.
- Published versions are never overwritten. Every edit creates a new version, so you can always see what it said before.

---

## Part 2: Small changes that need a file edit

### Who gets which role (AD groups)

Roles come from AD groups. The mapping is one setting on the hosting platform, `SSO_GROUP_ROLE_MAP`. Nothing in the code needs to change.

Format: `group:role` pairs separated by commas.

```
SSO_GROUP_ROLE_MAP=grp-techrisk:tech_risk,grp-internal-audit:auditor,grp-control-owners:control_owner
```

The four role names, spelled exactly like this: `tech_risk`, `auditor`, `control_owner`, `read_only`. What each may do is in the README ("Roles").

Good to know:
- Anyone signed in whose groups aren't in the map gets **read only**.
- A misspelled role name is ignored without any error, so check the spelling.
- One group can appear more than once to give it two roles.
- `AUTH_MODE=sso` turns on group-based sign-in. `AUTH_MODE=open` is the interim setup described in "Before SSO is set up" below. Site security and the sign-in setup are owned by the team member responsible for it; check with them before changing either setting.
- `TECH_RISK_USERS` (sso mode) lists usernames that always get Tech Risk, for example `TECH_RISK_USERS=jdoe,asmith`. Use the username exactly as the SSO user header sends it; capitals don't matter. Those people get Tech Risk even if no AD group maps to it.

### Change what a role is allowed to do

All rules live in one table at the top of `apps/accounts/permissions.py` (`ROLES_ALLOWED`). The workflow rules (who can submit, approve, reject or withdraw a draft) live in `apps/core/workflow_rules.py`. Change the table and run the tests (Part 3). The test `apps/core/tests/test_url_access.py` lists which pages each role should reach. If you change a rule on purpose, update that list too.

### Links to the other apps (TRUST, Risk)

Set `TRUST_URL` and `RISK_URL` on the hosting platform. The set is three apps: TRUST, Risk and TRAC (owner, 15 Nov 2026: the initiative tracker and the SOX schedule are dropped; the calendar here is the one calendar). An empty value hides the link in the Apps menu.

### The Library's "how to check it", the audience filter and Proposed commands

- Each control can say, for each platform and each audience, where to look, what good looks like and what to keep. These are `checks` in the control file; the format and an example are in `content/controls/README.md`. The Library shows them under the control's row (collapsed, one per control, platform and audience) and the control page shows them under its steps. Nothing is drawn for a control that has none.
- The two audiences are **Platform admins** (you run or administer the platform) and **Platform users** (your team uses it). On a Library category page the "Show guidance for" pills filter every tagged line and check by audience. Tag a guidance line by starting it with `[Platform admins]` or `[Platform users]` (see `content/README.md`). A line with no tag is for both.
- A command nobody has confirmed shows "Proposed: pending confirmation from the platform owner." When the platform owner confirms one, add `confirmed_by: <name>` and `confirmed_on: YYYY-MM-DD` to the command in its control file and the mark comes off. Then run `python manage.py commands_to_confirm` to make `docs/COMMANDS_TO_CONFIRM.md` again (the list of commands, by platform, and whether each is Proposed or confirmed).

### The front page

The front page asks "What are you working on?", then shows two doors and a list of shortcuts. All its words live in three files in `content/home/`:

- `index.md` holds the heading (the `title:` line) and the short line under it.
- `doors.md` holds the words for the two doors. Door 1 (`build_title`, `build_line`, `build_button`) opens My system, or the Controls page until My system exists. Door 2 (`run_title`, `run_line`, `run_button`, `run_placeholder`) is a search box; `run_placeholder` is the example text shown inside it, such as `AM-03 or access review`. Each line is written as `name: words`.
- `shortcuts.md` holds the list under the doors. The `title:` line is its heading. Then write one shortcut per line as `Title | One line | /link/`. The link is a TRAC page (such as `/guides/cicd-pipelines/`) or an `https://` address. Blank lines and lines starting with `#` are ignored. To add a shortcut, add a line; to remove one, delete its line.

Run `.\trac.ps1 check` after a change. It names the file and the line when something is wrong. These files aren't stored in the database, so the change shows once the site restarts with the new files.

### The risk and control calendar

The calendar at `/calendar/` shows the events in one file, `content/calendar/events.yaml`, and the events people propose on the site. Anyone signed in can use **Add an event** (a short form with the same lines as below). The event is saved as Proposed and appears in the Review queue; it shows on the calendar only after Tech Risk approves it. Tech Risk can change or retire an approved event from its page, through the same approval. Nothing is deleted: a retired event leaves the calendar and stays in its history. The file's events stay as they are and the file is still read. `check_calendar` checks the file only. To add an event in the file instead:

1. Open `content/calendar/events.yaml`. The comments at the top show the format.
2. Add an entry under `events:` (take the `[]` off the `events:` line the first time):

```
events:
  - title: Quarterly access review
    date: 2027-01-15
    type: control_due
```

3. Run `.\trac.ps1 check` (it runs `check_calendar`, which names any event with a mistake). The calendar reads the file on every page load, so the change shows on the next page load.

| Line | Needed? | What it does |
|---|---|---|
| `title` | yes | The event's name. |
| `date` | yes | The day, written `YYYY-MM-DD` (the first day, for an event that lasts several days). |
| `type` | yes | One of the keys in the `types:` list at the top of the file. |
| `end` | no | The last day of an event that lasts several days. |
| `details` | no | A few plain sentences. `[link text](/guides/)` makes a link. |
| `link` | no | A TRAC page starting with `/`, or an `https://` address. It becomes a button in the pop-up. |
| `repeats` | no | `monthly`, `quarterly` or `annual`. A repeat on a day the month lacks (the 31st) falls on the month's last day. |
| `on` | no | With `repeats: monthly`: the same weekday each month, like `on: second thursday` (first, second, third, fourth or last, then a weekday name; capitals don't matter). The `date` must be the first one, so a second Thursday starting 2027-01-14 is right and 2027-01-15 is reported. The pop-up says "Repeats on the second Thursday of each month". |
| `until` | no | The last day a repeating event can happen. |

#### The In progress list (beside the month)

The list shows controls and guidance on the way: each with its status (Wanted, In progress or Live), its TRAC control (or "<topic> · Proposed" while it has none), the owning team and the date the team expects it to go live. That date is also marked on the month (◇ expected, ✓ went live). Each box and its marker take the topic's color; the colors are the `.riskcal-topic-XX` lines in `static/css/riskcal.css` (Operations and jobs stays indigo). The filters above the month (Status, Topic, Team) narrow the list and the markers.

- **Anyone** can use **Propose an item**, or **Propose a change** on an item's page (a new date, Live, another run without an issue). Each goes to the Review queue; Tech Risk's approval is where it spot checks. Changes go one at a time.
- **A live item** stays on the list until the owning team reports **2 runs of the control without an issue** (a monthly control: 2 months; a quarterly one: 2 quarters, counted on the fiscal year that starts September 1). The number is in `RUNS_TO_SETTLE` in `apps/riskcal/models.py`.
- **Date changes** are kept in each item's History (Tech Risk and auditors). The page itself shows only the current date (owner, 16 Nov 2026).
- The list shows 10 items; "See all" opens `/calendar/in-progress/`, 10 to a page.

The `types:` list (key and label) can be changed too. Each type gets its own color, in list order, up to eight types. The calendar shows two years back and five years ahead.

#### Control due dates from a spreadsheet

Due dates kept in Excel can be loaded without retyping them:

1. Save the sheet as CSV (in Excel: Save As, "CSV UTF-8"). The first row holds these column names (see `content/calendar/control-dates.example.csv`):

| Column | Needed? | What it holds |
|---|---|---|
| `control_id` | yes | The control's ID from the RCM, like `MA-04`. |
| `period` | no | Words like `Q1 2027` or `Walkthrough period 2`. |
| `due_date` | yes | `YYYY-MM-DD`, or the forms Excel writes: `M/D/YYYY` and `MM/DD/YYYY`. |
| `note` | no | Plain text, shown as the event's details. |

2. Name the file `control-dates.csv` and put it in `content/calendar/`, next to `events.yaml`.
3. Run `.\trac.ps1 check`. It names any row with a mistake by its row number (the header is row 1); those rows are left out and the rest still show.
4. Reload the calendar page. It reads the file on every page load, so the rows show on the next page load.

Each row becomes a "Control due" event titled "MA-04 due" (with the period in brackets), whose button searches the site for the control ID. The names of the columns can be in any capitals, other columns are ignored and blank rows are skipped. The `control_due` type must stay in the `types:` list of `events.yaml`.

### Values you fill in later

Things that aren't known yet or can change at any time (the Access Control Policy link, the Tech Risk email address, the walkthrough dates) live in one file, `content/settings.yaml`. Each has a plain label, a kind (`link`, `email` or `text`) and a `value`. An empty value means "not set yet".

1. Open `content/settings.yaml` and find the value (the labels are plain names).
2. Type it between the quotes after `value:`. A link starts with `https://`.
3. Run `.\trac.ps1 check`. It says how many values are still waiting, and names a mistake if there is one.
4. Put the file on the site the same way as the other content files. The file is read again when it changes, so no sync or code change is needed.

Until a value is set, a page shows the words plainly with a small "(to be added)" next to them, never a broken link. To add a new value, copy an entry in the file, give it a new key and a label, then write it in content as described in `content/README.md`. The check fails if content uses a key that has no entry in the file.

### Diagrams

Diagrams are draw.io files in `content/diagrams/`, listed in `content/diagrams/diagrams.yaml`. The site shows them at `/diagrams/`, and on the Library page of each platform they name. Red and blue bubbles in a picture link to risk and control pages. To add or update one, follow `content/diagrams/README.md`, then run `.\trac.ps1 check` (it includes `check_diagrams`). The diagrams are read on every page load, so a change shows on the next page load. Nothing is stored in the database and there is no approval step. A picture can still ask the browser to load something from another site (an image, for example); if you want to stop that, add a Content-Security-Policy on the hosting platform.

### My system

My system (`/my-system/`) asks an engineer a few questions about their system and shows the risk areas and controls that apply, in order. Nothing is stored in the database: the answers are kept in the visitor's session, and the app is `apps/pathfinder`.

- **The questions** live in `content/my-system/questions.yaml`. Each has the `question` (a yes/no question), an optional `because` (the reason shown on the path, after "Because") and `shows` (the risk areas a Yes puts on the path, as the labels under `aspects` in `content/platforms/catalog.yaml`). A risk area no question names applies to every system. A No leaves the area out (the path lists it at the bottom), and an unanswered question keeps it in. Run `.\trac.ps1 check` after a change (it runs `check_my_system`, which names an unknown risk area or a missing field). The file is read when the site starts, so the change shows once the site restarts.
- **Ready and In progress.** A risk area on a path is Ready when every platform the visitor picked has published guidance for it (its own line under that heading in `content/platforms/<platform>.yaml`, or added in the site). With no platform picked, it is Ready when at least one category's published practices cover it. Otherwise it shows In progress. Drafts never count. The rule is one function, `is_ready` in `apps/pathfinder/paths.py`.
- **Controls on the path** are the published controls of the risk area's topic whose categories match the picked platforms' categories (or that are tagged to one of those platforms); with no platform picked, all of them.
- **Once a visitor has answered,** a bar under the top bar on every page says "Showing guidance for: ...", Library category pages open with their platforms switched on (a choice made on the page wins), and a control opened from the path ends with "Next on your path".

### Initiative lifecycle guide

Each stage of the **Initiative lifecycle** guide has its own link, for example `/guides/initiative-lifecycle/#stage-2-build-and-configure`. The part after `#` comes from the stage heading. If you rename a stage heading, that stage's link changes, so update any page that links to it. Editing anything else on the page is safe. In the starter content this guide is `content/guides/initiative-lifecycle.md`: keep the `## Stage N: ...` and `#### Item N: ...` headings and numbers as they are.

Each checklist item has its own link too: `#stage-<stage>-item-<n>`, for example `/guides/initiative-lifecycle/#stage-3-item-2`. It comes from a **Heading 4** that starts with "Item 2" inside the "Stage 3" section. If you add an item, add it at the end of that stage's list so the other numbers don't shift. (In `initiative-lifecycle.md`, the `#### Item N` lines are the source the tests use to check every item link.)

### Diagrams in guides

A diagram is a ```` ```mermaid ```` block of plain text in a guide file (format and rules: "Diagrams" in `content/README.md`). The site draws it with the Mermaid library in `static/vendor/mermaid/` (loaded only on pages that have a diagram). To update Mermaid, replace `mermaid.min.js` and its `LICENSE` with the files from the new release and run the tests, which include a browser check.

### Content files (guides, controls and risks)

TRAC codes are not the firm's SOX control IDs. TRAC's own guidance controls and risks use TRAC codes (for example `CM-01`, `AM-03`, `MO-02`, and risks like `R-CM-01`), which are deliberately different from the firm's SOX control IDs (`MC`, `MA`, `OP`), so the two can never be mixed up. The firm's SOX IDs appear only in the calendar's control due dates file.

Guides are Markdown files in `content/guides/`; controls and risks are YAML files in `content/controls/`; the platform list and the guidance for each category and platform are YAML files in `content/platforms/`. Formats and the full rules for how a sync behaves are in `content/README.md` and `content/controls/README.md`. The loop:

1. Edit a file.
2. `.\trac.ps1 check` (runs `check_content`: plain-word messages, changes nothing).
3. `.\trac.ps1 sync -DryRun`, then `.\trac.ps1 sync` (runs `sync_content --user <you>`). New items become drafts and changed items become proposed updates. Add `-Publish` to approve straight away; that works only in single-approver mode (`ALLOW_SELF_APPROVAL`).
4. If someone edited in the site, run `.\trac.ps1 export` (`export_content`) first so their edit comes into the files. Otherwise the sync skips that item and says so; `--force` replaces the site's version.

A control page has three cards: "Why you'd want this control", "How to build it" and, when the control has notes, "Choosing who performs and who reviews". The header shows only Preventive or Detective, and Key for key controls. The steps in "How to build it" can each carry how to do it, things to weigh when setting a threshold, the policy that sets it, the evidence to keep (and what it should show) and commands for pulling that evidence, one block per platform. A platform's block opens first for visitors who picked that platform on My system. Steps and notes are edited in the control's form or in the file (see `content/controls/README.md`). Method, frequency, level, owner, performer and reviewer roles, categories and platforms are still kept for the explorer, filters, the key controls page and My system. The control page shows only the platforms, as links under the title.

Also available one part at a time: `check_engine`, `sync_engine`, `check_guides`, `check_controls`, `check_platforms`, `sync_guides`, `sync_controls`, `sync_platforms`, `export_guides`, `export_controls`, `export_platforms`. If `$env:TRAC_USER` is not set, `sync` asks for your username.

The topics are in `apps/topics/management/commands/seed_topics.py`. The platforms and risk-area questions are in `content/platforms/catalog.yaml` (read by `seed_platforms`). Both only add what a site does not have yet, so once the site is live edit topics, platforms and questions in the site (Part 1).

### Refresh from the risk engine

The risk engine is the master list of risk drivers (RD01, RD02 ...) and of its own risks. TRAC keeps copies of the engine's files in `content/engine/` and shows them; it never changes them. Only the sample files ship with TRAC, so the first job is to replace them with the real ones.

1. Copy the engine's `driver_mapping.yaml` over `content/engine/driver_mapping.yaml`.
2. Copy the engine's `config/risks/*.yaml` over the files in `content/engine/risks/`. Delete any file there that the engine no longer has.
3. `.\trac.ps1 check`. It names the file and the risk for any mistake (for example a driver id that is not in the mapping).
4. `.\trac.ps1 sync -Publish`. New drivers become drafts (or publish at once with `-Publish` in single-approver mode), changed ones become proposed updates, and the engine's risks are replaced by the new copy.

Drivers cannot be added or edited in the site. TRAC's own details for a driver (title, category, owner role, leading and lagging indicators, and the TRAC risks it relates to) are written in one file, `content/drivers/drivers.json`. Edit it with any text editor, run check, then sync. The sync adds an empty entry for every new engine driver and never deletes one. An empty title shows as the id (RD01); an empty owner role shows as "Not assigned yet". The pages are Risks and controls → **Engine risks** and each driver's page. Details are in `content/README.md` and `content/engine/README.md`.

### Which risks a control addresses

Each control can list the risks it addresses (`addresses`: engine risk ids such as `air.ops.02`). It starts empty and is left out of the control files until the owner maps the controls. Edit it in the site (control → Edit → "Risks it addresses") or in the file; see `content/controls/README.md`. The ids are checked against `content/engine/risks/`, so refresh those files first (the engine's file is keyed by risk id, or each risk has an `id:` line). The published list of controls and their addresses is read-only at `/registers/controls.json`, for the Risk site. In `AUTH_MODE=sso` it needs the platform's sign-in headers like any page, so the Risk site's server cannot just call it. It has to come through the access add-on with a service identity (a service account) that sits in a group mapped to a TRAC role in `SSO_GROUP_ROLE_MAP`, for example `grp-risk-site:read_only`. Or the platform lets that one path (`/registers/controls.json`) through without sign-in. Without one of these the Risk site gets "403". The page is read only, so any role can read it.

### Wording and labels

| I want to change… | Edit |
|---|---|
| Guide section names (Build a system, Run a control, Get through a review, Reference) | `Section` in `apps/wiki/models.py` (change only the text in quotes, not the short key) |
| The one-line description under each section card | `SECTION_HINTS` in `apps/wiki/views_read.py` |
| Top menu items (Start, My system, Controls, Guides, Calendar, Help, and for Tech Risk only Risks and controls and Review queue) | `PRIMARY_NAV` in `apps/ui/templatetags/trac_ui.py` |
| The starting list of platforms and risk-area questions (new sites) | `content/platforms/catalog.yaml` (commented; run `.\trac.ps1 check` after) |
| Guidance for a category or platform, in bulk | `content/platforms/categories/<category>.yaml` and `content/platforms/<platform>.yaml` (format in `content/README.md`; bullets are lines starting with `- `) |
| Category names (Database, Identity…) | `Category` in `apps/platforms/categories.py` (text in quotes only) |

### How things look

Each kind of label, card or header is drawn in **one** template in `templates/components/`. Change that one file and every page follows. For example:

| Piece | Template |
|---|---|
| Platform pill (e.g. "GitHub Enterprise Server") | `platform_chip.html` |
| Status and coverage badges | `badge.html` |
| Section and type pills | `type_pill.html` |
| Category pill | `category_pill.html` |
| Page header band and breadcrumbs | `page_band.html`, `breadcrumbs.html` |
| Colored note boxes | `callout.html` |

Colors live in the CSS files in `static/css/`. Each file starts with a comment saying what belongs in it:
- `trac.css`: the main colors (top of the file, under `:root`), category colors (`.category-…`), and the shared pieces above
- `library.css`: guide section colors (`.library-section-…`)
- `topics.css`: topic pages and lifecycle colors
- `guidance.css`: Library and category pages, including the platform pills

#### The colors ("Slate blue") and the five style rules

The site uses one palette. Its colors are set once, at the top of `trac.css` under `:root`, and every other style refers to them by name, so changing a color there changes it everywhere. A test pins each value, so a change to the palette also means updating `apps/ui/tests/test_colors.py`.

| Use | Name in the file | Color |
|---|---|---|
| Page background | `--trac-canvas` | `#E4EAF1` |
| Cards and sidebar (the lightest color anywhere) | `--trac-paper` | `#F6F8FB` |
| Insets inside a card, table headers, opened detail | `--trac-panel` | `#EDF1F6` |
| Borders and dividers | `--trac-border` | `#C9D3DF` |
| Main text | `--trac-ink` | `#17212E` |
| Secondary text and labels | `--trac-ink-secondary` | `#4A5869` |
| Links, selected menu item, primary button | `--trac-accent` | `#2B5C8F` |
| Text on the accent color | `--trac-on-accent` | `#F6F8FB` |
| Top bar | `--trac-header` | `#1D2B3C` |
| Text on the top bar | `--trac-on-header` | `#EEF3F8` |
| Quieter text on the top bar | `--trac-header-muted` | `#B4C2D1` |
| Green (Ready, Published, Covered): fill and text | `--trac-green-fill`, `--trac-green-ink` | `#CDEBD8`, `#0F5A30` |
| Amber (In progress, In review, Partial): fill and text | `--trac-amber-fill`, `--trac-amber-ink` | `#FBE5AE`, `#6B4B00` |
| Red (Unmapped, errors): fill and text | `--trac-red-fill`, `--trac-red-ink` | `#F6C6C2`, `#8F1D16` |
| None (Draft, Retired, plain labels): fill and text | `--trac-none-fill`, `--trac-none-ink` | `#DCE3EB`, `#4A5869` |
| Elevated (SOX): fill and text | `--trac-elevated-fill`, `--trac-elevated-ink` | `#E6DFF7`, `#5B3FA8` |

The five rules, in plain words:

1. **Font and size.** The font is Inter and body text is 14 pixels. Numbers are bold. Inter's files are in `static/vendor/fonts/inter/` and load from the site itself, never from the internet.
2. **Cards.** Every card has rounded corners (12 pixels) and a thin 1 pixel border in the border color. No shadows and no gradients anywhere. (The colored strip down the left side of some cards is drawn inside the card.)
3. **Status is color plus words.** A status always shows a pale fill with dark text of the same color, and the word is always there too (Ready, In progress, and so on). Color alone never carries the meaning.
4. **Selected means outlined.** A selected item (a switched-on filter chip, platform pill, My system answer, calendar type chip, or the open status tab) gets a 3 pixel outline in the main text color, on top of its tick mark or bold text. The one exception is the selected item in the top menu bar, which is dark: it is shown by the accent color fill and bold text.
5. **No pure white.** The lightest color is the card color (`--trac-paper`). Don't write `#fff`, `#ffffff` or `white` in any CSS file; the tests fail if you do. The page also overrides Bootstrap's white (form fields, menus, pop-ups, tables), so a new Bootstrap part needs a look.

The category colors (`.category-…`) and a few type words (Preventive, Detective, Manual) keep their own colors, because they say what kind of thing something is, not what state it is in. They still have to be readable on the card and page colors.

After changing a color, run the tests. One test checks that every text color is readable on its background and names the one that isn't.

To see every shared piece on one page, open `/ui/gallery/`. A test fails if a new shared piece is added without a sample there.

### Code layout

The folder map is in [docs/HOW_TRAC_WORKS.md](docs/HOW_TRAC_WORKS.md).

Shared template tags are in two files: `apps/ui/templatetags/trac_ui.py` (layout pieces) and `apps/ui/templatetags/trac_labels.py` (pills, badges, chips). Each file lists its contents at the top.

---

## Part 3: Checking nothing broke

From the project folder in PowerShell:

```powershell
.\trac.ps1 test
```

Every line should end in dots and the last line should say `passed`. If something fails, the output names the test and the file. The tests also check that:
- each role can reach only what it should
- colors stay readable (contrast)
- pages don't get slower as content grows

`.\trac.ps1 demo` fills a demo database with published demo content (see the README). Run the site locally with `.\trac.ps1 run`. The component gallery at `/ui/gallery/` shows every shared piece of the page (pills, badges, cards) in one place, which is a quick way to check a styling change. If something fails and you are not sure why, see "If something breaks" in docs/HOW_TRAC_WORKS.md.

## Going live (first time only)

Work through these in order. Steps 1 to 3 are for whoever deploys and secures the site. For a quick start with one admin, use "Going live tomorrow (one admin)" below instead.

1. **Settings on the hosting platform:** `DJANGO_SETTINGS_MODULE=config.settings.prod`, a long random `SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` (the site's address), `SSO_GROUP_ROLE_MAP` with the real AD groups, and the `TRUST_URL` and `RISK_URL` links. See the README for the full list.
2. **Deploy.** Database changes run on their own at each release. Check that the platform also runs `python manage.py collectstatic --noinput` while building; without it the site has no styling.
3. **Sign-in.** Before anyone outside the build team gets the link, either set `AUTH_MODE=sso`, or stay on `AUTH_MODE=open` with `OPEN_MODE_ROLE=read_only` (visitors only read and comment; see below). Never leave `OPEN_MODE_ROLE=tech_risk` on a shared site: `python manage.py check` warns with `trac.W002`. With SSO, make sure `ALLOW_SELF_APPROVAL` is `false` or not set. The security owner also decides on HTTPS redirect, HSTS and the `/admin/` page (`python manage.py check --deploy` lists them).
4. **Two Tech Risk people sign in once.** Changes need a second person to approve them (or use single-approver mode, below).
5. **Load the starting content:** `python manage.py setup_trac --user <your username>`. It adds topics, platforms, the starter guides and the controls and risks from the content files. Guides arrive as drafts.
6. **Review and approve the drafts** in Guides. Fill in anything marked "to be confirmed".
7. **Add your own content:** controls and risks; the risk engine's real files (see "Refresh from the risk engine"); drivers.json details; guidance for each category and platform; and your existing guides (paste them into New page).
8. **Try it as each role** (Tech Risk, auditor, control owner, read only) with a test account in each AD group.

### Going live tomorrow (one admin)

Set these on the hosting platform (names exactly as written; replace the values in angle brackets):

```
DJANGO_SETTINGS_MODULE=config.settings.prod
SECRET_KEY=<long random text>
DATABASE_URL=<Postgres connection string>
ALLOWED_HOSTS=<site host name>
CSRF_TRUSTED_ORIGINS=https://<site host name>
AUTH_MODE=open
OPEN_MODE_ROLE=read_only
ALLOW_SELF_APPROVAL=true
```

Then, from the project folder in PowerShell (with `DATABASE_URL` and the settings above set in the same window):

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py setup_trac --user <your username>
```

1. `createsuperuser` makes your account (pick your own username and a strong password). Don't start the username with `open-`; that prefix is reserved for visitors.
2. `setup_trac --user` loads the starting content as drafts from your account.
3. Open the site, scroll to the footer and click **Tech Risk sign-in**. Sign in with the account from step 1.
4. Approve the drafts (Guides). With `ALLOW_SELF_APPROVAL=true` you can approve your own changes.
5. Share the link. Everyone else reads and comments; you answer comments in the Review queue.

The site must be served over HTTPS, because your password and session cookie travel over it. The platform normally does this; check the address starts with `https://`. There is no limit on wrong password attempts yet.

## Running TRAC on the platform (Kubernetes)

The platform team supplies the image; we run our code on it. What the platform needs from us is in the project folder:

- `requirements.txt`: the Python packages to install (Python 3.12, see `.python-version`).
- `Procfile`: `web: sh docker/start.sh`, the one command that starts TRAC.

The database is a separate Postgres server, not inside the pod. The guides, controls and platform guidance come from the `content/` folder that is deployed with the code.

(`Dockerfile` is a reference image for testing on your own machine, or if the platform ever asks us for one. It isn't needed when the platform supplies the image.)

### Updating content

1. Edit the files in `content/` (see "Content files" in Part 2). Optional but quicker: run `.\trac.ps1 check` on your machine first.
2. Deploy the new version of the code the usual way for the platform.
3. When the pod starts, it checks the files and publishes the changes on its own. The pod log shows each step, for example "Writing a runbook: published an update".

Edit content **only in the files**, not in the site's editor. The files are the source of truth, and an edit made in the site would not flow back into them. (`export` writes inside the pod and is lost when it is replaced.)

If the check finds a mistake, the pod still starts with the previous content and the log says what to fix (lines starting with `!!`).

### What the pod does each time it starts

`docker/start.sh`, in order: uses the live-site settings (`config.settings.prod`) unless `DJANGO_SETTINGS_MODULE` says otherwise; prepares the styling files (a buildpack's own build step can't, because it runs before the settings are available); updates the database; creates the admin account the first time; adds any new topics and platforms; checks the content files; if they pass, syncs them into the site (published straight away when `ALLOW_SELF_APPROVAL=true`, otherwise as proposed updates to approve); then starts the web server on port 8000.

### Settings

Set these on the pod; put `SECRET_KEY`, `DATABASE_URL` and `TRAC_ADMIN_PASSWORD` in a Kubernetes Secret.

| Setting | Value |
|---|---|
| `SECRET_KEY` | Long random text |
| `DATABASE_URL` | Postgres connection string |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | The site's host name (`https://<host>` for the second) |
| `AUTH_MODE`, `OPEN_MODE_ROLE` | `open` and `read_only` until SSO is set up |
| `ALLOW_SELF_APPROVAL` | `true` while you are the only admin, so changes publish on start-up |
| `TRAC_ADMIN_USER` | Your admin username. The start-up sync runs as this account |
| `TRAC_ADMIN_PASSWORD` | Needed only for the first start, to create the account. You can remove it afterwards |
| `WEB_WORKERS` | Optional, default 3 |

### Kubernetes notes for whoever runs the cluster

- Run **one replica**. Start-up updates the database and syncs content, so two pods starting together could clash.
- Health check: `GET /health/` returns 200. Give the first start a few minutes before the probe gives up (start-up probe), because the first sync loads everything.
- The site expects HTTPS in front of it (the ingress) and reads `X-Forwarded-Proto`.
- TRAC listens on port 8000 (or `PORT` if the platform sets it).

A minimal example:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: trac
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels: {app: trac}
  template:
    metadata:
      labels: {app: trac}
    spec:
      containers:
        - name: trac
          image: <the platform's image with TRAC deployed>
          ports: [{containerPort: 8000}]
          envFrom:
            - secretRef: {name: trac-secrets}      # SECRET_KEY, DATABASE_URL, TRAC_ADMIN_PASSWORD
            - configMapRef: {name: trac-settings}  # everything else in the table above
          startupProbe:
            httpGet: {path: /health/, port: 8000}
            periodSeconds: 10
            failureThreshold: 30
          readinessProbe:
            httpGet: {path: /health/, port: 8000}
```

## Before SSO is set up

Until real sign-in is ready, TRAC runs in `open` mode with one admin (you) and everyone else read only.

- **Visitors** (`AUTH_MODE=open`, `OPEN_MODE_ROLE=read_only`): nobody signs in. Everyone who opens the link can read every guide and page and leave comments. They can't edit anything and can't pick a role. The top bar shows **Read only** and **Add your name**; adding a name is optional and only puts it next to their comments (`/accounts/login/`).
- **You (the admin):** create your account once with `python manage.py createsuperuser`. A superuser always has the Tech Risk role. Then click **Tech Risk sign-in** in the footer (`/accounts/staff/`) and sign in with your username and password. **Sign out** in the top bar returns the browser to a normal visitor. Only Tech Risk accounts can sign in on that page. To add a second admin, run `createsuperuser` again.
- **`OPEN_MODE_ROLE`**: the role every visitor has (default `read_only`). Leave it as `read_only` on a shared site. While it is anything else, `python manage.py check` prints warning `trac.W002`. For local work only, `config.settings.dev` sets it to `tech_risk` so you can edit without signing in.
- **`ALLOW_SELF_APPROVAL=true`**: single-approver mode. One Tech Risk person can approve or reject their own proposal. The rule is in one place, `apps/core/workflow_rules.py`. While it is on, `python manage.py check` prints warning `trac.W001`. Turn it off once a second Tech Risk approver has access.
- **Over HTTPS only:** serve the site over HTTPS, because the password page sends your password to the site.

When SSO is ready, set `AUTH_MODE=sso`. The footer link and the password page go away. Everyone whose groups map to no role is read only. List yourself in `TECH_RISK_USERS` (your username as the SSO header sends it) to keep Tech Risk even without an AD group, and map the real groups in `SSO_GROUP_ROLE_MAP`.
