# 20 — Metric intake: the front door for new metrics

Status: built 15 Nov 2026 (`backend/trust/metric_intake.py`, `metric_intake_rules.py`, migration `0014_metric_intake.sql`, the Metric intake page). **Nothing here scores anything.** A record, a send and a check never change a score and never put a metric on the scorecard.

This document has two halves. **Part 1** is for the owner, in plain words. **Part 2** is for a team's developer.

---

# Part 1. For the owner

## What the record is

When a team says "we would like this measured", Tech Risk adds one **intake record** on the Metric intake page (Governance, Tech Risk only). It has a short ID: MI-001, MI-002, and so on. The record is where everything about the metric is written down once: what it is, who provides it, what is counted, and how the numbers will arrive. Nobody fills in the same thing twice, and **Tech Risk fills the record in, not the team.**

## The three stages

| Stage | Means | What is filled in | Counts in a score? |
|---|---|---|---|
| **Wanted** | We want it and it isn't there yet. | Six answers, in a minute, in the room: metric name; what it tells leadership (one sentence); building block; provider team; contact name; system the data lives in. | No |
| **In progress** | Agreed and being built. | The **data contract**: what is counted; what it is measured against; unit (%, per 10 apps, per 100 releases); direction (higher or lower is better); what ties each row to a team (application, repository or person); shape (Totals or Items); how often it is sent (monthly unless agreed otherwise); how it arrives (the team sends it by API, Tech Risk collects it, or a file for now); the service account that will send it; who approved on the provider's side, and the date. | No |
| **Measured** | Counted and scored. | Nothing more. Tech Risk sets it **by hand**, only after the usual metric approval, and writes which approval in a note. | The page only records the stage and who set it. It does not create a metric. Adding the metric to the scorecard is a separate step. |

Moving a record to In progress needs the In progress answers complete. The page says plainly which ones are missing. A record moves one step at a time (Wanted, then In progress, then Measured), and can move back.

Every change is kept as a history row with who and when. Nothing is overwritten.

## Who does what

- **Tech Risk** adds and completes records, moves their stage, and reads what has been received.
- **The team** builds a small job that sends its numbers from its own **service account**. It never touches the record.
- **Access** works through the company's add-on and AD groups, as for the rest of TRUST. A team's service account is added to the **data senders' AD group**. TRUST handles no token or password.
- **TRUST** checks every row, keeps the good rows, sets the others aside with the reason, and stores the send. Nothing reaches the scorecard.
- **Auditors** can read the page but not change it.

Until the metric is approved and Measured, what the teams send is only stored. That is the point: teams can start sending, and we can see their numbers, before anything is scored.

## What Tech Risk sees

For each record and month: how many rows were kept, how many were set aside and why, who sent them and when. A second send for the same record and month replaces the first on screen. Both stay in the history.

---

# Part 2. For a team's developer

## The address and the header

```
POST /api/metric-values
X-TRUST: 1
```

Use the full address of the TRUST site, for example `https://trust.example.com/api/metric-values`. Every change to TRUST needs the header `X-TRUST: 1`. The page for your metric (Tech Risk opens the record, "How to send") shows the exact address and an example filled in for it.

## How your service account gets access

1. Tech Risk writes your **service account's SAM account name** on the metric's record (for example `svc-lending`).
2. Your service account is added to the **data senders' AD group** (the group named under `data_sender` in `config/access.json`).
3. The company's access add-on passes your account name to TRUST on every request. You send no token.

Rules: when access is switched on, the account you send from must be **the service account named on the record** (Tech Risk may send for any record). A data sender can send numbers and do nothing else: it cannot read the scorecard or the intake list. While TRUST runs open (the TEST site), anyone may send, and the request must also carry `"by": "Your name"` (or a form field `by`) so the record shows who sent it.

## What you can send

Two ways, with the same rows:

- **JSON:** `{"intake_id": "MI-001", "month": "2026-10", "shape": "totals", "rows": [ ... ]}`
- **CSV file:** a multipart upload with the file in the field `file`. The first line holds the column names. Comma, semicolon, tab or pipe separators all work. `intake_id` and `month` can be read from the rows; `shape`, if given, must match the record.

One send is for **one record and one month**. A second send for the same record and month replaces the first on screen; the first is kept in the history.

## The standard layout, version 1

The record says which shape it uses. Column names are not case sensitive. Every column is required except that `intake_id` and `month` may be left out of the rows when the send names them.

### Totals: one row per team per month

| Column | Meaning |
|---|---|
| `intake_id` | The record, for example `MI-001`. |
| `month` | The month the numbers count for, `YYYY-MM`. |
| `key_type` | `application`, `repository` or `person`. Must be the one on the record. |
| `key` | The application's ID or name, the repository, or the person's SAM account. |
| `count` | Whole number: how many were counted. |
| `total` | Whole number: how many there were. Not less than `count`. |
| `as_of` | The date the numbers were taken, `YYYY-MM-DD`. |

CSV:

```
intake_id,month,key_type,key,count,total,as_of
MI-001,2026-10,application,APP-1234,3,4,2026-10-31
MI-001,2026-10,application,APP-5678,10,10,2026-10-31
```

JSON:

```json
{
  "intake_id": "MI-001",
  "month": "2026-10",
  "shape": "totals",
  "rows": [
    {"intake_id": "MI-001", "month": "2026-10", "key_type": "application", "key": "APP-1234", "count": 3, "total": 4, "as_of": "2026-10-31"},
    {"intake_id": "MI-001", "month": "2026-10", "key_type": "application", "key": "APP-5678", "count": 10, "total": 10, "as_of": "2026-10-31"}
  ]
}
```

### Items: one row per item (preferred)

Preferred because your team can then see what sits behind its number. TRUST works out the count and the total for each team itself: **the count is the number of rows with `counted` = yes, the total is the number of rows.** Four rows for APP-1234, three of them yes, give 3 counted out of 4.

| Column | Meaning |
|---|---|
| `intake_id`, `month`, `key_type`, `key`, `as_of` | As above. |
| `item_id` | Your own reference for the item (a ticket, a test, a server). Appears once per send. |
| `item_name` | What a person would call it. |
| `counted` | `yes` if it counts toward the number, `no` if not. |

CSV:

```
intake_id,month,item_id,item_name,key_type,key,counted,as_of
MI-002,2026-10,RT-17,Restore test of Payments DB,application,APP-1234,yes,2026-10-28
MI-002,2026-10,RT-18,Restore test of Ledger DB,application,APP-1234,no,2026-10-28
```

JSON:

```json
{
  "intake_id": "MI-002",
  "month": "2026-10",
  "shape": "items",
  "rows": [
    {"intake_id": "MI-002", "month": "2026-10", "item_id": "RT-17", "item_name": "Restore test of Payments DB", "key_type": "application", "key": "APP-1234", "counted": "yes", "as_of": "2026-10-28"},
    {"intake_id": "MI-002", "month": "2026-10", "item_id": "RT-18", "item_name": "Restore test of Ledger DB", "key_type": "application", "key": "APP-1234", "counted": "no", "as_of": "2026-10-28"}
  ]
}
```

## The checks

The whole send is refused (nothing stored) when:

- the `intake_id` does not exist, or the record is still **Wanted** (not agreed yet); the answer says to ask Tech Risk to move it to In progress;
- the send's `month` is not written `YYYY-MM`;
- the shape you name is not the record's shape;
- there are no rows;
- your account is not allowed to send for this record.

Each **row** is checked on its own. A row that fails is **set aside with its reason**, never dropped silently:

1. `count` and `total` are whole numbers (Totals).
2. `count` is not more than `total` (Totals).
3. `month` is well formed, and is the month of the send.
4. `key_type` is application, repository or person, and is the one on the record.
5. `as_of` is a real date, `YYYY-MM-DD`.
6. `counted` is yes or no (Items).
7. A team appears once per send (Totals); an `item_id` appears once per send (Items).
8. No required column is empty; `intake_id` matches the send.

If **no** row can be kept, nothing is stored, and the answer lists every reason.

## The answers

Always JSON, with a plain message. A send with some rows set aside:

```json
{
  "ok": true,
  "message": "Received. 1 row kept, 1 row was set aside (see the reasons below). Nothing here changes any score.",
  "intake_id": "MI-001", "month": "2026-10", "shape": "totals",
  "send_id": 7, "received_at": "2026-11-15T22:35:03+00:00", "received_from": "svc-lending",
  "rows_received": 2, "rows_kept": 1, "rows_set_aside": 1,
  "set_aside": [{"row_number": 2, "reason": "The count (9) is more than the total (7). The count is the part of the total that was counted.", "row": {"key": "APP-5678", "count": 9, "total": 7}}],
  "totals": [{"key_type": "application", "key": "APP-1234", "count": 3, "total": 4, "as_of": "2026-10-31"}],
  "replaced_earlier_send": false,
  "scored": false
}
```

A refusal: `{"ok": false, "error": "MI-004 is Wanted, which means it isn't agreed yet, so TRUST can't take numbers for it. Ask Tech Risk to move it to In progress first."}` with HTTP status 400 (or 403 when your account is not allowed).

## Examples

curl, JSON:

```
curl -X POST "https://trust.example.com/api/metric-values" \
  -H "X-TRUST: 1" -H "Content-Type: application/json" \
  -d '{"intake_id":"MI-001","month":"2026-10","shape":"totals","rows":[{"intake_id":"MI-001","month":"2026-10","key_type":"application","key":"APP-1234","count":3,"total":4,"as_of":"2026-10-31"}]}'
```

curl, CSV file:

```
curl -X POST "https://trust.example.com/api/metric-values" -H "X-TRUST: 1" -F "file=@restore-tests-2026-10.csv"
```

PowerShell:

```powershell
$body = @{
  intake_id = "MI-001"; month = "2026-10"; shape = "totals"
  rows = @(@{ intake_id = "MI-001"; month = "2026-10"; key_type = "application"; key = "APP-1234"; count = 3; total = 4; as_of = "2026-10-31" })
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri "https://trust.example.com/api/metric-values" `
  -Headers @{ "X-TRUST" = "1" } -ContentType "application/json" -Body $body -UseDefaultCredentials
```

(How the service account signs in to the company's add-on is set up by whoever runs the add-on; TRUST sees only the account name it passes on.)

## For Tech Risk: the other two addresses

- `GET /api/metric-intake`: every record, its history, and per record and month what was received. Tech Risk, and auditors read only.
- `POST /api/metric-intake`: `{"by": "...", "fields": {...}}` adds a record; with `"id": "MI-001"` it changes one; `"stage": "In progress"` (with `"note"`) moves it. Tech Risk only.
- `GET /api/metric-intake/MI-001/2026-10`: the newest send's rows, kept and set aside, and every send for that month.

## Where it is kept

Three tables (migration 0014; without a database, files in the store folder): `metric_intake` (the records), `metric_intake_history` (every change, never edited) and `metric_value_send` (every send). To add to the data model doc (doc 11): these three tables.
