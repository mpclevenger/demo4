---
title: Timings your team sets
section: best_practice
order: 10
---
TRAC names the timings and alerts each control needs. Your team decides each one, or follows the firm policy that sets it, and writes it in your procedure. Each control page lists its own under "Timings your team sets".

## Five questions for any timing

These questions help you pick a timing you can defend. The answers push it shorter or longer.

- **What is the worst that happens in the gap?** The worse the outcome, the shorter the timing. A missed alert on a payments system that goes unread for a day can mean a fraud runs all day. A missed alert on a test system can wait.
- **How exposed is the system?** More exposure means a shorter timing. A system open to the internet, or one many people can change, needs faster action than a system few people can reach.
- **How fast would you notice by other means?** If something else would catch the problem soon, the timing can be longer. A nightly reconciliation that flags missing data soon after a job fails already covers part of the gap.
- **What limits the damage meanwhile?** Limits allow a longer timing. If a failed deployment cannot reach production without a second approval, a slow review of the failure does less harm.
- **What does doing it faster cost?** A cost that is high pushes the timing longer, unless the risk is high too. Patching a system that needs a full outage window is a real cost, so weigh it against how bad the gap would be.

## What the BCP tier tells you

Tier 0 and tier 1 systems are the most critical, so the same question usually gets a shorter answer there. Recovery time and data loss targets come with the tier. They bound the backup and recovery timings: you cannot back up less often than your data loss target allows, or plan a restore that takes longer than your recovery time target.

## Write down what you can meet

Auditors and reviewers test against what your procedure says. A timing you miss is a finding, even if it was stricter than the system needed.

- Choose a timing you can meet every time.
- Record who agreed it.
- Look at it again each year, or when the system changes.

## Timings by area

Each area lists the timings and alerts to decide, and what to weigh as you decide them.

#### Access

TRAC does not set or advise access timing. Follow the firm's [Access Control Policy](#todo-access-control-policy).

#### Change

Timings to decide:

- How soon an emergency change is reviewed afterward.
- How often deployed changes are compared with approved ones.
- How often direct database changes are reviewed.
- How many releases are spot-checked.

Weigh:

- How often you release.
- How many people can write to production.
- Whether the pipeline already blocks unapproved changes.

#### Vendors

Timings to decide:

- How often the vendor's SOC report is obtained and reviewed.

Weigh:

- When the vendor issues its report and the period it covers.
- How much your system relies on the vendor's controls.

#### Jobs and data transfers

Timings and alerts to decide:

- How often job changes are compared with approved requests.
- An alert when a job or transfer fails or does not start.
- How fast a failed job is fixed.
- When an open reject is escalated.

Weigh:

- When the next job or report needs the data.
- Who is affected downstream.
- Whether anyone is on call.

#### Logging and alerting

Timings and alerts to decide:

- How fast a stopped log feed is noticed.
- How fast an alert is triaged.
- How fast an alert is resolved and closed.

Weigh:

- What the logs are evidence for.
- How long a gap could run before it breaks another control.
- Who watches out of hours.

#### Vulnerabilities and patching

Timings to decide:

- How often scans run.
- How long a finding of each severity may stay open.

Weigh:

- Whether the system is reachable from the internet.
- What data it holds.
- How disruptive patching is.

#### Configuration

Timings to decide:

- How often live settings are compared with the baseline.

Weigh:

- How often settings change.
- Whether a tool can check continuously.

#### Backup and recovery

Timings and alerts to decide:

- How often each system is backed up.
- An alert when a backup fails.
- How fast a failed backup is fixed.
- How often a restore is tested.
- How often the recovery plan is exercised.

Weigh:

- The recovery targets that come with the BCP tier.
- How much recent work you can afford to lose.

## If a firm policy covers it

Follow the policy. Where the policy and your procedure differ, the policy wins. If you cannot meet it, see [When an exception is appropriate](/guides/when-an-exception-is-appropriate/).

If you're unsure, Tech Risk can help.
