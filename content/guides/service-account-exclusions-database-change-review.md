---
title: Service account exclusions: database change review
section: run
order: 33
---
This guide is for control owners and auditors. It shows how a service account is shown to belong outside the database change review, and what evidence goes with that choice. It is a worked procedure for [documenting population exclusions](/guides/documenting-population-exclusions/).

It supports [CM-09: Direct database changes are reviewed](/rcm/controls/CM-09/).

An account does not qualify just because it is a service account. It qualifies because of what it actually did during the review period. If it fails any criterion, it stays in the review.

The dates of the review period this time are {{svcacct_exclusion_review_period}}. The script and workbook come from [the evidence script and workbook template](#todo-svcacct-exclusion-evidence-script).

## The criteria

Tech Risk's evidence script looks at every account that was active on the in-scope SQL servers and databases during the period. That includes service accounts, deployment accounts and personal accounts. It is not a typed list, so no account can be left out by accident. People and change deployment accounts are expected to come out NOT ELIGIBLE and stay in the review. Deployment accounts are the change path, so they are not excluded.

Each account is checked against these criteria. An account that passes all of them is shown as ELIGIBLE.

| Criterion | Evidence tab | What passing looks like |
|---|---|---|
| Audit data is complete for the period | Q0 Completeness | Every in-scope SQL server sent audit events on every day of the period. |
| Every active account is assessed | QP Population | The accounts come from Splunk (everything active on in-scope servers and databases), not from a typed list, so none can be left out. |
| Used by an application, not a person | QB Connections | No human tool (SSMS, sqlcmd, Excel and the like). Every client machine it connected from is an expected application or job server, confirmed by the control owner. |
| Limited activity: no schema, permission, role or ownership changes | QC Changes | Zero rows in in-scope databases or at server level. |
| Not used to sign in to Windows interactively | QE Win Logons | No logon types 2, 7, 10 or 11 (console, unlock, remote desktop, cached). |
| Predictable pattern (supporting) | QD Pattern | Activity clusters around scheduled job times. This one is the reviewer's judgment, shown as the share of activity in business hours. |
| Cannot change schema or permissions (preventive) | UAR Permissions | No sysadmin, securityadmin or serveradmin role. No db_owner, db_ddladmin, db_securityadmin or db_accessadmin role. No ALTER or CONTROL grants. |
| Password not used by people | CyberArk Checkouts | No person checked out or retrieved the password during the period. |
| Audit captures the activity tested | SQL Audit Spec | The audit specification includes the action groups listed on that tab, on every in-scope server. |

## Who does what

Tech Risk runs the evidence script, which fills in the workbook, and completes the tabs that don't come from Splunk.

Each control owner fills in the owner and purpose for their accounts, chooses Exclude or Keep in review, and adds the change ticket link. The control owner uploads the completed workbook with their first change review of the year.

## Steps for Tech Risk

1. Fill in the list of in-scope SQL servers and their in-scope databases, and the run settings (the Splunk addresses, the dates and the approved version of the script).
2. Close email, chat and anything sensitive. The screenshots capture the whole primary screen. Sign in to Splunk Web in your browser.
3. Run the launcher script and enter your Splunk token. Leave the keyboard and mouse alone until it finishes, because it opens each search in Splunk Web and takes a screenshot.
4. Confirm the overall status is OK. Take your own full-screen screenshot of the final lines (the checksum list's hash, the status and the clock) and save it in the run folder.
5. Open the workbook the script created in the run folder and save it under a new name, such as one ending in `_COMPLETED`. The generated file stays as it was hashed.
6. In the completed copy, fill in the UAR Permissions, SQL Audit Spec and CyberArk Checkouts tabs and the yellow UAR and CyberArk columns on the Account Scorecard. Send it to the control owners with the zipped run folder.

## Steps for control owners

1. On Account Scorecard, find your accounts (filter by server set or account name) and fill in Owner and Purpose.
2. Use Account Detail to see the evidence for any account.
3. For each account, choose Exclude or Keep in review. Exclude is for accounts marked ELIGIBLE. An account marked NOT ELIGIBLE stays in review.
4. Add the change ticket link and any notes.
5. Upload the workbook with your first change review of the year.

## What auditors receive

The files in the script's run folder are the evidence of record: the query results, the query text, the Splunk screenshots, the run manifest, the transcript and the generated workbook. Every file is listed with its SHA256 hash in `SHA256SUMS.txt`, and the hashes are also on the Run Manifest tab. The tabs in the workbook are working copies for review.

Auditors get the whole run folder, zipped and unmodified, with the completed workbook. They can hash each file again and compare.

Two more checks help an auditor trust the run:

- **The run manifest.** It records the script version that ran, the run details, and for each query its Splunk search ID, row count and output hash.
- **The Splunk audit check.** The Q_AUDIT Verification tab confirms each search ID from Splunk's own audit log, so the run can be matched to what Splunk recorded.

Two small steps happen in the script rather than in Splunk, so they are worth pointing out. The completeness check adds any in-scope server that sent no events and compares the days with events to the days in the period. The account profile adds accounts with no events as zero rows.

## Known limitations

- Application names come from the connecting client and can be faked. The control owner's confirmation of the client machines on QB Connections, and the Windows logon evidence on QE Win Logons, carry more weight.
- Older SQL Server versions may not log the client host or IP. Those rows show "REVIEW: client not logged" and rely on the Windows logon evidence.
- Times in the query results use the time zone in the Splunk user's preferences. The period itself is sent as exact times, shown on the Run Manifest tab.
- Excluding an account only takes it out of the review population. Its activity keeps flowing to Splunk so it can be tested again.
- An account with no activity in the period passes without proving anything. Consider whether it should be disabled instead.

If you're unsure, Tech Risk can help.
