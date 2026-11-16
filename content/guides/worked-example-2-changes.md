---
title: Worked example, part 2: a normal change and an emergency change
section: run
order: 31
---
**This is an example.** The application, the people, the tickets and the dates are made up to show what the evidence looks like. It is part 2 of 3, after [part 1 on access](/guides/worked-example-1-access-review/) and before [part 3 on jobs](/guides/worked-example-3-jobs/).

The same payments reconciliation application releases through a pipeline. In the period covered, a developer changed how the matching step treats small rounding differences (a normal change), and one Friday evening a developer fixed a setting that stopped the nightly bank file import (an emergency change).

Controls used: [CM-07 Changes start from an approved request](/rcm/controls/CM-07/), [CM-01 Peer-reviewed changes](/rcm/controls/CM-01/), [CM-04 Production deployment approval and test gates](/rcm/controls/CM-04/), [CM-08 Changes are tested and accepted before release](/rcm/controls/CM-08/), [CM-02 Production changes only through the pipeline](/rcm/controls/CM-02/), [CM-05 Emergency changes are recorded and reviewed afterward](/rcm/controls/CM-05/) and [CM-06 Production change reconciliation](/rcm/controls/CM-06/).

## Who does what

The team that runs the application is a Platform user: it owns the controls over its own changes. Platform admins run the repository hosting and the pipeline service, and the team sets up its own repositories and workflows on them.

## What the team did

The team's written rule says a change is high risk when it changes how financial figures are calculated, stored or reported. The rounding change is high risk under that rule.

#### The normal change

1. **Logged a request.** The developer who proposed the change logged request CHG-1042 in the ticket system (CM-07 step 1) and sized it as high risk using the written rule (CM-07 step 2).
2. **Got approval before release.** The application owner approved it. The application owner was neither the requester nor the developer building it (CM-07 step 3).
3. **Opened a pull request with the request number in the title.** A second developer read the whole change and approved it. The branch protection settings block the author from approving their own change and from approving the latest push they made themselves (CM-01 steps 2 and 3, CM-07 step 4).
4. **Passed the named checks.** Build, tests and security scan ran in the pipeline. The deploy job depends on them (CM-04 steps 1 and 2).
5. **Tested and accepted.** Automated tests ran against the commit. Because the change touches figures, extra tests compared expected and actual results, and the finance business owner accepted the results in the request, naming the version they looked at (CM-08 steps 2, 3 and 5).
6. **Deployed through the pipeline.** The production environment has a deployment approver who is not the person who started the deployment. The deployment record names the commit and the request (CM-04 steps 2 and 3, CM-02 step 2).

#### The emergency change

1. **Recorded the reason first.** The developer opened emergency record EMG-0007 before making the change: the reason, what would change, who agreed to the emergency path and how to roll back (CM-05 step 2).
2. **Used the pipeline with the approval relaxed.** The change was not made by hand. The application owner, who can declare an emergency under the team's written definition, approved in place of a peer review. The pipeline checks still ran (CM-05 step 1).
3. **Reviewed it afterward.** A developer who did not make the change compared the diff with the reason, confirmed the skipped steps were completed later, and decided whether the change held up (CM-05 step 4).

#### The month

At month end, someone who does not deploy to the system matched every production change to an approved request, or to an emergency record with a completed review (CM-06 steps 2 to 6). The count of emergency changes went to management (CM-05 step 5).

## The evidence as it would look

Everything below is made up.

#### Normal change: the request (CM-07)

Taken from the ticket system on 2026-09-22.

| Field | Value |
|---|---|
| Request | CHG-1042: change how the matching step treats rounding differences |
| Requested by | Developer A, 2026-09-14 |
| Systems touched | Matching step of the reconciliation job |
| Risk size | High. It changes how financial figures are calculated |
| Approved by | Application owner, 2026-09-16 |
| Approver differs from requester and builder? | Yes |
| Approval time compared with deployment time | Approved 2026-09-16, deployed 2026-09-22 |

#### Normal change: branch protection in effect (CM-01 step 2)

Exported from the repository host on 2026-09-30 for the main branch of the application's repository.

| Setting | Value |
|---|---|
| Pull request needed before merge | On |
| Approvals needed, not from the author | 1 |
| Approval of the most recent push, by someone other than the pusher | On |
| Old approvals dismissed when new commits arrive | On |
| Direct and force pushes | Blocked |
| Applies to administrators | Yes |
| People allowed to bypass | None |

#### Normal change: the pull request (CM-01 step 3, CM-07 step 4)

| Field | Value |
|---|---|
| Pull request | #318, titled "CHG-1042 Rounding tolerance in matching" |
| Author | Developer A |
| Approved by | Developer B, 2026-09-18 (not the author) |
| Merged | 2026-09-18 |
| Commit | a3f9c21 |

#### Normal change: checks, tests and acceptance (CM-04, CM-08)

| Item | Environment | Commit | Result | Run or accepted by, when |
|---|---|---|---|---|
| Build | Pipeline | a3f9c21 | Passed | Pipeline, 2026-09-18 |
| Automated tests (212 of 212) | Test | a3f9c21 | Passed | Pipeline, 2026-09-18 |
| Security scan | Pipeline | a3f9c21 | Passed | Pipeline, 2026-09-18 |
| Expected and actual results comparison (30 sample days) | Test | a3f9c21 | Matched | Developer B, 2026-09-20 |
| Acceptance of the results | Test | a3f9c21 | Accepted | Finance business owner, 2026-09-21. Not the developer |

#### Normal change: the deployment (CM-04 step 3, CM-02)

| Field | Value |
|---|---|
| Pipeline run | Production deploy, run 4471 |
| Commit | a3f9c21, the same commit that was tested |
| Request | CHG-1042 |
| Started by | Developer A |
| Production environment approval | Developer C, 2026-09-22 (not the person who started the run) |
| Result | Succeeded |

#### Emergency change: the record, written before the change (CM-05 steps 1 and 2)

| Field | Value |
|---|---|
| Record | EMG-0007 |
| Opened | 2026-10-09 17:12, before the change reached production |
| Reason | The nightly bank file import rejects every file. A setting in the previous release points to a folder that does not exist |
| What will change | One setting value |
| Declared and agreed by | Application owner, 2026-10-09 17:20 |
| Way back | Redeploy the previous version |
| Skipped steps | Peer review before merge, and the normal request. Both to be completed afterward |

#### Emergency change: the pull request and deployment

| Field | Value |
|---|---|
| Pull request | #331, titled "EMG-0007 Fix import folder setting" |
| Approved by | Application owner, 2026-10-09 17:38, in place of a peer review |
| Pipeline checks | Build, tests and security scan passed |
| Deployed | 2026-10-09 17:55 through the pipeline. Deployment names EMG-0007 |
| Extra access requested | None |

#### Emergency change: the review afterward (CM-05 step 4)

The team's own written-down time for this review is 2 business days after the change. This is a made-up time for the example. Tech Risk sets no time, and each team writes its own; see [Timings your team sets](/guides/timings-your-team-sets/).

| Field | Value |
|---|---|
| Reviewed by | Developer D, 2026-10-13. Did not make or approve the change |
| Compared | The diff (one line changed) with the reason in EMG-0007 |
| Skipped steps completed | Peer review of #331 done by Developer D on 2026-10-12 and recorded in the pull request. Normal request CHG-1051 logged and approved by the application owner on 2026-10-12 |
| Decision | The change holds up. No revert |
| Follow-up | Ticket CHG-1052: add a test that checks the setting value points to an existing folder |
| Within the team's written time? | Yes. Change on Friday 2026-10-09, review on Tuesday 2026-10-13 |

#### The month: reconciliation of October 2026 (CM-06)

Pulled 2026-11-03 from the pipeline's deployment records. A second source, the workflow run history, shows the same 11 production deployments.

| Change | Pull request | Request or record | Approver | Matched? |
|---|---|---|---|---|
| Release of 2026-10-02 | #325 | CHG-1046 | Application owner | Yes |
| Release of 2026-10-06 | #328 | CHG-1048 | Application owner | Yes |
| Release of 2026-10-09 | #331 | EMG-0007 (review completed 2026-10-13) | Application owner | Yes, emergency |
| Release of 2026-10-27 | #340 | CHG-1055 | Application owner | Yes |

Four of 11 releases are shown. Across all 11: 10 matched to an approved request, 1 matched to an emergency record with a completed review, and 0 are unmatched. The summary to management reads: 1 emergency change out of 11 releases in October.

## Questions a reviewer would ask

#### About the normal change

- Was the request logged before the work, and is the approval earlier than the deployment?
- Is the approver someone other than the requester and the person who built it?
- Does the pull request carry the request number, and did someone other than the author approve it?
- Do the protection settings apply to administrators, and who can bypass them?
- Was the commit that was tested the commit that was deployed?
- For a change to figures, did someone other than the developer accept the results, and which version did they look at?
- Did anyone start and approve the same deployment?

#### About the emergency change

- Does the emergency record show a creation time before the change reached production?
- Does the team's written definition cover this case, and did the person who declared it have the standing to do so?
- Was the change made through the pipeline, or by hand?
- Did someone other than the person who made the change review it afterward, inside the team's own written time?
- Were the skipped steps completed, and what did the reviewer compare?
- If the change did not hold up, was it reverted or fixed?

#### About the month

- Do the counts tie to a second source, such as the workflow run history?
- Is every change matched to a request or to an emergency record with a finished review?
- What happened to anything unmatched?
- Who reviewed the reconciliation, and do they deploy to the system?
- Did the count of emergency changes reach management?

If you're unsure, Tech Risk can help.
