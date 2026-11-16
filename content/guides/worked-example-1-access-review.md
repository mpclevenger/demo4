---
title: Worked example, part 1: a quarterly access review
section: run
order: 30
---
**This is an example.** The application, the people, the tickets and the dates are made up to show what the evidence looks like. It follows one application through the controls, in three parts: this one on access, then [part 2 on changes](/guides/worked-example-2-changes/) and [part 3 on jobs](/guides/worked-example-3-jobs/).

The application is a payments reconciliation application: it loads bank files each day and matches the payments to the ledger. Its application owner runs the quarterly access review for July to September 2026, and one developer moved to another team during the quarter, so the review also shows that the move was handled.

Controls used: [AM-04 Periodic user access review](/rcm/controls/AM-04/), [AM-05 Leavers and movers lose access on time](/rcm/controls/AM-05/), [AM-02 Access is granted only from an approved request](/rcm/controls/AM-02/), [AM-06 Service accounts are owned and restricted](/rcm/controls/AM-06/) and [AM-01 Roles are documented with their permissions](/rcm/controls/AM-01/).

## Who does what

The team that runs the application is a Platform user: it owns the review of access to its own application. Platform admins run the database server and the directory groups underneath it, and they supply platform-level lists on request. The Access Control Policy sets how often the review runs and how long it may take, so no timing is stated here.

## What the team did

1. **Pulled the full list from the system.** The application owner exported every account from the application's own user table, including service, vendor and disabled accounts, with each person's job or manager and last sign-in. This is step 1 of AM-04.
2. **Checked the list was complete.** The count was compared with the admin console and with the local logins on the database server. One local login was missing from the list and was added before the review. This is step 2 of AM-04.
3. **Sent each line to someone who knows the job.** Managers got their own people, the application owner got the service, vendor and disabled accounts, and the Head of Engineering got the application owner's own line. This is step 3 of AM-04.
4. **Got a keep or remove decision on every line.** Each reviewer recorded decisions from their own account. This is step 4 of AM-04.
5. **Removed what was marked and showed it was gone.** Each removal became a ticket, and a fresh list was pulled afterward. This is step 5 of AM-04.
6. **Signed off.** The control owner checked the list, the decisions, the self-review rule and the removals. This is step 6 of AM-04.
7. **Handled the mover.** One developer moved teams on 2026-08-10. HR's list of movers started the removal, the old write access was taken away, some read access stayed for a written handover reason with an end date, and the access needed in the new job was requested and approved on its own. This is AM-05 and AM-02.

## The evidence as it would look

Everything below is made up. Account names are placeholders, and people appear as roles.

#### The access list (AM-04 step 1)

Pulled 2026-10-05 09:40 from the application's user table, query saved as `access-list-2026Q3.sql`, by the application owner. Seven of 41 lines are shown.

| Account | Type | Access held | Job or manager | Last sign-in |
|---|---|---|---|---|
| acct-101 | Person | Recon-Developer | Developer, manager M1 | 2026-10-02 |
| acct-104 | Person | Recon-Reader | Developer on another team, manager M2 | 2026-09-02 |
| acct-110 | Person | Recon-Reader | Finance analyst, manager M3 | 2026-10-03 |
| acct-120 | Person, vendor | Recon-Reader | Vendor support contact, sponsor is the application owner | 2026-06-11 |
| acct-130 | Person, disabled | Recon-Reader | Former contractor | 2026-05-20 |
| svc-recon-load | Service | Write to loading tables | Owner: application owner. Used by the daily load job | 2026-10-05 |
| svc-recon-old | Service | Recon-Reader | No owner recorded | 2026-03-30 |

#### The completeness check (AM-04 step 2)

| Check | Result | Source | Done by and when |
|---|---|---|---|
| Accounts in the application's user table | 40 | Export in the first table | Application owner, 2026-10-05 |
| Accounts shown in the admin console | 40 | Admin console users page | Application owner, 2026-10-05 |
| Local logins on the database server | 4 found, 3 on the list | Server login query | Application owner, 2026-10-05 |
| Login not on the list | login-recon-tmp, added to the list | Server login query | Application owner, 2026-10-05 |
| Lines in the review | 41 (40 plus the added login) | Final list | Application owner, 2026-10-05 |

#### Who reviewed which lines (AM-04 step 3)

| Reviewer | Lines | Own access on their list? |
|---|---|---|
| Manager M1 | 12 | No |
| Manager M2 | 7 | No |
| Manager M3 | 8 | No |
| Application owner | 13 | No (own line moved) |
| Head of Engineering | 1 (the application owner's own access) | No |
| **Total** | **41** | |

#### The decisions (AM-04 step 4)

Seven of 41 lines are shown. Across all 41 lines: 36 keep and 5 remove.

| Account | Decision | Decided by | Date | Reason or ticket |
|---|---|---|---|---|
| acct-101 | Keep | Manager M1 | 2026-10-06 | Current developer |
| acct-104 | Remove | Application owner | 2026-10-06 | Handover access ended 2026-09-10 and was never removed. ACC-2201 |
| acct-110 | Keep | Manager M3 | 2026-10-07 | Needs the daily reports |
| acct-120 | Remove | Application owner | 2026-10-07 | Vendor support has ended. No sign-in since 2026-06-11. ACC-2202 |
| acct-130 | Remove | Application owner | 2026-10-07 | Disabled former contractor. ACC-2203 |
| svc-recon-load | Keep | Application owner | 2026-10-07 | Owner and purpose recorded |
| svc-recon-old | Remove | Application owner | 2026-10-07 | No owner and no use since 2026-03-30. ACC-2204. The other removal, login-recon-tmp, is ACC-2205 |

#### The removals and the fresh list (AM-04 step 5)

Fresh list pulled 2026-10-15 10:05 from the same user table, by the application owner: 36 lines (41 less 5 removals).

| Ticket | Account | Removed on | Done by | In the fresh list? |
|---|---|---|---|---|
| ACC-2201 | acct-104 | 2026-10-13 | Access administrator | No |
| ACC-2202 | acct-120 | 2026-10-13 | Access administrator | No |
| ACC-2203 | acct-130 | 2026-10-13 | Access administrator | No |
| ACC-2204 | svc-recon-old | 2026-10-14 | Access administrator | No |
| ACC-2205 | login-recon-tmp | 2026-10-14 | Database administrator | No |

#### The sign-off (AM-04 step 6)

Control owner, 2026-10-16. Review period 2026-07-01 to 2026-09-30. The list was complete (41 lines, with the one missing login added). 41 of 41 lines have a decision. No reviewer had their own access on their list. 5 of 5 removals were done and are absent from the fresh list. No items are open.

#### The mover (AM-05 steps 1 to 5)

HR's list of leavers and movers for July to September 2026, pulled from the HR system on 2026-10-01: 8 people (6 leavers and 2 movers, contractors included), which matches HR's own total for the period. One of the 2 movers had access to this application.

| Item | Record |
|---|---|
| Person | acct-104, a developer |
| HR move date | 2026-08-10, to another team |
| Removed | Recon-Developer (write access to reporting tables). Ticket ACC-2088, done 2026-08-19 by the access administrator. The ticket was raised on 2026-08-12 |
| Kept | Recon-Reader, for handover. Written reason: answering questions about the matching rules. Ends 2026-09-10. Approved by the application owner on 2026-08-10 |
| Removal compared with the Access Control Policy | Recorded as late, with the reason: the access administrator was away |
| Lookback | The reviewer searched the application's audit log for acct-104 from 2026-08-10 to 2026-08-19 on 2026-08-20: no write events. Reads only |
| Access in the new job | Request REQ-1190, approved by manager M2 and by the owner of the new system on 2026-08-12, granted on 2026-08-13 by the access administrator, who did not request or approve it (AM-02) |

The handover access that was meant to end on 2026-09-10 shows up again in the quarterly list above. The review caught it, and ACC-2201 removed it.

## Questions a reviewer would ask

#### About the list

- Was the list pulled from the system, and does it show the date, time and source?
- Does it include service, vendor, privileged and disabled accounts?
- Do two counts from different places agree? Was access outside the main list looked for, such as local logins?
- Does every line show a job or manager and a last sign-in?

#### About the decisions

- Does every line have a decision, made by the person named and from their own account?
- Did anyone review their own access?
- Why was unused or privileged access kept, where it was kept?
- Were decisions made inside the time the Access Control Policy sets, and where one was late, is the reason written down?

#### About the removals

- Does every remove decision have a ticket?
- After the work, is the access absent from a fresh list, not just the ticket closed?
- Is anything still open at sign-off, and who is chasing it?

#### About the mover

- Does the count of leavers and movers tie to HR's own total?
- Was the old access removed, and was that compared with the time the Access Control Policy sets?
- For access that stayed, is there a written reason, an approver and an end date? Did it end?
- Where access was removed late, was activity after the move date searched?
- Was the access in the new job requested and approved by two people before it was granted?

If you're unsure, Tech Risk can help.
