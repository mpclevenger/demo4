---
title: Worked example, part 3: the job inventory and one failure
section: run
order: 32
---
**This is an example.** The application, the people, the jobs, the tickets, the dates and the times are made up to show what the evidence looks like. It is part 3 of 3, after [part 1 on access](/guides/worked-example-1-access-review/) and [part 2 on changes](/guides/worked-example-2-changes/).

The same payments reconciliation application runs four scheduled jobs. The team keeps an inventory of them with a rating for each, and in October 2026 the daily bank file load failed once and was handled.

Controls used: [MO-02 Job failures are monitored, investigated and resolved](/rcm/controls/MO-02/) and [MO-01 Changes to scheduled jobs go through change control](/rcm/controls/MO-01/).

## Who does what

The team that runs the application is a Platform user: it owns the inventory, the ratings and the failure records for its own jobs. Platform admins run the schedulers (SQL Server Agent, Windows scheduled tasks and the in-house scheduling application) and give the team the job lists and run history it asks for.

## A note on times

Tech Risk states no timing figures for jobs. Every time in this part, such as how quickly a failure is addressed, is the team's own written-down time, made up for this example. Each team writes its own in its inventory. See [Timings your team sets](/guides/timings-your-team-sets/) for the questions that help you choose.

## What the team did

1. **Kept an inventory.** The team pulled the job list from each scheduler and recorded the eight attributes for every job: job name; where it runs; the job's owner; what it does and what it feeds; its rating; how a failure is noticed and who is told; how quickly a failure is addressed (the team's own time); and where the record of a failure and its fix is kept (MO-02 step 1).
2. **Rated each job High, Medium or Low, and wrote down why.** The reason sits next to the rating, and the application owner agreed the ratings (MO-02 step 2).
3. **Made failures visible.** Each job raises an alert when it fails, does not start or runs long, and the inventory says who is told (MO-02 step 3).
4. **Wrote down how quickly each rating gets addressed.** Higher ratings are addressed sooner (MO-02 step 4).
5. **Kept a record of every failure.** Each failed run has a record with the cause, the fix and the date resolved, kept where the inventory says (MO-02 step 5).
6. **Handled one failure.** The bank file load failed on 2026-10-20. The fix changed the job, so it went through change control (MO-01 steps 3 to 5).
7. **Reviewed it.** A reviewer who does not operate the jobs checked the failures, the inventory and the ratings (MO-02 step 6, MO-01 step 6).

## The evidence as it would look

Everything below is made up. The job inventory was pulled on 2026-10-01 from the three schedulers and is shown in two tables because it has eight attributes.

#### The job inventory, part 1 of 2 (MO-02 step 1)

| Job name | Where it runs | The job's owner | What it does and what it feeds | Rating |
|---|---|---|---|---|
| recon-load-bank-files | SQL Server Agent on the production SQL Server | Application owner | Loads the daily bank files. Feeds recon-match-daily | High |
| recon-match-daily | In-house scheduling application | Application owner | Matches loaded payments to ledger entries. Feeds the exceptions report and the finance close | High |
| recon-exceptions-report | In-house scheduling application | Reconciliation team lead | Builds the daily list of unmatched payments for finance | Medium |
| recon-archive-old-files | Windows scheduled task on the file server | Reconciliation team lead | Moves processed bank files to the archive folder. Feeds nothing downstream | Low |

#### The job inventory, part 2 of 2 (MO-02 step 1)

| Job name | How a failure is noticed and who is told | How quickly a failure is addressed (the team's own time) | Where the record of a failure and its fix is kept |
|---|---|---|---|
| recon-load-bank-files | Scheduler failure alert pages the on-call developer. Backup: the application owner | Within 8 hours of the alert | Ticket project REC-OPS |
| recon-match-daily | Failure and long-run alerts from the in-house scheduler, whose logs go to Splunk, page the on-call developer | Within 8 hours of the alert | Ticket project REC-OPS |
| recon-exceptions-report | Alert to the team's queue, watched on working days. Backup: the team lead | By the end of the next working day | Ticket project REC-OPS |
| recon-archive-old-files | Alert to the team's queue, watched on working days | Within 5 working days | Ticket project REC-OPS |

#### The ratings, their reasons and the team's times (MO-02 steps 2 and 4)

Agreed by the application owner on 2026-09-28. The times are the team's own written-down times.

| Rating | Why | The team's own time to address a failure |
|---|---|---|
| High: recon-load-bank-files | Nothing downstream can run without it, and finance relies on the matching result each morning | Within 8 hours of the alert |
| High: recon-match-daily | Feeds the exceptions report and the finance close | Within 8 hours of the alert |
| Medium: recon-exceptions-report | Finance would notice a missing report, and can wait for it a day | By the end of the next working day |
| Low: recon-archive-old-files | Nothing downstream needs it. Files stay where they are until it runs | Within 5 working days |

#### The alert settings (MO-02 step 3)

Exported from the three schedulers on 2026-10-01. 4 of 4 jobs in the inventory are covered.

| Job name | Alert on failure | Alert if it does not start | Alert if it runs long | Sent to |
|---|---|---|---|---|
| recon-load-bank-files | Yes | Yes | Yes | On-call developer |
| recon-match-daily | Yes | Yes | Yes | On-call developer |
| recon-exceptions-report | Yes | Yes | No | Team queue |
| recon-archive-old-files | Yes | No | No | Team queue |

#### The failed runs in October 2026 (MO-02 step 5)

From the schedulers' own run history for 2026-10-01 to 2026-10-31: 3 failed runs. The ticket project holds 3 failure records. The counts match.

| Record | Job | Failed at | Rating | Cause | Fix | Resolved at | Within the team's time? |
|---|---|---|---|---|---|---|---|
| REC-OPS-214 | recon-exceptions-report | 2026-10-07 06:30 | Medium | Database timeout while building the report | Reran the job, which succeeded | 2026-10-07 09:15 | Yes |
| REC-OPS-221 | recon-load-bank-files | 2026-10-20 02:04 | High | The bank changed the position of the amount column, so the load step rejected the file | Changed the column mapping, then reloaded the file. See the failure below | 2026-10-20 09:40 | Yes |
| REC-OPS-228 | recon-archive-old-files | 2026-10-27 22:00 | Low | The archive folder was locked by a backup | Reran the job after the backup finished | 2026-10-28 08:10 | Yes |

#### The failure handled: REC-OPS-221, in order

| Time (2026-10-20) | What happened | Who |
|---|---|---|
| 02:04 | recon-load-bank-files failed. The alert paged the on-call developer | Scheduler |
| 02:12 | The page was acknowledged. The bank file was held and not edited by hand | On-call developer |
| 02:15 | recon-match-daily did not start, because it waits for the load job to succeed | Scheduler |
| 08:30 | Job change request JCR-3310 raised: map the amount column by its header, not by its position | On-call developer |
| 08:50 | JCR-3310 approved | Application owner (not the developer making the change) |
| 09:10 | The new mapping tested in the test environment against the last 3 bank files | On-call developer |
| 09:30 | Change applied to the job on the SQL Server | On-call developer |
| 09:35 | recon-load-bank-files rerun. The load finished at 09:40 | On-call developer |
| 09:40 | Comparison of the bank file and the loaded table: 1,206 records in the file, 1,206 loaded once, control total of amounts matched | On-call developer |
| 09:55 | recon-match-daily started | Scheduler |

The alert reached a person at 02:04 and the failure was resolved at 09:40, which is 7 hours 36 minutes later. The team's own written-down time for a High job is 8 hours from the alert.

#### Job changes in October, from the scheduler's own change history (MO-01 steps 3 to 5)

Pulled 2026-11-02 from the change history of the SQL Server Agent, the in-house scheduling application and Windows task scheduler: 2 changes.

| Job | Changed on | Changed by | Request | Approved by | Before and after kept? |
|---|---|---|---|---|---|
| recon-archive-old-files | 2026-10-02 | Developer A | JCR-3302 | Application owner | Yes |
| recon-load-bank-files | 2026-10-20 | On-call developer | JCR-3310 | Application owner | Yes. The job script before and after is attached to JCR-3310 |

#### The review (MO-02 step 6, MO-01 step 6)

Reviewer: Developer D, who does not operate the jobs. Date: 2026-11-04. Period: October 2026. Notes: 3 of 3 failures were handled within the team's own written times. All 4 jobs on the scheduler lists are in the inventory. The ratings still hold. 2 of 2 job changes match an approved request. No repeat failure in the month, so no root cause review was needed.

## Questions a reviewer would ask

#### About the inventory

- Was it pulled from the schedulers, and does it show the date and the scheduler each job came from?
- Does it include disabled jobs, and does every job have a named owner?
- Are all eight attributes filled in for every job?
- Are there jobs on a scheduler that are not in the inventory?

#### About the ratings and times

- Is there a reason next to each rating, and who agreed it and when?
- Does a higher rating get a shorter time?
- Where did the times come from, and has the team been able to meet them?

#### About the alerts

- Does every job in the inventory have a failure alert, or a reason it does not?
- Does the alert go to a queue or a person that someone watches, with cover when they are away?

#### About the failure

- Does the count of failed runs in the scheduler's history match the count of failure records?
- Does each record show the cause, the fix and when it was resolved?
- Was the time from alert to resolution inside the team's own written time?
- Was the missing data loaded once, and does a comparison show it?
- Did the fix go through a request approved by someone other than the person who made the change, with the before and after kept?
- Does the scheduler's own list of changes match the approved requests?

If you're unsure, Tech Risk can help.
