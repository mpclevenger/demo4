# Commands to confirm with each platform owner

Every query and command shown on a control page, grouped by platform. Each one is read-only.
Until someone who runs the platform confirms a command works on the firm's version and returns what the
step says, the control page shows it marked "Proposed: pending confirmation from the platform owner."
To record a confirmation, add two lines to the command in its control file (content/controls/*.yaml):
`confirmed_by: <name>` and `confirmed_on: YYYY-MM-DD`. The mark comes off, and this list shows it as confirmed.
This list is made from the control files by `manage.py commands_to_confirm`; run it again after a change.

109 commands: 109 proposed, 0 confirmed.

## AWS (19)

### AM-01, step 1: List every role.

Control: Roles are documented with their permissions

Status: Proposed: pending confirmation from the platform owner.

The managed and inline policies attached to one IAM role. Replace <role name>.

```
aws iam list-attached-role-policies --role-name <role name>
aws iam list-role-policies --role-name <role name>
```

### AM-04, step 1: Pull the full list from the system.

Control: Periodic user access review

Status: Proposed: pending confirmation from the platform owner.

The IAM credential report for the account, saved as CSV (IAM users only; IAM Identity Center users and roles are listed separately).

```
aws iam generate-credential-report
$b64 = aws iam get-credential-report --query Content --output text
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64)) | Out-File credential-report.csv
```

### AM-05, step 5: Look back where access stayed too long.

Control: Leavers and movers lose access on time

Status: Proposed: pending confirmation from the platform owner.

Recent CloudTrail management events by an IAM user name; older events are in the trail's own store or Splunk. Replace <user name>.

```
aws cloudtrail lookup-events --lookup-attributes AttributeKey=Username,AttributeValue=<user name>
```

### AM-06, step 1: List every service account.

Control: Service accounts are owned and restricted

Status: Proposed: pending confirmation from the platform owner.

IAM users in the account. The credential report (see AM-04) adds key age and last use.

```
aws iam list-users --query "Users[].[UserName,CreateDate,PasswordLastUsed]" --output table
```

### AM-06, step 4: Give each one only what its job needs.

Control: Service accounts are owned and restricted

Status: Proposed: pending confirmation from the platform owner.

The policies attached to the role a workload uses. Replace <role name>.

```
aws iam list-attached-role-policies --role-name <role name>
aws iam list-role-policies --role-name <role name>
```

### AM-08, step 1: List how people sign in.

Control: Authentication settings are enforced

Status: Proposed: pending confirmation from the platform owner.

The IAM credential report as CSV. Its password_enabled and mfa_active columns show who can sign in to the console and whether they use multi-factor sign-in.

```
aws iam generate-credential-report
$b64 = aws iam get-credential-report --query Content --output text
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64)) | Out-File credential-report.csv
```

### CM-02, step 4: Control break-glass access.

Control: Production changes only through the pipeline

Status: Proposed: pending confirmation from the platform owner.

Every assumption of the break-glass role in a period. Event history covers recent events only; for older periods search the trail's logs. With single sign-on, use AssumeRoleWithSAML.

```
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRole \
  --start-time <from> --end-time <to> \
  --query "Events[?contains(CloudTrailEvent, '<break-glass-role-name>')].[EventTime,Username]" \
  --output table
```

### DR-01, step 3: Set up the backups and list the jobs.

Control: Backups match the system's needs and are monitored

Status: Proposed: pending confirmation from the platform owner.

The AWS Backup plans in the account, then the resources that have been backed up.

```
aws backup list-backup-plans
aws backup list-protected-resources
```

### DR-01, step 5: Record every failure.

Control: Backups match the system's needs and are monitored

Status: Proposed: pending confirmation from the platform owner.

Failed AWS Backup jobs created since a date; replace the date.

```
aws backup list-backup-jobs --by-state FAILED --by-created-after 2027-01-01T00:00:00Z
```

### DR-02, step 2: Restore a real backup to a separate place.

Control: Restores are tested

Status: Proposed: pending confirmation from the platform owner.

Automated RDS snapshots for an instance, to pick a real backup to restore; replace <instance>.

```
aws rds describe-db-snapshots --db-instance-identifier <instance> --snapshot-type automated
```

### DR-04, step 1: List who can reach the backups.

Control: Access to backups is restricted

Status: Proposed: pending confirmation from the platform owner.

The resource policy on an AWS Backup vault; IAM policies can grant access too. Replace <vault>.

```
aws backup get-backup-vault-access-policy --backup-vault-name <vault>
```

### DR-04, step 3: Make deleting backups hard.

Control: Access to backups is restricted

Status: Proposed: pending confirmation from the platform owner.

An AWS Backup vault's settings, including whether Vault Lock is on and its retention limits; replace <vault>.

```
aws backup describe-backup-vault --backup-vault-name <vault>
```

### DR-04, step 4: Check restores and deletions.

Control: Access to backups is restricted

Status: Proposed: pending confirmation from the platform owner.

Recent deletions of AWS Backup recovery points from CloudTrail; run again with StartRestoreJob for restores. Lookup covers recent events only, so use your CloudTrail data in Splunk for a full period.

```
aws cloudtrail lookup-events --lookup-attributes AttributeKey=EventName,AttributeValue=DeleteRecoveryPoint
```

### LA-01, step 3: Turn it on and send it to Splunk.

Control: Audit logging is configured and evidenced

Status: Proposed: pending confirmation from the platform owner.

The CloudTrail trails in the account, then whether a trail is logging; replace <trail> with the trail name.

```
aws cloudtrail describe-trails
aws cloudtrail get-trail-status --name <trail>
```

### PI-01, step 1: List the kinds of server and platform you run.

Control: Servers are built to a documented baseline

Status: Proposed: pending confirmation from the platform owner.

Every account in the AWS organization. Run from the management account or a delegated administrator.

```
aws organizations list-accounts --query "Accounts[].[Id,Name,Status]" --output table
```

### PI-02, step 3: Compare cloud accounts and clusters with the baseline.

Control: Configuration drift is monitored

Status: Proposed: pending confirmation from the platform owner.

Config rules with resources that don't match. Run per account and region.

```
aws configservice describe-compliance-by-config-rule --compliance-types NON_COMPLIANT
```

### VM-01, step 4: Compare what was scanned with the inventory.

Control: Vulnerability scans cover every system in the inventory

Status: Proposed: pending confirmation from the platform owner.

Resources Amazon Inspector covers in the account, with their scan status (INACTIVE means not being scanned).

```
aws inspector2 list-coverage --query "coveredResources[].[resourceType,resourceId,scanStatus.statusCode]" --output table
```

### VM-02, step 2: Give every finding an owner and a due date.

Control: Findings are fixed by their due date or an exception is recorded

Status: Proposed: pending confirmation from the platform owner.

Active Amazon Inspector findings with severity, first-seen time and the affected resource.

```
aws inspector2 list-findings --filter-criteria '{"findingStatus":[{"comparison":"EQUALS","value":"ACTIVE"}]}' --query "findings[].[severity,firstObservedAt,title,resources[0].id]" --output table
```

### VM-02, step 4: Prove the fix worked.

Control: Findings are fixed by their due date or an exception is recorded

Status: Proposed: pending confirmation from the platform owner.

Installed, missing and failed patch counts for managed instances; replace <instance-id>.

```
aws ssm describe-instance-patch-states --instance-ids <instance-id>
```

## Active Directory (7)

### AM-03, step 1: List who holds privileged access.

Control: Privileged access is limited and controlled

Status: Proposed: pending confirmation from the platform owner.

Members of the main domain admin groups, with nested groups expanded. Add your own admin groups to the list.

```
foreach ($g in 'Domain Admins', 'Enterprise Admins', 'Schema Admins', 'Administrators') {
  Get-ADGroupMember -Identity $g -Recursive |
    Select-Object @{n='Group'; e={$g}}, Name, SamAccountName, objectClass
}
```

### AM-04, step 1: Pull the full list from the system.

Control: Periodic user access review

Status: Proposed: pending confirmation from the platform owner.

The people in a group that grants access, with nested groups expanded. LastLogonTimestamp is only updated periodically, so it can be days behind. Replace <group name>.

```
Get-ADGroupMember -Identity "<group name>" -Recursive |
  Where-Object objectClass -eq 'user' |
  Get-ADUser -Properties Enabled, LastLogonTimestamp, Title, Manager |
  Select-Object SamAccountName, Name, Enabled, Title, Manager,
    @{n='LastLogon'; e={ if ($_.LastLogonTimestamp) { [DateTime]::FromFileTime($_.LastLogonTimestamp) } }}
```

### AM-06, step 1: List every service account.

Control: Service accounts are owned and restricted

Status: Proposed: pending confirmation from the platform owner.

Group managed service accounts, then user accounts with a service principal name (usually service accounts).

```
Get-ADServiceAccount -Filter * | Select-Object Name, Enabled
Get-ADUser -Filter "ServicePrincipalName -like '*'" -Properties ServicePrincipalName, PasswordLastSet, LastLogonTimestamp, Description |
  Select-Object SamAccountName, Enabled, PasswordLastSet, Description
```

### AM-07, step 4: Compare everyone's access with the list.

Control: Segregation of duties conflicts are prevented or monitored

Status: Proposed: pending confirmation from the platform owner.

People in both of two conflicting groups (nested groups expanded). It won't catch a second account, so match those by employee ID. Replace the group names.

```
$a = Get-ADGroupMember -Identity "<group A>" -Recursive | Select-Object -ExpandProperty SamAccountName
$b = Get-ADGroupMember -Identity "<group B>" -Recursive | Select-Object -ExpandProperty SamAccountName
$a | Where-Object { $b -contains $_ }
```

### AM-08, step 4: Set password and lockout rules on the local accounts that remain.

Control: Authentication settings are enforced

Status: Proposed: pending confirmation from the platform owner.

The domain password and lockout policy, then any fine-grained policies that override it.

```
Get-ADDefaultDomainPasswordPolicy
Get-ADFineGrainedPasswordPolicy -Filter *
```

### CM-02, step 1: List who and what can write to production.

Control: Production changes only through the pipeline

Status: Proposed: pending confirmation from the platform owner.

Expands a group found above to the people in it, including nested groups. Replace <group>.

```
Get-ADGroupMember -Identity <group> -Recursive | Select-Object Name, SamAccountName, objectClass
```

### PI-01, step 1: List the kinds of server and platform you run.

Control: Servers are built to a documented baseline

Status: Proposed: pending confirmation from the platform owner.

Every server computer object in the domain.

```
Get-ADComputer -Filter 'OperatingSystem -like "*Server*"' -Properties OperatingSystem, LastLogonDate |
  Select-Object Name, OperatingSystem, LastLogonDate
```

## Azure (4)

### DR-01, step 3: Set up the backups and list the jobs.

Control: Backups match the system's needs and are monitored

Status: Proposed: pending confirmation from the platform owner.

Items protected in a Recovery Services vault; replace <rg> and <vault>.

```
az backup item list --resource-group <rg> --vault-name <vault> --output table
```

### DR-01, step 5: Record every failure.

Control: Backups match the system's needs and are monitored

Status: Proposed: pending confirmation from the platform owner.

Failed backup jobs in a vault since a date (day-month-year); replace <rg>, <vault> and the date.

```
az backup job list --resource-group <rg> --vault-name <vault> --status Failed --start-date 01-01-2027 --output table
```

### DR-04, step 1: List who can reach the backups.

Control: Access to backups is restricted

Status: Proposed: pending confirmation from the platform owner.

Role assignments on a Recovery Services vault, including inherited ones; replace <vault-resource-id>.

```
az role assignment list --scope <vault-resource-id> --include-inherited --output table
```

### PI-02, step 3: Compare cloud accounts and clusters with the baseline.

Control: Configuration drift is monitored

Status: Proposed: pending confirmation from the platform owner.

Policy compliance for a subscription. Replace <subscription-id>.

```
az policy state summarize --subscription <subscription-id>
```

## Databricks (5)

### AM-01, step 1: List every role.

Control: Roles are documented with their permissions

Status: Proposed: pending confirmation from the platform owner.

Who holds which privilege on a catalog. Replace <catalog name>; use ON SCHEMA or ON TABLE for lower levels.

```
SHOW GRANTS ON CATALOG <catalog name>;
```

### AM-02, step 4: Compare grants with approved requests.

Control: Access is granted only from an approved request

Status: Proposed: pending confirmation from the platform owner.

Unity Catalog grant changes and group additions in a date range. Replace the dates.

```
SELECT event_time, user_identity.email AS changed_by,
       service_name, action_name, request_params
FROM system.access.audit
WHERE event_date >= '<start date>' AND event_date < '<end date>'
  AND action_name IN ('updatePermissions', 'addPrincipalToGroup')
ORDER BY event_time;
```

### CM-08, step 6: Reconcile data conversions before go-live.

Control: Changes are tested and accepted before release

Status: Proposed: pending confirmation from the platform owner.

The same comparison for a Databricks table. Replace the placeholders.

```
SELECT COUNT(*) AS row_count, SUM(<amount_column>) AS total_amount
FROM <catalog>.<schema>.<table>;
```

### CM-09, step 1: List the databases and tables in scope.

Control: Direct database changes are reviewed

Status: Proposed: pending confirmation from the platform owner.

Who holds which privileges on a schema; MODIFY and ALL PRIVILEGES can change data. Check catalog-level grants too.

```
SHOW GRANTS ON SCHEMA <catalog>.<schema>;
```

### CM-09, step 3: Pull the list of direct changes for the period.

Control: Direct database changes are reviewed

Status: Proposed: pending confirmation from the platform owner.

Every write to one Delta table, with the operation, user and time. Leave out the pipeline's service principal.

```
DESCRIBE HISTORY <catalog>.<schema>.<table>;
```

## Entra ID (3)

### AM-03, step 1: List who holds privileged access.

Control: Privileged access is limited and controlled

Status: Proposed: pending confirmation from the platform owner.

Everyone active in each Entra directory role. People only eligible through Privileged Identity Management show in PIM, not here.

```
Get-MgDirectoryRole -All | ForEach-Object {
  $role = $_.DisplayName
  Get-MgDirectoryRoleMember -DirectoryRoleId $_.Id -All |
    Select-Object @{n='Role'; e={$role}}, Id,
      @{n='Name'; e={$_.AdditionalProperties.displayName}}
}
```

### AM-05, step 5: Look back where access stayed too long.

Control: Leavers and movers lose access on time

Status: Proposed: pending confirmation from the platform owner.

Sign-ins by one user since a date. Entra keeps sign-in logs only for a limited time, so use Splunk for older ones. Replace the UPN and date.

```
Get-MgAuditLogSignIn -All -Filter "userPrincipalName eq '<upn>' and createdDateTime ge <leave date>T00:00:00Z" |
  Select-Object CreatedDateTime, AppDisplayName, IpAddress
```

### AM-08, step 3: Require multi-factor sign-in for privileged and remote access.

Control: Authentication settings are enforced

Status: Proposed: pending confirmation from the platform owner.

Conditional Access policies and whether each is on, off or report-only.

```
Get-MgIdentityConditionalAccessPolicy -All | Select-Object DisplayName, State, CreatedDateTime, ModifiedDateTime
```

## GitHub Enterprise Server (14)

### AM-03, step 3: Make admin rights temporary where the platform allows.

Control: Privileged access is limited and controlled

Status: Proposed: pending confirmation from the platform owner.

Organization owners. Replace <ghes host> and <org>.

```
gh api --hostname <ghes host> "/orgs/<org>/members?role=admin" --paginate --jq '.[].login'
```

### CM-01, step 1: List the repositories that hold production changes.

Control: Peer-reviewed changes

Status: Proposed: pending confirmation from the platform owner.

Lists every repository in an organization. Set GH_HOST to your server's host name first, and replace <org>.

```
gh repo list <org> --limit 1000 --json name,isArchived,defaultBranchRef
```

### CM-01, step 2: Protect the main branch.

Control: Peer-reviewed changes

Status: Proposed: pending confirmation from the platform owner.

Branch protection, or the rulesets if the repository uses them instead. Replace <ghes-host>, <owner>, <repo> and <branch>. Rulesets and last-push approval need a recent server version.

```
gh api --hostname <ghes-host> repos/<owner>/<repo>/branches/<branch>/protection
gh api --hostname <ghes-host> repos/<owner>/<repo>/rulesets
```

### CM-01, step 3: Review the whole change before approving it.

Control: Peer-reviewed changes

Status: Proposed: pending confirmation from the platform owner.

Merged pull requests in a period with their reviews. Replace the host, owner, repo and the <from>..<to> dates.

```
gh pr list -R <ghes-host>/<owner>/<repo> --state merged --limit 1000 \
  --search "merged:<from>..<to>" \
  --json number,title,author,mergedAt,mergedBy,reviews
```

### CM-01, step 4: Watch for changes to the protection itself.

Control: Peer-reviewed changes

Status: Proposed: pending confirmation from the platform owner.

Changes to branch protection and rulesets. Needs an organization owner's token. Replace <ghes-host> and <org>.

```
gh api --hostname <ghes-host> --paginate "orgs/<org>/audit-log?phrase=action:protected_branch"
gh api --hostname <ghes-host> --paginate "orgs/<org>/audit-log?phrase=action:repository_ruleset"
```

### CM-03, step 1: List what makes up the pipeline.

Control: Pipeline configuration is protected

Status: Proposed: pending confirmation from the platform owner.

Environments with their protection rules, then repository secret names (never their values). Replace <ghes-host>, <owner> and <repo>.

```
gh api --hostname <ghes-host> repos/<owner>/<repo>/environments
gh api --hostname <ghes-host> repos/<owner>/<repo>/actions/secrets
```

### CM-03, step 2: Require named owners to approve pipeline changes.

Control: Pipeline configuration is protected

Status: Proposed: pending confirmation from the platform owner.

The review settings on the main branch; look for require_code_owner_reviews. Replace the placeholders.

```
gh api --hostname <ghes-host> repos/<owner>/<repo>/branches/<branch>/protection --jq '.required_pull_request_reviews'
```

### CM-03, step 3: Limit who can change environments, rules and secrets.

Control: Pipeline configuration is protected

Status: Proposed: pending confirmation from the platform owner.

Everyone with admin rights on a repository, direct or through a team. Replace the placeholders.

```
gh api --hostname <ghes-host> --paginate "repos/<owner>/<repo>/collaborators?affiliation=all" --jq '.[] | select(.permissions.admin) | .login'
```

### CM-03, step 4: Account for every change to the pipeline.

Control: Pipeline configuration is protected

Status: Proposed: pending confirmation from the platform owner.

Environment and branch protection changes. Secret changes appear as repo actions ending in _actions_secret. Needs an organization owner's token.

```
gh api --hostname <ghes-host> --paginate "orgs/<org>/audit-log?phrase=action:environment"
gh api --hostname <ghes-host> --paginate "orgs/<org>/audit-log?phrase=action:protected_branch"
```

### CM-04, step 2: Put the gates on the production environment.

Control: Production deployment approval and test gates

Status: Proposed: pending confirmation from the platform owner.

The environment's protection rules, deployment branch policy and administrator bypass. Some fields, such as prevent_self_review, need a recent server version. Replace the placeholders.

```
gh api --hostname <ghes-host> repos/<owner>/<repo>/environments/production
```

### CM-04, step 4: Stop the release when a gate fails.

Control: Production deployment approval and test gates

Status: Proposed: pending confirmation from the platform owner.

Runs of the deploy workflow, then who approved one run. Keep the runs in the period by createdAt. Replace <deploy-workflow>, <run-id> and the other placeholders.

```
gh run list -R <ghes-host>/<owner>/<repo> --workflow <deploy-workflow>.yml --limit 1000 \
  --json databaseId,headSha,headBranch,conclusion,createdAt,event
gh api --hostname <ghes-host> repos/<owner>/<repo>/actions/runs/<run-id>/approvals
```

### CM-06, step 2: Pull the full change list for the period.

Control: Production change reconciliation

Status: Proposed: pending confirmation from the platform owner.

Deployments to the production environment; keep those with created_at in the period. Replace the placeholders.

```
gh api --hostname <ghes-host> --paginate "repos/<owner>/<repo>/deployments?environment=production" \
  --jq '.[] | [.id, .sha, .ref, .creator.login, .created_at] | @tsv'
```

### CM-07, step 4: Carry the request number through.

Control: Changes start from an approved request

Status: Proposed: pending confirmation from the platform owner.

Merged pull requests in a period whose title lacks a request number. Replace <request-id-pattern> with your ticket format as a regular expression, and the other placeholders.

```
gh pr list -R <ghes-host>/<owner>/<repo> --state merged --limit 1000 \
  --search "merged:<from>..<to>" --json number,title,mergedAt \
  --jq '.[] | select(.title | test("<request-id-pattern>") | not)'
```

### CM-08, step 3: Record what was tested and the result.

Control: Changes are tested and accepted before release

Status: Proposed: pending confirmation from the platform owner.

Every workflow run for one commit, with its result. Replace <sha> and the other placeholders.

```
gh run list -R <ghes-host>/<owner>/<repo> --commit <sha> \
  --json workflowName,conclusion,createdAt,headSha,url
```

## Kubernetes (7)

### AM-03, step 3: Make admin rights temporary where the platform allows.

Control: Privileged access is limited and controlled

Status: Proposed: pending confirmation from the platform owner.

Who is bound to cluster-wide and namespace roles (look for cluster-admin and edit rights in production).

```
kubectl get clusterrolebindings -o wide
kubectl get rolebindings --all-namespaces -o wide
```

### AM-06, step 1: List every service account.

Control: Service accounts are owned and restricted

Status: Proposed: pending confirmation from the platform owner.

Service accounts in every namespace.

```
kubectl get serviceaccounts --all-namespaces
```

### AM-06, step 4: Give each one only what its job needs.

Control: Service accounts are owned and restricted

Status: Proposed: pending confirmation from the platform owner.

Everything a service account can do in a namespace. Replace <namespace> and <name>.

```
kubectl auth can-i --list --as=system:serviceaccount:<namespace>:<name> -n <namespace>
```

### CM-02, step 1: List who and what can write to production.

Control: Production changes only through the pipeline

Status: Proposed: pending confirmation from the platform owner.

Who is bound to which role in a production namespace and across the cluster. Check which of those roles can create, update or delete.

```
kubectl get rolebindings -n <namespace> -o wide
kubectl get clusterrolebindings -o wide
```

### MO-01, step 1: List your jobs and where each one is defined.

Control: Changes to scheduled jobs go through change control

Status: Proposed: pending confirmation from the platform owner.

Lists every CronJob in every namespace, with its schedule and last run.

```
kubectl get cronjobs -A
```

### PI-02, step 3: Compare cloud accounts and clusters with the baseline.

Control: Configuration drift is monitored

Status: Proposed: pending confirmation from the platform owner.

Differences between the live cluster and the baseline manifests; changes nothing. Replace <baseline-folder>.

```
kubectl diff -R -f <baseline-folder>/
```

### VM-03, step 1: Record versions and end-of-support dates.

Control: End-of-life software is tracked and replaced or excepted

Status: Proposed: pending confirmation from the platform owner.

Each node's kubelet version, OS image, kernel and container runtime.

```
kubectl get nodes -o wide
```

## SQL Server (26)

### AM-01, step 1: List every role.

Control: Roles are documented with their permissions

Status: Proposed: pending confirmation from the platform owner.

Permissions granted to each database role. Run it in each database.

```
SELECT r.name AS role_name, p.class_desc,
       CASE p.class WHEN 1 THEN OBJECT_NAME(p.major_id)
                    WHEN 3 THEN SCHEMA_NAME(p.major_id) END AS object_name,
       p.permission_name, p.state_desc
FROM sys.database_permissions AS p
JOIN sys.database_principals AS r ON r.principal_id = p.grantee_principal_id
WHERE r.type = 'R'
ORDER BY r.name, p.permission_name;
```

### AM-03, step 1: List who holds privileged access.

Control: Privileged access is limited and controlled

Status: Proposed: pending confirmation from the platform owner.

Server role members, then anyone granted CONTROL SERVER (which acts like sysadmin).

```
SELECT r.name AS server_role, m.name AS member, m.type_desc, m.is_disabled
FROM sys.server_role_members AS rm
JOIN sys.server_principals AS r ON r.principal_id = rm.role_principal_id
JOIN sys.server_principals AS m ON m.principal_id = rm.member_principal_id
ORDER BY r.name, m.name;

SELECT p.name, p.type_desc
FROM sys.server_permissions AS sp
JOIN sys.server_principals AS p ON p.principal_id = sp.grantee_principal_id
WHERE sp.permission_name = 'CONTROL SERVER' AND sp.state IN ('G', 'W');
```

### AM-04, step 1: Pull the full list from the system.

Control: Periodic user access review

Status: Proposed: pending confirmation from the platform owner.

Every login on the instance, then the database role members (run that part in each database). Windows groups need expanding in Active Directory.

```
SELECT name, type_desc, is_disabled, create_date, modify_date
FROM sys.server_principals
WHERE type IN ('S', 'U', 'G', 'E', 'X')
ORDER BY name;

SELECT r.name AS db_role, m.name AS member, m.type_desc
FROM sys.database_role_members AS rm
JOIN sys.database_principals AS r ON r.principal_id = rm.role_principal_id
JOIN sys.database_principals AS m ON m.principal_id = rm.member_principal_id
ORDER BY r.name, m.name;
```

### AM-08, step 1: List how people sign in.

Control: Authentication settings are enforced

Status: Proposed: pending confirmation from the platform owner.

SQL logins (the ones that don't use Windows sign-in), with whether password policy and expiry are enforced.

```
SELECT name, is_disabled, is_policy_checked, is_expiration_checked, create_date
FROM sys.sql_logins
ORDER BY name;
```

### CM-02, step 1: List who and what can write to production.

Control: Production changes only through the pipeline

Status: Proposed: pending confirmation from the platform owner.

Members of sysadmin, then (run in each production database) members of roles that can change data or structure. Permissions granted directly to a user need checking separately.

```
SELECT m.name AS member, r.name AS server_role
FROM sys.server_role_members AS rm
JOIN sys.server_principals AS r ON r.principal_id = rm.role_principal_id
JOIN sys.server_principals AS m ON m.principal_id = rm.member_principal_id
WHERE r.name = 'sysadmin';

SELECT m.name AS member, r.name AS database_role
FROM sys.database_role_members AS rm
JOIN sys.database_principals AS r ON r.principal_id = rm.role_principal_id
JOIN sys.database_principals AS m ON m.principal_id = rm.member_principal_id
WHERE r.name IN ('db_owner', 'db_datawriter', 'db_ddladmin');
```

### CM-06, step 2: Pull the full change list for the period.

Control: Production change reconciliation

Status: Proposed: pending confirmation from the platform owner.

Objects whose structure last changed in the period, as a cross-check on the database audit. Only the latest change per object shows.

```
SELECT SCHEMA_NAME(schema_id) AS schema_name, name, type_desc, modify_date
FROM sys.objects
WHERE is_ms_shipped = 0 AND modify_date >= '<from>' AND modify_date < '<to>'
ORDER BY modify_date;
```

### CM-08, step 6: Reconcile data conversions before go-live.

Control: Changes are tested and accepted before release

Status: Proposed: pending confirmation from the platform owner.

Run on the source and the target for each table and compare. Replace the table and amount column.

```
SELECT COUNT(*) AS row_count, SUM(<amount_column>) AS total_amount
FROM <schema>.<table>;
```

### CM-09, step 1: List the databases and tables in scope.

Control: Direct database changes are reviewed

Status: Proposed: pending confirmation from the platform owner.

Every user database on the instance.

```
SELECT name, create_date, state_desc
FROM sys.databases
WHERE database_id > 4
ORDER BY name;
```

### CM-09, step 2: Turn on auditing of data and structure changes.

Control: Direct database changes are reviewed

Status: Proposed: pending confirmation from the platform owner.

Whether each audit is running, then (in each in-scope database) what its audit specification covers.

```
SELECT name, status_desc, status_time, audit_file_path
FROM sys.dm_server_audit_status;

SELECT s.name, s.is_state_enabled, d.audit_action_name, d.class_desc,
       CASE d.class_desc
         WHEN 'SCHEMA' THEN SCHEMA_NAME(d.major_id)
         WHEN 'OBJECT_OR_COLUMN' THEN OBJECT_SCHEMA_NAME(d.major_id) + '.' + OBJECT_NAME(d.major_id)
       END AS covers
FROM sys.database_audit_specifications AS s
JOIN sys.database_audit_specification_details AS d
  ON d.database_specification_id = s.database_specification_id;
```

### CM-09, step 3: Pull the list of direct changes for the period.

Control: Direct database changes are reviewed

Status: Proposed: pending confirmation from the platform owner.

Data and structure changes in a period by anyone but the pipeline, then any audit stops or starts (a stop is a gap). Times are UTC. Replace the folder, dates and account.

```
SELECT event_time, server_principal_name, database_name, schema_name,
       object_name, action_id, statement
FROM sys.fn_get_audit_file('<audit-folder>\*.sqlaudit', DEFAULT, DEFAULT)
WHERE action_id IN ('IN', 'UP', 'DL', 'CR', 'AL', 'DR')
  AND event_time >= '<from>' AND event_time < '<to>'
  AND server_principal_name <> '<pipeline-account>'
ORDER BY event_time;

SELECT event_time, server_principal_name, statement
FROM sys.fn_get_audit_file('<audit-folder>\*.sqlaudit', DEFAULT, DEFAULT)
WHERE action_id = 'AUSC' AND event_time >= '<from>' AND event_time < '<to>';
```

### DR-01, step 3: Set up the backups and list the jobs.

Control: Backups match the system's needs and are monitored

Status: Proposed: pending confirmation from the platform owner.

Every database with its latest full, differential and log backup.

```
SELECT d.name, d.recovery_model_desc,
       MAX(CASE WHEN b.type = 'D' THEN b.backup_finish_date END) AS last_full,
       MAX(CASE WHEN b.type = 'I' THEN b.backup_finish_date END) AS last_diff,
       MAX(CASE WHEN b.type = 'L' THEN b.backup_finish_date END) AS last_log
FROM sys.databases AS d
LEFT JOIN msdb.dbo.backupset AS b ON b.database_name = d.name
GROUP BY d.name, d.recovery_model_desc
ORDER BY d.name;
```

### DR-01, step 5: Record every failure.

Control: Backups match the system's needs and are monitored

Status: Proposed: pending confirmation from the platform owner.

Backups taken since a date. msdb records only successful backups, so a missing one means a failure or a miss; check the backup job's history for the error. Replace the date.

```
SELECT database_name, type, backup_start_date, backup_finish_date
FROM msdb.dbo.backupset
WHERE backup_start_date >= '2027-01-01'
ORDER BY database_name, backup_start_date;
```

### DR-02, step 2: Restore a real backup to a separate place.

Control: Restores are tested

Status: Proposed: pending confirmation from the platform owner.

Checks a backup file is complete and readable, as a quick check before or between full restores; it doesn't replace a restore. Replace the path.

```
RESTORE VERIFYONLY FROM DISK = N'<backup file path>' WITH CHECKSUM;
```

### DR-02, step 3: Check the restored data is complete and usable.

Control: Restores are tested

Status: Proposed: pending confirmation from the platform owner.

Checks the restored database for corruption; replace the name.

```
DBCC CHECKDB (N'<restored database>') WITH NO_INFOMSGS;
```

### LA-01, step 3: Turn it on and send it to Splunk.

Control: Audit logging is configured and evidenced

Status: Proposed: pending confirmation from the platform owner.

Server audits and their specifications with on/off state, then the actions each specification captures.

```
SELECT a.name AS audit_name, a.type_desc, a.is_state_enabled AS audit_on,
       s.name AS spec_name, s.is_state_enabled AS spec_on
FROM sys.server_audits AS a
LEFT JOIN sys.server_audit_specifications AS s ON s.audit_guid = a.audit_guid;

SELECT s.name AS spec_name, d.audit_action_name
FROM sys.server_audit_specifications AS s
JOIN sys.server_audit_specification_details AS d
  ON d.server_specification_id = s.server_specification_id
ORDER BY s.name, d.audit_action_name;
```

### LA-03, step 1: List your alert rules and where they land.

Control: Alerts are triaged within a defined timeframe

Status: Proposed: pending confirmation from the platform owner.

SQL Server Agent alerts and the operators they notify.

```
SELECT a.name AS alert_name, a.enabled, o.name AS operator_name, o.email_address
FROM msdb.dbo.sysalerts AS a
LEFT JOIN msdb.dbo.sysnotifications AS n ON n.alert_id = a.id
LEFT JOIN msdb.dbo.sysoperators AS o ON o.id = n.operator_id
ORDER BY a.name;
```

### MO-01, step 1: List your jobs and where each one is defined.

Control: Changes to scheduled jobs go through change control

Status: Proposed: pending confirmation from the platform owner.

Lists every SQL Server Agent job with when it was created and last changed.

```
SELECT name, enabled, date_created, date_modified
FROM msdb.dbo.sysjobs
ORDER BY name;
```

### MO-01, step 5: Get a list of every change from the scheduler.

Control: Changes to scheduled jobs go through change control

Status: Proposed: pending confirmation from the platform owner.

Jobs changed since a date. It shows only each job's latest change, so a job changed twice appears once; replace the date with the start of your period.

```
SELECT name, date_modified
FROM msdb.dbo.sysjobs
WHERE date_modified >= '2027-01-01'
ORDER BY date_modified;
```

### MO-02, step 1: Keep an inventory of your scheduled jobs.

Control: Job failures are monitored, investigated and resolved

Status: Proposed: pending confirmation from the platform owner.

Lists every SQL Server Agent job on the instance.

```
SELECT name, enabled, date_created, date_modified
FROM msdb.dbo.sysjobs
ORDER BY name;
```

### MO-02, step 5: Keep a record of every failure and its fix.

Control: Job failures are monitored, investigated and resolved

Status: Proposed: pending confirmation from the platform owner.

Failed job runs since a date (run_status 0 is failed; step_id 0 is the job outcome).

```
SELECT j.name, h.run_date, h.run_time, h.message
FROM msdb.dbo.sysjobhistory AS h
JOIN msdb.dbo.sysjobs AS j ON j.job_id = h.job_id
WHERE h.step_id = 0 AND h.run_status = 0
  AND h.run_date >= 20270101
ORDER BY h.run_date, h.run_time;
```

### MO-03, step 1: List who can manage jobs.

Control: Access to the scheduler is limited

Status: Proposed: pending confirmation from the platform owner.

Members of the SQL Server Agent roles in msdb, then members of sysadmin (who can manage every job).

```
SELECT r.name AS role_name, m.name AS member_name
FROM msdb.sys.database_role_members AS rm
JOIN msdb.sys.database_principals AS r ON r.principal_id = rm.role_principal_id
JOIN msdb.sys.database_principals AS m ON m.principal_id = rm.member_principal_id
WHERE r.name IN ('SQLAgentUserRole', 'SQLAgentReaderRole', 'SQLAgentOperatorRole');

SELECT m.name AS sysadmin_member
FROM sys.server_role_members AS rm
JOIN sys.server_principals AS r ON r.principal_id = rm.role_principal_id
JOIN sys.server_principals AS m ON m.principal_id = rm.member_principal_id
WHERE r.name = 'sysadmin';
```

### MO-03, step 3: Run jobs as limited accounts.

Control: Access to the scheduler is limited

Status: Proposed: pending confirmation from the platform owner.

Each job step with its job owner and proxy. A step with no proxy runs as the SQL Server Agent service account, or as the job owner for T-SQL steps.

```
SELECT j.name AS job_name, SUSER_SNAME(j.owner_sid) AS job_owner,
       s.step_name, s.subsystem, p.name AS proxy_name
FROM msdb.dbo.sysjobs AS j
JOIN msdb.dbo.sysjobsteps AS s ON s.job_id = j.job_id
LEFT JOIN msdb.dbo.sysproxies AS p ON p.proxy_id = s.proxy_id
ORDER BY j.name, s.step_id;
```

### PI-01, step 3: Build from the baseline.

Control: Servers are built to a documented baseline

Status: Proposed: pending confirmation from the platform owner.

The instance's configuration settings, to compare with the baseline.

```
SELECT name, value, value_in_use
FROM sys.configurations
ORDER BY name;
```

### PI-02, step 2: Compare servers and databases with the baseline.

Control: Configuration drift is monitored

Status: Proposed: pending confirmation from the platform owner.

The instance's live settings, to compare with the baseline export.

```
SELECT name, value_in_use
FROM sys.configurations
ORDER BY name;
```

### VM-02, step 4: Prove the fix worked.

Control: Findings are fixed by their due date or an exception is recorded

Status: Proposed: pending confirmation from the platform owner.

The SQL Server build and cumulative update level, to compare with the fixed version.

```
SELECT SERVERPROPERTY('ProductVersion') AS build,
       SERVERPROPERTY('ProductUpdateLevel') AS update_level;
```

### VM-03, step 1: Record versions and end-of-support dates.

Control: End-of-life software is tracked and replaced or excepted

Status: Proposed: pending confirmation from the platform owner.

The SQL Server version, service pack level and edition.

```
SELECT SERVERPROPERTY('ProductVersion') AS version,
       SERVERPROPERTY('ProductLevel') AS level,
       SERVERPROPERTY('Edition') AS edition;
```

## Splunk (11)

### AM-02, step 4: Compare grants with approved requests.

Control: Access is granted only from an approved request

Status: Proposed: pending confirmation from the platform owner.

Users added to Active Directory groups (events 4728, 4732 and 4756 from domain controllers). Replace the index and dates.

```
index=<windows security index> EventCode IN (4728, 4732, 4756)
  earliest="<start date, MM/DD/YYYY:00:00:00>" latest="<end date, MM/DD/YYYY:00:00:00>"
| table _time, host, EventCode, _raw
```

### AM-05, step 4: Match the HR list to the removals.

Control: Leavers and movers lose access on time

Status: Proposed: pending confirmation from the platform owner.

Active Directory accounts disabled in a date range (event 4725), to get the removal time. Replace the index and dates.

```
index=<windows security index> EventCode=4725
  earliest="<start date, MM/DD/YYYY:00:00:00>" latest="<end date, MM/DD/YYYY:00:00:00>"
| table _time, host, _raw
```

### AM-05, step 5: Look back where access stayed too long.

Control: Leavers and movers lose access on time

Status: Proposed: pending confirmation from the platform owner.

Windows sign-ins (event 4624) mentioning the account after the leave date. Replace the index, account and date.

```
index=<windows security index> EventCode=4624 "<account name>"
  earliest="<leave date, MM/DD/YYYY:00:00:00>"
| table _time, host, _raw
```

### LA-01, step 5: Show the logs are arriving.

Control: Audit logging is configured and evidenced

Status: Proposed: pending confirmation from the platform owner.

The latest event time for each host and sourcetype in an index; replace <index>.

```
| tstats latest(_time) AS last_seen WHERE index=<index> BY host, sourcetype
| eval last_seen = strftime(last_seen, "%Y-%m-%d %H:%M:%S")
```

### LA-02, step 2: Alert when a feed stops or logging changes.

Control: Log feeds are actively monitored and a stopped feed is fixed

Status: Proposed: pending confirmation from the platform owner.

Feeds in an index with no events for longer than your threshold; replace <index> and <hours>.

```
| tstats latest(_time) AS last_seen WHERE index=<index> BY host, sourcetype
| eval hours_quiet = round((now() - last_seen) / 3600, 1)
| where hours_quiet > <hours>
```

### LA-02, step 2: Alert when a feed stops or logging changes.

Control: Log feeds are actively monitored and a stopped feed is fixed

Status: Proposed: pending confirmation from the platform owner.

DB Connect: the latest event time per input, which stops moving when the checkpoint stops advancing. DB Connect sets source to the input name by default; replace <index>.

```
| tstats latest(_time) AS last_seen WHERE index=<index> BY source
| eval last_seen = strftime(last_seen, "%Y-%m-%d %H:%M:%S")
```

### LA-02, step 5: Review it regularly.

Control: Log feeds are actively monitored and a stopped feed is fixed

Status: Proposed: pending confirmation from the platform owner.

Every host that has sent events to an index, with first and last event times; replace <index>.

```
| metadata type=hosts index=<index>
| eval firstTime = strftime(firstTime, "%Y-%m-%d"), lastTime = strftime(lastTime, "%Y-%m-%d %H:%M:%S")
| table host, firstTime, lastTime, totalCount
```

### LA-03, step 1: List your alert rules and where they land.

Control: Alerts are triaged within a defined timeframe

Status: Proposed: pending confirmation from the platform owner.

Scheduled searches with their schedule, actions and email recipients. It includes scheduled reports, so filter to your alerts.

```
| rest /servicesNS/-/-/saved/searches
| search is_scheduled=1
| table title, eai:acl.app, cron_schedule, actions, action.email.to
```

### LA-03, step 4: Record a first decision on every alert.

Control: Alerts are triaged within a defined timeframe

Status: Proposed: pending confirmation from the platform owner.

Alerts fired in a period, counted by app and alert name; replace <start> and <end>. Needs read access to the _audit index.

```
index=_audit action="alert_fired" earliest=<start> latest=<end>
| stats count BY ss_app, ss_name
```

### LA-05, step 2: Know where your logs are and how far back they go.

Control: System owners are ready to support a security incident

Status: Proposed: pending confirmation from the platform owner.

The earliest and latest event for each host in an index, showing how far back the logs go; replace <index>.

```
| tstats earliest(_time) AS first_seen latest(_time) AS last_seen WHERE index=<index> BY host
| eval first_seen = strftime(first_seen, "%Y-%m-%d"), last_seen = strftime(last_seen, "%Y-%m-%d")
```

### PI-02, step 4: Set how often you compare, and alert on the settings that matter most.

Control: Configuration drift is monitored

Status: Proposed: pending confirmation from the platform owner.

Members added to global, local and universal security groups, from Windows Security logs. Replace <windows-index>.

```
index=<windows-index> EventCode IN (4728, 4732, 4756)
| stats count by host, EventCode
```

## Windows Server (13)

### AM-03, step 3: Make admin rights temporary where the platform allows.

Control: Privileged access is limited and controlled

Status: Proposed: pending confirmation from the platform owner.

Local Administrators on a member server. Run it on each server (it doesn't work on domain controllers).

```
Get-LocalGroupMember -Group Administrators
```

### AM-08, step 1: List how people sign in.

Control: Authentication settings are enforced

Status: Proposed: pending confirmation from the platform owner.

Local user accounts on a member server.

```
Get-LocalUser | Select-Object Name, Enabled, PasswordLastSet, LastLogon
```

### AM-08, step 4: Set password and lockout rules on the local accounts that remain.

Control: Authentication settings are enforced

Status: Proposed: pending confirmation from the platform owner.

The local password and lockout policy on a server.

```
net accounts
```

### DR-02, step 2: Restore a real backup to a separate place.

Control: Restores are tested

Status: Proposed: pending confirmation from the platform owner.

Lists the Windows Server Backup versions available to restore from.

```
wbadmin get versions
```

### DR-04, step 1: List who can reach the backups.

Control: Access to backups is restricted

Status: Proposed: pending confirmation from the platform owner.

Who has which permissions on a backup folder; replace the path.

```
Get-Acl -Path '<backup folder>' | Select-Object -ExpandProperty Access
```

### LA-01, step 3: Turn it on and send it to Splunk.

Control: Audit logging is configured and evidenced

Status: Proposed: pending confirmation from the platform owner.

The effective audit policy for every category on the server (run as administrator).

```
auditpol /get /category:*
```

### MO-01, step 1: List your jobs and where each one is defined.

Control: Changes to scheduled jobs go through change control

Status: Proposed: pending confirmation from the platform owner.

Lists scheduled tasks on the server, leaving out the built-in Microsoft ones.

```
Get-ScheduledTask |
  Where-Object TaskPath -notlike '\Microsoft\*' |
  Select-Object TaskPath, TaskName, State
```

### MO-03, step 1: List who can manage jobs.

Control: Access to the scheduler is limited

Status: Proposed: pending confirmation from the platform owner.

Members of the local Administrators group, who can create and change any scheduled task. AD groups appear as one entry; expand them in Active Directory.

```
Get-LocalGroupMember -Group Administrators
```

### MO-03, step 3: Run jobs as limited accounts.

Control: Access to the scheduler is limited

Status: Proposed: pending confirmation from the platform owner.

The account and privilege level each scheduled task runs with.

```
Get-ScheduledTask |
  Where-Object TaskPath -notlike '\Microsoft\*' |
  Select-Object TaskName,
    @{n='RunAs';e={$_.Principal.UserId}},
    @{n='RunLevel';e={$_.Principal.RunLevel}}
```

### PI-01, step 3: Build from the baseline.

Control: Servers are built to a documented baseline

Status: Proposed: pending confirmation from the platform owner.

The Group Policy applied to a server, as an HTML report, and its installed updates. Replace <server>.

```
gpresult /s <server> /scope computer /h C:\Temp\<server>-gpresult.html
Get-HotFix -ComputerName <server> | Sort-Object InstalledOn
```

### PI-02, step 2: Compare servers and databases with the baseline.

Control: Configuration drift is monitored

Status: Proposed: pending confirmation from the platform owner.

The Group Policy applied to a server, and who is in its local Administrators group. Replace <server>.

```
gpresult /s <server> /scope computer /h C:\Temp\<server>-gpresult.html
Invoke-Command -ComputerName <server> { Get-LocalGroupMember -Group Administrators }
```

### VM-02, step 4: Prove the fix worked.

Control: Findings are fixed by their due date or an exception is recorded

Status: Proposed: pending confirmation from the platform owner.

Windows updates installed on the server, newest first. It doesn't cover other software on the server.

```
Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object HotFixID, Description, InstalledOn
```

### VM-03, step 1: Record versions and end-of-support dates.

Control: End-of-life software is tracked and replaced or excepted

Status: Proposed: pending confirmation from the platform owner.

The Windows Server edition, version and build.

```
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber
```
