---
title: What good evidence looks like
section: run
order: 0
---
Evidence answers one question for someone who wasn't there: did this control do what it says, for everything it covers, for the whole time? That someone might be a reviewer next month or an auditor next year, and all they have is what you kept. Everything in this guide follows from that question.

## Start with what you need to prove

Before you save anything, say in one sentence what the control claims. The claim tells you two things: whether you're proving something about a moment or about a period, and what "everything" means.

- **Access:** "Only the database team holds sysadmin on the payments SQL Server." That's a moment: who holds the role on a given date. Everything means every member of the role, including groups and disabled logins.
- **Change:** "Every production deployment last quarter had an approval before it went out." That's a period, and everything means every deployment between the first and last day of the quarter, not only the ones that had a ticket.
- **Jobs:** "Every failed job run in March was investigated and resolved." Also a period. Everything means every failed run in the scheduler's own history, not only the ones someone noticed.

Once you can write the claim, most of what follows is mechanical.

## A moment or a period

Most evidence is one of two kinds, and they need different things.

**Point-in-time evidence** shows how something stood at one moment: a setting, a password policy, who is in an admin group today. It needs when it was taken, which system it came from, and proof that it's the whole thing rather than a filtered list or a cropped view.

**Period evidence** shows everything that happened between two dates: every change, every new account, every failed job. It needs the start and end dates, the full population for that period, and a way to show nothing is missing. That can be a count that ties back to the source system, the query kept with its output so anyone can rerun it, or a sequence of run or ticket numbers with no gaps.

| Kind of evidence | What it proves | What it must show |
|---|---|---|
| Point in time | How something stood at one moment | The date and time, the system, and that nothing was left out |
| Period | Everything that happened between two dates | The start and end dates, the full population, and a completeness check |

The classic trap is mixing the two up. An export of a group's members taken today proves who is in the group today. It can't prove who was in it three months ago, when the control ran, because people have joined and left since. So point-in-time evidence has to be collected when the control runs, not when someone asks for it. Period evidence is more forgiving, since history can often be queried later, but logs and job history roll off, so don't count on it.

## Collect it from the system, not from memory

The strongest evidence comes straight from the system with little handling. Prefer a query, export or API call over a screenshot, and keep the query or command with its output so someone else can see exactly what was asked and run it again. Keep the raw output untouched and do any working on a copy. If you filter, for example to set aside service accounts the control doesn't cover, say what you filtered and why, in the same place as the evidence. When a screenshot really is the only way, capture the full window with the system name or address and the date and time visible.

Here's what that looks like for one point-in-time check: who holds the sysadmin role on a SQL Server instance. The query only reads:

    SELECT sp.name, sp.type_desc, sp.is_disabled
    FROM sys.server_role_members AS rm
    JOIN sys.server_principals AS r ON r.principal_id = rm.role_principal_id
    JOIN sys.server_principals AS sp ON sp.principal_id = rm.member_principal_id
    WHERE r.name = 'sysadmin'
    ORDER BY sp.name;

Save one file that holds the query exactly as run, the server and instance name, the date and time it ran, who ran it, the output as returned, and the row count. Running `SELECT @@SERVERNAME, SYSDATETIME(), SUSER_SNAME();` in the same session puts the server, the time and the account into the output itself, so nobody has to take your word for them.

## The attributes, and why each one matters

Whatever the evidence is, a reader asks the same handful of questions. If the evidence answers them on its own, nobody has to come back to you.

| Attribute | The question it answers | An easy way to show it |
|---|---|---|
| Where it came from | Which system is this from? | The server or system name in the output, or the query with its connection |
| When, or the period it covers | When was this true? | The run date and time; for a period, the start and end dates in the query and the file name |
| Complete | Is anything missing? | A row count that matches the source, with any filter written down |
| Who collected it | Who produced this? | The account that ran the query, or a named person in a note beside it |
| Not altered | Has it changed since? | The raw output kept as produced, with any working done on a copy |
| What was done with it | What did anyone decide? | The review notes, tickets or sign-off, pointing back to this file |

Dates are never changed after the fact. Evidence that's late is a problem you can explain; evidence that's been backdated is a serious integrity problem.

## When the evidence is a review

A review is evidence of a decision, so it has to show what the decision was based on as well as the outcome. Keep what was reviewed, with its source and the date it was pulled, and who reviewed it and when. Say what each item was checked against, such as the approved access list or the change ticket. Record a decision on every item, not only the exceptions, so it's clear nothing was skipped. For each flagged item, show what happened next: the ticket, the fix and the date it closed. Then sign it off. A sign-off that says "reviewed" with nothing behind it only tells the reader that someone clicked a button.

## Common ways evidence fails

**The export taken at audit time.** A list pulled when the request arrives shows today, not the day the control ran.

**The filtered list with no note.** If rows were removed and nobody wrote down which ones or why, the reader can't tell a reasonable exclusion from a hidden problem.

**The count that doesn't match the source.** Two hundred changes in the system and 187 in the evidence means someone now has to explain thirteen. Check the count before you file it.

**The screenshot with no date.** Without the date, the time and the system name, a screenshot could be from anywhere, at any time.

**The sign-off with no record of what was looked at.** A name and a date prove someone was there, not what they checked.

**The evidence that answers a different question.** Before you send anything, check it matches the period and the items that were asked for.

Where evidence is kept, and for how long, follows the firm's [records retention schedule](#todo-records-retention-schedule).

If you're unsure, Tech Risk can help.
