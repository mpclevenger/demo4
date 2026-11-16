---
title: Sending data for TRUST
section: run
order: 20
---
TRUST is the monthly scorecard of tech risk. Some of its numbers come from teams. This guide is for a team that will send numbers to TRUST from a small job of its own. It covers what is set up first, what the numbers look like, how the send works, and what comes back.

Sending numbers only stores them. A send never changes a score and never puts a metric on the scorecard. That means your team can start sending, and see what arrives, before anything is counted.

## Before you can send

Every metric has one intake record in TRUST. It holds what the metric is, who provides it, what is counted and how the numbers arrive. Tech Risk fills the record in. Your team does not need to touch it. Each record has a short ID, such as MI-001.

A record moves through three stages:

| Stage | What it means | Can your team send numbers? | Counts in a score? |
|---|---|---|---|
| Wanted | We want it and it isn't there yet. | No | No |
| In progress | Agreed and being built. | Yes | No |
| Measured | Counted and scored. | Yes | Yes, once the metric is added to the scorecard |

A new metric starts as Wanted. Tech Risk moves it to In progress once the details are agreed: what is counted, what it is measured against, the unit, which way is better, what ties each row to a team, the shape of the numbers, how often they are sent, how they arrive, and the service account that will send them. A metric moves to Measured by hand, after the usual metric approval.

What to ask Tech Risk for:

- A record for your metric, if there isn't one yet.
- Its move to In progress, so TRUST can take your numbers.
- The exact address and an example filled in for your metric. Tech Risk can see both when they open the record and look at "How to send".

## The two shapes

The record says which shape your metric uses. Your send should use the same one. Column names can be written in any capitals.

#### Totals

One row per team for the month. You work out the count and the total, and send both.

| Column | What goes in it |
|---|---|
| `intake_id` | The record, for example `MI-001`. |
| `month` | The month the numbers are for, written `YYYY-MM`. |
| `key_type` | `application`, `repository` or `person`. It should match the record. |
| `key` | The application's ID or name, the repository, or the person's SAM account name. |
| `count` | A whole number: how many were counted. |
| `total` | A whole number: how many there were. It is not less than `count`. |
| `as_of` | The date the numbers were taken, written `YYYY-MM-DD`. |

Example, as a CSV file:

```
intake_id,month,key_type,key,count,total,as_of
MI-001,2026-10,application,APP-1234,3,4,2026-10-31
MI-001,2026-10,application,APP-5678,10,10,2026-10-31
```

#### Items

One row per item. Items is the shape to prefer, because your team can then see what sits behind its number. TRUST works out the count and total for each team: the count is the number of rows marked `yes`, and the total is the number of rows. Four rows for one application, three of them `yes`, make 3 counted out of 4.

| Column | What goes in it |
|---|---|
| `intake_id`, `month`, `key_type`, `key`, `as_of` | The same as in Totals. |
| `item_id` | Your own reference for the item, such as a ticket, a test or a server. Each one appears once per send. |
| `item_name` | What a person would call it. |
| `counted` | `yes` if it counts toward the number, `no` if not. |

Example, as a CSV file:

```
intake_id,month,item_id,item_name,key_type,key,counted,as_of
MI-002,2026-10,RT-17,Restore test of Payments DB,application,APP-1234,yes,2026-10-28
MI-002,2026-10,RT-18,Restore test of Ledger DB,application,APP-1234,no,2026-10-28
```

The names above are examples only.

## How your service account gets access

TRUST has no sign-in of its own, and your team doesn't use a password or token. Access works through the company's add-on and AD groups, the same as the rest of TRUST.

1. Tech Risk writes your service account's SAM account name on the record, for example `svc-example-sender`.
2. Your service account is added to the data senders' AD group.
3. The add-on passes the account name to TRUST on every request.

When access is switched on, the account you send from should be the one named on the record. TRUST refuses a send from any other account. A data sender can send numbers and do nothing else. It can't read the scorecard or the intake list.

How the service account signs in to the add-on is set up by whoever runs the add-on. TRUST only sees the account name it passes on.

On the TEST site, where access is open, anyone can send. The send should then also carry a name in a `by` field, so the record shows who sent it.

## How to send

Send a POST request to your TRUST site, at `/api/metric-values`. Use the full address of the site, for example `https://trust.example.com/api/metric-values`. The request carries the header `X-TRUST: 1`.

There are two ways to send the same rows:

- **JSON.** A body with the record, the month, the shape and the rows.
- **A CSV file.** A file upload in the field `file`. The first line holds the column names. Commas, semicolons, tabs and pipes all work as separators. The record and month can be read from the rows. If you name a shape, it should match the record.

The JSON body looks like this:

```json
{
  "intake_id": "MI-001",
  "month": "2026-10",
  "shape": "totals",
  "rows": [
    {"intake_id": "MI-001", "month": "2026-10", "key_type": "application", "key": "APP-1234", "count": 3, "total": 4, "as_of": "2026-10-31"}
  ]
}
```

One send is for one record and one month. If you send again for the same record and month, the second send replaces the first on screen. The first stays in the history.

## What comes back

The answer is always JSON, with a plain message. When some rows are kept and some are set aside, it reads like this:

```json
{
  "ok": true,
  "message": "Received. 1 row kept, 1 row was set aside (see the reasons below). Nothing here changes any score.",
  "rows_received": 2,
  "rows_kept": 1,
  "rows_set_aside": 1,
  "set_aside": [{"row_number": 2, "reason": "The count (9) is more than the total (7). The count is the part of the total that was counted.", "row": {"key": "APP-5678", "count": 9, "total": 7}}],
  "totals": [{"key_type": "application", "key": "APP-1234", "count": 3, "total": 4, "as_of": "2026-10-31"}],
  "replaced_earlier_send": false,
  "scored": false
}
```

The answer also names the record, the month, the shape, the send number, when it was received and from which account. These are the parts to look at:

- `rows_kept` and `rows_set_aside` say how many rows went each way.
- `set_aside` lists each row set aside, its position in your file and the reason in plain words.
- `totals` shows the count and total for each team, as TRUST worked them out.
- `scored` is always `false`.

A row that can't be kept is never dropped quietly. It is set aside with its reason, and the rest of the send is stored.

## Why a send is refused

A whole send is refused, and nothing is stored, when:

- The record doesn't exist. Check the `intake_id`.
- The record is still Wanted. The answer asks you to have Tech Risk move it to In progress.
- The month isn't written `YYYY-MM`.
- The shape you name isn't the record's shape.
- There are no rows, or the body isn't JSON in the form shown above.
- A send has more than 200,000 rows, or a file is bigger than TRUST accepts. Send it in smaller parts.
- Your account isn't the service account on the record, or the record has no service account yet. This answer comes back with a 403 status. The other refusals above come back with a 400.
- Your account isn't in the data senders' group. TRUST says the role doesn't allow it, with a 403 status, before it looks at anything else.

Each row is also checked on its own. A row is set aside, with its reason, when:

1. `count` or `total` isn't a whole number, or the count is more than the total (Totals).
2. `counted` isn't `yes` or `no` (Items).
3. The month isn't written `YYYY-MM`, or isn't the month of the send.
4. `key_type` isn't `application`, `repository` or `person`, or isn't the one on the record.
5. `as_of` isn't a real date written `YYYY-MM-DD`.
6. A team appears twice in one send (Totals), or an `item_id` appears twice (Items).
7. A column is empty, or the row's `intake_id` isn't the one for the send.

If no row can be kept, nothing is stored. The answer lists every reason, with a 400 status.

## A worked example

This example is for a made-up metric on restore tests, sent as Items. Every name in it is an example.

**Setting up**

1. Tech Risk adds the record. It is MI-002 and starts as Wanted. It counts in no score.
2. The details are agreed, including the shape (Items), what ties each row to a team (application), that the team sends it by API, and the service account `svc-example-sender`. Tech Risk moves MI-002 to In progress.
3. The service account is added to the data senders' AD group.

**Sending October's numbers**

The job collects its October restore tests and sends two items for one application. One restore test counted and one did not.

```
curl -X POST "https://trust.example.com/api/metric-values" \
  -H "X-TRUST: 1" -H "Content-Type: application/json" \
  -d '{"intake_id":"MI-002","month":"2026-10","shape":"items","rows":[
    {"intake_id":"MI-002","month":"2026-10","item_id":"RT-17","item_name":"Restore test of Payments DB","key_type":"application","key":"APP-1234","counted":"yes","as_of":"2026-10-28"},
    {"intake_id":"MI-002","month":"2026-10","item_id":"RT-18","item_name":"Restore test of Ledger DB","key_type":"application","key":"APP-1234","counted":"no","as_of":"2026-10-28"}]}'
```

The same send in PowerShell:

```powershell
$body = @{
  intake_id = "MI-002"; month = "2026-10"; shape = "items"
  rows = @(
    @{ intake_id = "MI-002"; month = "2026-10"; item_id = "RT-17"; item_name = "Restore test of Payments DB"; key_type = "application"; key = "APP-1234"; counted = "yes"; as_of = "2026-10-28" },
    @{ intake_id = "MI-002"; month = "2026-10"; item_id = "RT-18"; item_name = "Restore test of Ledger DB"; key_type = "application"; key = "APP-1234"; counted = "no"; as_of = "2026-10-28" }
  )
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri "https://trust.example.com/api/metric-values" `
  -Headers @{ "X-TRUST" = "1" } -ContentType "application/json" -Body $body -UseDefaultCredentials
```

**What comes back**

TRUST keeps both rows. For APP-1234 it works out 1 counted out of 2, and the answer says `"rows_kept": 2`, `"rows_set_aside": 0` and `"scored": false`. The message reads "Received. 2 rows kept. Nothing here changes any score."

**If something is wrong**

Suppose the second row had `counted` set to `maybe`. TRUST keeps the first row and sets the second aside, with the reason "counted must be yes or no (it was 'maybe')." The job's owner fixes the value and sends the whole month again. The new send replaces the first on screen, and the answer shows `"replaced_earlier_send": true`.

**After that**

The numbers sit in TRUST and Tech Risk can read them. Once the metric has had the usual metric approval and Tech Risk sets the record to Measured, adding the metric to the scorecard is a separate step.

If you're unsure, Tech Risk can help.
