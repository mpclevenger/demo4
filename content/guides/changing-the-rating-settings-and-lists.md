---
title: Changing the rating settings and lists
section: run
order: 43
---
Some parts of the Risk site are lists that Tech Risk can change: the rating settings, the sign-off approvers, the questions, each risk's building block and the drivers answered from data. They all work the same way. This guide is for Tech Risk.

## Open the editing pages

Tech Risk sees an Edit link in the top bar. It opens a page with one card for each list, showing how many entries it holds. Everyone who can open the site can read a list and its history. Only Tech Risk can save a change.

## The lists

| List | What it holds | Can a change move a rating? |
|---|---|---|
| Rating settings | Three values: the share of drivers that makes a risk Medium (starting at 30%), and the lowest likelihood and impact level that make a risk Elevated (both High to start). | Yes |
| Sign-off approvers | One entry for each TRUST team, with the person who can sign off when the L3 can't be found. | No |
| Questions | For each question: the driver it feeds, section, order, wording, kind of answer, and which answer turns the driver on. | Yes |
| Building blocks | Each risk's (or each domain's) building block, shown on the results. | No, display only |
| Drivers answered from data | The prevailing median or a fixed number for each driver. Nothing reads it yet, so it is Wanted. | No |

The rating rules themselves do not change here. Only these values do.

## Make a change

Every list has a table of its entries. A long list has a search box. Choose Add, Edit or Retire on an entry. Nothing is ever deleted. A retired entry is greyed, stays in the history, and can be restored. Use "Show retired" to see them.

1. Make the change in the form.
2. Write the reason. **The site will not save without one.**
3. Choose "See what would move" (or "Check the change" on a list that cannot move ratings).
4. Read the answer, then save.

## See what would move

For a list that can move a rating, the site rates each team's newest assessment again with your proposed values. It then lists every rating that would change, with the team, the risk, the rating, and the values now and after the change. If nothing moves, it says "No rating would move."

Saved assessments never change. A team's next Submit uses the new values. That is a good moment to let the teams know.

> **Example.** Tech Risk edits the share that makes a risk Medium. The panel lists 3 ratings that would move from Low to Medium. After reading the list, Tech Risk saves with the reason "Agreed with the risk owners."

## Reason and history

Every change asks for a reason and is kept as a new row, never edited. The history sits under the list and is open to everyone who can see the page. It shows when, who, the entry, the old and new value, and why. Each list can be downloaded as CSV or JSON, with retired entries marked.

## Who may save

Tech Risk, for every list. Anyone who can open the site can read a list and its history.

## Related guides

- [Setting up a team for risk assessment](/guides/setting-up-a-team-for-risk-assessment/)
- [Comparing the Risk site with the risk engine](/guides/comparing-the-risk-site-with-the-risk-engine/)

If you're unsure, Tech Risk can help.
