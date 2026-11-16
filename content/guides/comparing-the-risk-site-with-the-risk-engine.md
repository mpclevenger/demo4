---
title: Comparing the Risk site with the risk engine
section: run
order: 44
---
The Risk site rates risks itself. The risk engine can rate them too, and the comparison page shows the two side by side. This guide is for Tech Risk. It covers sending the engine a team's answers, bringing the engine's output back, and reading the result.

## Open the comparison

The "Compare with the engine" link sits on the Groups page and on each team's results page. The first page lists every team with the result of its last comparison. Choose Open for one team. Uploading is for Tech Risk. Anyone who can see the team can read its comparison.

## Step 1: download the engine's input

On a team's comparison page, choose "Download this team's answers for the engine". It gives a JSON file of the team's answers, keyed the way the engine's driver rules read them, plus the team's ID and name. It uses the answers of the team's newest assessment, which is the one the comparison is made against.

**Wanted:** confirm this file's layout with the engine's owner. The page says the same.

## Step 2: upload the engine's output

Run the engine, then on the same page choose the file and "Upload and compare". The file is the engine's JSON for that team (schema 2.0). Only `risks` is needed. Level words can be in any case. Each upload is kept with who sent it, when and a short file ID, and the newest upload is the one compared.

The page tells you if something is missing or unreadable, and still compares what it can. A file that is not JSON, or has no `risks`, is refused with the reason.

## Step 3: read the result

The page says which engine file and which site assessment it compared (their dates). A summary line gives the counts, such as "7 risks the same, 1 different, 2 site only".

| Result | What it means |
|---|---|
| Same | Both agree. |
| Different | One side says Critical or High and the other says something else. The reason is written under the risk: what each side says, the site's own steps, and the drivers that are on in only one of the two. |
| Site only | The site says Medium, Low or "does not apply", and the engine has no rating to match. These are new on the site, so they are not differences. |
| Engine only | The engine rated a risk that the site's risk files don't have. |

Differences come first, then Engine only, then "Drivers that differ", then Same and Site only. A difference in drivers is often the cause of a difference in a rating.

If there are no differences, the page says the site rates every Critical and High risk the way the engine does.

> **Example.** The summary reads "7 risks the same, 1 different, 2 site only". The Different row says the engine rates the likelihood High and the site rates it Medium, and lists one driver that is on in the engine only. Tech Risk checks that driver's answer.

Nothing on this page changes how a rating is worked out.

## Download the risks and drivers

The Groups page also has "Download risks and drivers", a .zip laid out like TRAC's engine folder. It is open to anyone who can open the Risk site.

## Related guides

- [Changing the rating settings and lists](/guides/changing-the-rating-settings-and-lists/)

If you're unsure, Tech Risk can help.
