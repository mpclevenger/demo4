# Repo contributors (file `repo_contributors_<YYYY-MM>.csv`)

**Provider:** Tech Risk, from GitHub Enterprise Server. **Made by** `tools/github_repo_export.py`, in the same run as the [repos file](repos.md).

## What it is

For one month, the people who committed to each repo's **default branch**. One row per person per repo. It feeds the drivers that need to know how many people work in a repo. Archived repos, forks and empty repos are left out. Bots (`dependabot`, `renovate`, `github-actions`, `jenkins`, names ending `[bot]`) are not counted as people.

## Columns

`Repository`, `Month`, `Contributor login`, `Contributor email`, `Commits`

- `Repository` is written the same way as `Repo` in the repos file (`org/repo` when several orgs are exported).
- `Month` is `YYYY-MM`.
- `Contributor login` is the GitHub login when the commit has one. When it doesn't, it is empty and the person is counted by email.
- `Contributor email` is what TRUST matches people on, so the export makes it as reliable as it can. It uses the commit's own author email (lower case). If that is a GitHub no-reply address (`...@users.noreply...`) or empty, and the commit has a login, the export looks up that person's **public email** on their GitHub profile (once per login, then remembered) and uses it when there is one. When there isn't, the no-reply address stays as it is. `Contributor login` is kept as well.
- `Commits` is how many commits that person made to the default branch in the month.

Rows within a repo run from the most commits to the fewest.

## Running it (Windows PowerShell)

Set `GITHUB_HOST` and `GITHUB_TOKEN` first, as for the repos file. Then:

```powershell
# last full month, languages and contributors both on:
python tools/github_repo_export.py

# a chosen month:
python tools/github_repo_export.py --month 2026-10

# leave one part out:
python tools/github_repo_export.py --no-with-contributors
python tools/github_repo_export.py --no-with-languages
```

Files are written to the folder you run it from: `repos.csv` and `repo_contributors_2026-10.csv`.

**Cost.** The month's first 100 commits for each repo come back with the repo settings, 25 repos per request, so a quiet repo costs nothing extra. Only busier repos need more: one request per extra 100 commits. Public emails for hidden addresses are looked up 50 people per request. The export prints the estimate before it starts (for example "This takes about 120 requests, about 8 minutes at 900 per hour") and keeps to the 900 per hour budget. Leave the window open.

**Busy repos.** For each repo it reads at most **10 pages of 100 commits** (setting `CONTRIBUTOR_MAX_PAGES` in the script). If a repo had more commits than that in the month, the people with only older commits may be missing. That repo is named in the window and in `repo_contributors_<month>.notes.txt`, next to the file.

## If the run stops part-way

Run the **same command** again (same month, same options). It carries on where it stopped:

- `repos.progress.json` remembers which page of repos it reached.
- `repo_contributors_<month>.progress.json` lists the repos already finished for the month. Those are not read again.

Both files disappear when the run finishes. If you change the month or the options, the export says so and asks you to add `--fresh` to start over. `--fresh` also deletes the month's earlier contributors file.
