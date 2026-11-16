# Content files: controls and risks

These YAML files hold the controls and risks for TRAC, one file per topic (for example `change-management.yaml`). Each is plain text you can open in any editor. They are the place to update controls and risks in bulk; the site is where people read them and where drafts are approved.

## The loop

TRAC codes are not the firm's SOX control IDs. TRAC's own guidance controls and risks use TRAC codes (for example `CM-01`, `AM-03`, `MO-02`, and risks like `R-CM-01`), which are deliberately different from the firm's SOX control IDs (`MC`, `MA`, `OP`), so the two can never be mixed up.

Edit the file, then check and sync with `.\trac.ps1 check` and `.\trac.ps1 sync` (add `-DryRun` to preview, `-Publish` in single-approver mode). How a sync decides what to do (new, unchanged, in progress, edited in the site, update), and what `--force` and the export do, is explained once in `content/README.md`.

Every control and risk has a TRAC `id` (for example `CM-01` or `R-CM-01`), and the site finds it by that ID. A changed entry becomes a proposed change ("Updated from content/controls/..."), and a control's risks, platforms and links follow the file. The export keeps the comment block at the top of the file but not comments written inside it.

You can change a title freely, because the ID stays the same. To change an ID, edit the `id` line (and any `covered_by` line that points to it); the next sync gives the same control the new ID. Change the ID or the title in one sync, not both at once, or the site treats it as a new item.

## What is in a file

The comment block at the top of each file explains every field in one line. In short:

- `topic`: the topic name, exactly as on the site.
- `risks`: each has a TRAC `id`, a title, a plain statement (shown on the control page under "What could go wrong"), an owner role, a stage (or a theme) and `covered_by`, the controls that reduce it, with `coverage` (full or partial) and a one-line `why`.
- `controls`: each has a TRAC `id` (risks point at it in `covered_by`, from any topic's file), a title, `why` (the benefit), `applies_when` (when the control fits), nature, method, frequency, its level (key, non-key, compensating or supporting; most important first, see levels.yaml), owner, performer and reviewer roles, stage or theme, categories, optional platforms, `steps`, optional `choosing_people` and optional references (each a `label` and a `link`: a web address, or a page on TRAC starting with `/`, such as `/guides/worked-example-1-access-review/`; the worked example parts are linked this way).

The control page shows the title, Preventive or Detective (and Key for key controls), then three cards: why you'd want the control (`why` and `applies_when`), how to build it (`steps`) and, if you wrote them, notes on choosing who performs and who reviews (`choosing_people`). Method, frequency, level, owner, roles, categories and platforms stay in the file because the explorer, the filters, the key controls page and My system use them.

### Steps: how to build it

`steps` is the order a team would build the control in. Write four to seven. Each step is one entry; only `do` is required, and everything else is there when it helps:

- `do` (required): a short instruction as a title, such as "List your jobs."
- `how`: one to three plain sentences on doing it and why it matters.
- `weigh`: a list of things to consider when this step sets a threshold or a timing. It shows as "Consider these when setting your thresholds:". Don't put figures here.
- `policy`: the firm policy that sets it. A `[text](/page/)` or `[text](#todo-name)` link works here. It shows as "Set by: ...".
- `evidence`: what to keep. `keep` (required once you write `evidence`) is the thing to save, in one line. `shows` is a list of what it must show, such as the date it was pulled, the system it came from, the period it covers or a record count. Plain text after `evidence:` is not allowed.
- `commands`: the actual query or command. One entry per platform, with `platform` (named exactly as on the site) and `code` required, and a `note` if useful. Each shows as a collapsible block, and a visitor's My system platforms open first. A platform name the site doesn't have is a warning, not an error. Three optional lines: `audience` (`Platform admins` or `Platform users`; no line counts as Platform users), and `confirmed_by` and `confirmed_on` (see "Commands nobody has confirmed" below).
- `checks`: the Library's "how to check it" (see "How to check it" below).

Keys can come in any order in your file; the export writes them as do, how, weigh, policy, evidence, commands, checks. A key that isn't listed here fails the check and the message names the file, the control and the step number. The old step keys `who` and `part`, and the old `criteria` and `timings` lists, are gone.

Here is a trimmed example with two steps:

```yaml
- id: MO-02
  title: Job failures are monitored, investigated and resolved
  why: >-
    A failed or missed job can leave a report short of data with no visible error. This control
    turns a silent gap into a problem someone fixes.
  applies_when:
    - Your team runs scheduled jobs, wherever they run.
  steps:
    - do: Keep an inventory of your scheduled jobs.
      how: >-
        Pull every scheduled job from the scheduler itself, so the list is complete. Recommended
        attributes to track for each job include its name, where it runs, its owner and its rating.
      evidence:
        keep: The job inventory
        shows:
          - The date it was pulled and the scheduler it came from
          - Every job, including disabled ones, with a named owner
      commands:
        - platform: SQL Server
          note: Lists every SQL Server Agent job on the instance.
          code: |
            SELECT name, enabled, date_created, date_modified
            FROM msdb.dbo.sysjobs
            ORDER BY name;
    - do: Write down how quickly each rating gets addressed.
      how: Your team writes its own time for each rating in the inventory.
      weigh:
        - When the next job or report needs this data
        - Who is affected downstream, and whether they can be told early
        - What the system's BCP tier implies for how late its data can be
  choosing_people:
    performer:
      - Sees the alerts as part of their daily work
      - Has the access to rerun a job
    reviewer:
      - Doesn't operate the jobs
      - Has the standing to get a fix prioritized
    small_team: If no one is independent, have someone from another team look at a sample.
```

Write `code: |` and indent the lines under it, so the code keeps its line breaks. Evidence should be specific: name the thing and what it must show. A period needs the period covered and a count that ties back to the source; a point-in-time pull needs the date and the system.

### How to check it (`checks`)

One pattern for every control. For each platform the control applies to, and each audience, write three short parts, always in this order:

1. `where`: the screen, report or command to look at.
2. `good`: a list of specific points someone can check, such as "Every job in the inventory has a named owner."
3. `keep`: the evidence to save, in one line, with `shows` listing what it must show (the date, the source, who).

Plus `platform` (named as on the site) and `audience`. No times anywhere: the team writes down its own. Put the checks in one final step of the control ("Check it on each platform."), or in any step where they fit; the Library gathers them from all steps. Write only the parts you have; a part with nothing to say is left out and nothing is drawn for it.

```yaml
- do: Check it on each platform.
  checks:
    - platform: SQL Server
      audience: Platform users
      where: SQL Server Agent, then Jobs, in SQL Server Management Studio, or the query for this platform.
      good:
        - Every job in the inventory has a named owner.
        - Every failed run in the period has a record with its cause and its fix.
      keep: The list of failed runs for the period, and the record for each
      shows:
        - The period covered and the instance it came from
    - platform: SQL Server
      audience: Platform admins
      where: SQL Server Agent, then Alerts and Operators.
      good:
        - An operator receives job failure notifications.
```

The two audiences follow the firm's model: a platform team runs the platform with its own controls, and each team that uses the platform owns the controls over its own use.

- `Platform admins`: you run or administer the platform.
- `Platform users`: your team uses the platform.

Where a platform has both kinds of reader, write one check for each. The Library page shows each check under the control's row, and the control page shows it under its steps. The Library's commands for a check are the control's `commands` for the same platform and audience, so write `audience: Platform admins` on a command that admins run, and leave it off for the ones users run. Guidance lines in `content/platforms/` are tagged the same way (see `content/README.md`).

### Commands nobody has confirmed

A command shows with a "Proposed" mark and the words "Proposed: pending confirmation from the platform owner." until the owner of the platform has confirmed it works on the firm's version and returns what the step says. To record a confirmation, add two lines to the command:

```yaml
- platform: SQL Server
  confirmed_by: A. Admin
  confirmed_on: 2027-01-05
  code: |
    SELECT name FROM msdb.dbo.sysjobs;
```

Give both or neither. No lines means Proposed. Then run `manage.py commands_to_confirm` to make `docs/COMMANDS_TO_CONFIRM.md` again; it lists each command by platform and whether it is Proposed or confirmed.

### Choosing who performs and who reviews

`choosing_people` is optional, and every key in it is optional too: `performer` (a list of things to look for in the person who does the work), `reviewer` (the same for the person who checks it) and `small_team` (one line on what to do when no one is independent). The page adds the fixed line "Name a backup for both." under them.

The site never makes up an ID. A control or risk added in the site's own form asks for its ID too.

The four levels:
- `key`: relied on to address the risk, tested by auditors.
- `non-key`: matters, but is not relied on alone.
- `compensating`: covers for a control that is missing or not working, usually for a limited time.
- `supporting`: helps other controls work (documentation, baselines, tuning).

### Changing the levels (`levels.yaml`)

The levels live in one small file, `content/controls/levels.yaml`, listed most important first. Each entry has a `key` (what controls point at), a `label` (what readers see) and `open`:

- **To add a level**, add another entry in the place you want it to rank. Pages sort controls in this order.
- **To show a level by default**, set `open: true`. Levels with `open: false` are folded under a "More controls" box on library, platform and topic pages.
- **To rename a level** for readers, change its `label`. Leave `key` alone.
- The first level is also the one listed on the "Key controls for SOX in-scope apps" page.
- The old `key_control` and `scope` fields are gone. A file that still has them fails the check and says to use `level`.

`.\trac.ps1 check` also checks `levels.yaml` and names the problem (a repeated key, a missing label, or a missing `open`).

Two YAML habits to know:
- `yes` and `no` mean true and false. Write `in_sox_scope: true` for a risk.
- Indentation matters. Use spaces, never tabs, and keep list dashes lined up.

### Risks it addresses (`addresses`)

`addresses` is an optional list on a control: the ids of the risks teams are rated against (the risk engine's risks, such as `air.ops.02`). It is empty for now: the owner maps controls to risks later. **Leave the line out** of a control that addresses no risk yet. Don't write `addresses: []`; the export leaves empty lists out, so files stay tidy either way. When the mapping is made, it looks like this:

```yaml
  addresses:
    - air.ops.02
    - air.ops.03
```

Each id must be one the risk engine files in `content/engine/risks/` have, and each may appear once. `.\trac.ps1 check` says which id it can't find. The control page shows the list as "Risks it addresses", and each engine risk's entry on the Engine risks page lists "Controls that address this risk". Nothing is drawn when the list is empty. The list is edited like any other control field: in the site (Edit the control, "Risks it addresses"; a second Tech Risk person approves it) or in the file.

## Add a control

1. Open the topic's file. Copy an existing entry under `controls:` and paste it at the end.
2. Give it a new TRAC `id` for the topic and change the fields.
3. To cover a risk with it, add a line under that risk's `covered_by:` with the control's `id`, a coverage and a reason.
4. Run the check below.

## Check your changes before syncing

`.\trac.ps1 check` (`check_content`; `check_controls` for these files alone) reads every file and changes nothing. It prints a plain-word message naming the file and the field for each problem (for example an unknown category, an unknown stage or a mistyped value) and stops with an error. A platform the site doesn't have is a warning, and that platform is skipped. Topics and platforms must already exist, so run `seed_topics` and `seed_platforms` first (`setup_trac` does).
