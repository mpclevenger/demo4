# 19 — How a risk is rated (15 Nov 2026)

Status: **the rules are built as code with tests (`backend/trust/risk/`). The Risk site uses them** ([doc 21](21_risk_site.md)): `backend/trust/risk/assess.py` rates every risk with them when a group's form is submitted, and each assessment is kept in `risk_assessment`. No TRUST score reads them. Every example here uses the made-up risks in `tools/test_risks/`.

Owner, 15 Nov 2026: the site works out the ratings itself. The engine's files are still read, and its rules for Critical and High are followed as written, so the two can be compared side by side.

## From answers to a rating

| Step | What happens | Code |
|---|---|---|
| 1 | Each driver is on or off for the group, from an answer or from data | `drivers.driver_is_on` |
| 2 | Does the risk apply? At least one of its own drivers is on | `rating.is_applicable` |
| 3 | Likelihood: Critical, High, Medium or Low | `rating.likelihood` |
| 4 | Impact, rated three ways; the overall impact is the highest | `rating.impact_by_kind`, `rating.overall_impact` |
| 5 | Elevated: likelihood and impact both High or Critical | `rating.is_elevated` |
| 6 | Better, worse, mixed or no change since the last assessment | `rating.trend` |

## The three numbers a rule can ask for

| In the risk file | Means | Worked out as |
|---|---|---|
| `RD02 in ad` | Driver RD02 is on for this group | the group's active drivers |
| `dc >= 1` | At least one of this risk's own drivers is on | drivers on, out of the risk's likelihood and impact drivers |
| `>.80` | Driver share above 80% | likelihood drivers on ÷ likelihood drivers. Two of three is 67% |

`and` is worked out before `or`, so `A and B or C` means `(A and B) or C`.

## What was picked, and why

| Rule | Value | Why | Status |
|---|---|---|---|
| Critical and High likelihood | The risk's own rule, as written in its file | So the site and the engine agree | From the files |
| Medium likelihood | Driver share above 30% (`medium_share_above`) | The files stop at High. 30% means one driver of three is on | **Starting value** |
| Low likelihood | Everything else that applies | | Starting value |
| Impact of each kind | The highest level whose rule is met | As written in the files | From the files |
| Overall impact | The highest of the three kinds | Owner, 15 Nov | Decided |
| Not applicable | None of the risk's own drivers is on | Even the lowest impact rule needs one driver on (`dc >= 1`) | **Starting value** |
| Elevated | Likelihood and impact both at least High | Owner, 9 Nov | Proposed |
| Trend with one rating up and one down | "mixed" | Calling it better or worse hides half the story | Starting value |

The starting values are in `config/risk_settings.json`. Tech Risk changes them on the Rating settings page (Edit, Rating settings); a saved change wins over the file.

## Read this way until the engine's owner confirms

1. `>.80` is the driver share (the share of the risk's **likelihood** drivers that are on).
2. `dc` counts the risk's **own** drivers that are on, not every driver the group has on.
3. `ad` is every driver the group has on, including drivers the risk doesn't list.
4. `A and B or C` is read as `(A and B) or C`.

If any of these is wrong, the fix is in one place: `rating.driver_share`, `rating.driver_count`, or `expressions.py`.

## Checks for when risk files are loaded (the Risk site runs them: `site.py` calls `files.check_risks`)

`files.check_risks` lists, without refusing anything: a rule that can't be read, a level or kind written in a way that is not read, a rule naming a driver that isn't in the drivers file, and a rule naming a driver that isn't in the risk's own lists. The made-up files have the last two.

## Details worth knowing
- A driver with no answer yet, or no prevailing median to compare with, is "not known". It is never counted as on.
- A share is kept as a fraction: 0.25 for 25%. An answer typed as "25%" is read as 0.25.
- A risk can apply and still have no impact rating, when none of its impact rules is met. It is then never Elevated and has no trend.
- A rule longer than 500 characters, or a driver share written above 1 (">80" for ">.80"), is refused with a plain message.

## One group, worked through

`tests/test_risk_rating.py`, `test_one_group_from_answers_to_ratings`: 21 answers for a made-up group switch 13 drivers on, and the eight made-up risks come out as four Elevated, with every rating written out beside the reason.

## Not built
The tables, the questionnaire, the Rating settings page, the results pages, the engine download and upload, and the side-by-side comparison. See the Risk build plan (kept with the project notes).
