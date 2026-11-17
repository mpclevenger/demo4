"""Step 4, PUBLISH: put every scored month into one data.json and a ready-to-open page.

Reads store/scored/*.json, adds what needs more than one month (prior value, change arrows,
history, New red / Chronic red on the watch list, trend) only where the earlier month is scored,
and writes:

    store/published/data.json     the data the front end reads
    store/published/index.html    the front end with that data built in (serve the folder, open it)
    store/published/evidence.json the items behind each family's numbers ("What's driving it")

The front end's own definitions (building blocks, metrics, dictionary, method page) are kept as they are.
Nothing synthetic is carried over: the prototype's families are replaced.
"""
import json
import os
import pathlib
import re
import shutil
import time

from . import codelinks, config, evidence, linking, measure, score_month, scoring, storage, store


def previous_month(month):
    """The calendar month before, as text: 2026-01 gives 2025-12."""
    year, month_number = int(month[:4]), int(month[5:7])
    return f"{year - 1}-12" if month_number == 1 else f"{year}-{month_number - 1:02d}"


def _prev(month, months):
    """The calendar month before, if it is scored; else None. Every month stands alone (DEVELOPER_GUIDE.md rule 1):
    change arrows and trends compare with the month just before, never a month further back."""
    earlier = previous_month(month)
    return earlier if earlier in months else None


TREND_MIN_BLOCKS = 3      # Sharp drop and Declining only for TRUST scores resting on at least this many blocks
SHARP_DROP_POINTS = 10    # Sharp drop: TRUST down this many points or more ...
SHARP_DROP_WORSE_METRICS = 2     # ... with at least this many metrics worse than the month before
EARLIER_MONTHS_KEPT = 2   # a metric's history keeps the statuses of this many earlier months, then this month's
CHRONIC_RED_MONTHS = EARLIER_MONTHS_KEPT + 1     # Chronic red: Red this month and in each earlier month kept


def _blocks(f):
    """A family-month's block scores."""
    return f.get("blocks") or {}


def _blocks_scored(f):
    """How many blocks a family-month's TRUST rests on (older months without the count: worked out)."""
    n = f.get("blocks_scored")
    if n is not None:
        return n
    return sum(1 for B in _blocks(f).values() if B.get("score") is not None)


# Watch-list order (owner, 1 Nov 2026: the CTO page shows the top 10 in this order); the page groups them.
WATCH_ORDER = ["Override red", "New red", "Chronic red", "Sharp drop", "Declining", "Behind peers"]
RANK = {"Green": 0, "Amber": 1, "Red": 2}


def _watch(fid, name, fr, pf, ppf):
    """Watch-list items for one family-month. pf / ppf: the same family one and two months before (or None).

    Rules from 02_metric_dictionary and the old demo's reference (docs/reference/old-demo):
      Override red  a metric made Red by an automatic Red rule
      New red       Red now, not Red the month before
      Chronic red   Red this month and the two months before (CHRONIC_RED_MONTHS)
      Sharp drop    TRUST down SHARP_DROP_POINTS or more, with at least SHARP_DROP_WORSE_METRICS metrics worse
                    than the month before
      Declining     a block's score fell this month and the month before
      (Sharp drop and Declining are skipped when this month's or the month before's TRUST rests on fewer than
       TREND_MIN_BLOCKS blocks, so a file arriving or not doesn't look like a fall; owner, 4 Nov 2026.)
      Behind peers  worse than the typical family by the metric's gap (set when scoring)
    None of them changes a status or a score."""
    out = []
    add = lambda kind, mid, text: out.append(dict(kind=kind, family_id=fid, metric_id=mid, text=f"{name}: {text}"))
    for mid, r in fr["metrics"].items():
        pr = pf["metrics"].get(mid) if pf else None
        if r["status"] == "Red" and r.get("override"):
            add("Override red", mid, f"{mid} is Red by an automatic Red rule")
        elif r["status"] == "Red" and pr:
            streak = 0
            for s in reversed(r["history"]):
                if s != "Red":
                    break
                streak += 1
            if streak >= CHRONIC_RED_MONTHS:
                add("Chronic red", mid, f"{mid} Red this month and the two months before")
            elif pr["status"] != "Red":
                add("New red", mid, f"{mid} turned Red")
    enough = lambda *fs: all(_blocks_scored(f) >= TREND_MIN_BLOCKS for f in fs if f)
    if enough(fr, pf) and pf and fr.get("delta") is not None and fr["delta"] <= -SHARP_DROP_POINTS:
        worse = sum(1 for mid, r in fr["metrics"].items()
                    if mid in pf["metrics"] and r["status"] in RANK and pf["metrics"][mid]["status"] in RANK
                    and RANK[r["status"]] > RANK[pf["metrics"][mid]["status"]])
        if worse >= SHARP_DROP_WORSE_METRICS:
            add("Sharp drop", None, f"TRUST fell {-fr['delta']} points")
    if enough(fr, pf, ppf) and pf and ppf:
        fr["declining"] = [c for c in _blocks(fr)
                           if (_blocks(fr).get(c, {}).get("delta") or 0) < 0
                           and (_blocks(pf).get(c, {}).get("delta") or 0) < 0]
        if fr["declining"]:
            add("Declining", None, f"{', '.join(fr['declining'])} fell two months in a row")
    listed = {i["metric_id"] for i in out}          # a metric already on the list as Red isn't listed twice
    for mid, r in fr["metrics"].items():
        if r.get("behind_peers") and mid not in listed:
            add("Behind peers", mid, f"{mid} {r['value']} vs typical {r['typical']}")
    return out


def build(empty_months=()):
    """Assemble data.json from every scored month. Returns the dict.

    empty_months (YYYY-MM): months to show although they aren't scored, each with no results, saying
    "Not scored yet" (owner, 4 Nov 2026: the real site shows from the start, and a month with uploads can be
    picked before it is scored). Nothing is saved: these months exist only in what is returned."""
    tpl = score_month.template()
    settings = score_month.thresholds_config()        # read once for the whole page
    real = storage.months("scored")
    extra = sorted(set(empty_months or ()) - set(real))
    if not real and not extra:
        raise ValueError("no month has been scored yet: run  python manage.py score YYYY-MM")
    scored = {m: storage.load_month("scored", m) for m in real}
    for m in extra:
        scored[m] = score_month.score_month({"month": m, "feeds": {}, "notes": []}, settings, tpl)
        scored[m]["period"].setdefault("meta", {})["not_scored"] = True    # shown, but nothing scored yet
    months = sorted(scored)

    # The team list is the newest scored month's that has teams (made from HR); older months keep their own results.
    # Owner, 17 Nov 2026: a newer month scored without HR has no teams, and the list (team picker, L3 pages) was empty.
    with_teams = [m for m in real if scored[m]["families"]]
    families = scored[with_teams[-1]]["families"] if with_teams else []
    names = {f["id"]: f["name"] for m in months for f in scored[m]["families"]}
    # Every page reads each listed team in every month. A month with no team of its own (scored without HR, or a
    # team that is new since) gets the team shown as not scored, instead of breaking the page (owner, 17 Nov 2026).
    for m in months:
        teams = scored[m]["period"].setdefault("families", {})
        why = ("This L3 team wasn't in this month's HR file: not scored" if teams else
               "No HR file this month, so nobody could be placed in an L3 team: not scored")
        if not teams and families:
            scored[m]["period"].setdefault("meta", {})["no_teams"] = True    # the page opens on a month with teams
        for f in families:
            if f["id"] not in teams:
                teams[f["id"]] = score_month._scored({x["id"]: score_month.blank_result("N/A", why)
                                                      for x in tpl["metrics"]}, tpl, settings)
    periods = {}
    for m in months:
        p = scored[m]["period"]
        pm = _prev(m, months)
        prev = periods.get(pm) if pm else None
        p["watch_list"] = []
        for fid, fr in p["families"].items():
            pf = prev["families"].get(fid) if prev else None
            if pf and fr["trust"] is not None and pf["trust"] is not None:
                fr["delta"] = fr["trust"] - pf["trust"]
            for c, B in _blocks(fr).items():
                pb = _blocks(pf).get(c) if pf else None
                if pb and B["score"] is not None and pb["score"] is not None:
                    B["delta"] = B["score"] - pb["score"]
            for mid, r in fr["metrics"].items():
                pr = pf["metrics"].get(mid) if pf else None
                if pr:
                    r["prior_value"], r["prior_status"] = pr["value"], pr["status"]
                    r["history"] = (pr.get("history") or [])[-EARLIER_MONTHS_KEPT:] + [r["status"]]
                else:
                    r["history"] = [r["status"]]
            ppm = _prev(pm, months) if pm else None
            ppf = periods[ppm]["families"].get(fid) if ppm and ppm in periods else None
            p["watch_list"] += _watch(fid, names.get(fid, fid), fr, pf, ppf)
        p["watch_list"].sort(key=lambda w: WATCH_ORDER.index(w["kind"]))
        if prev:
            for mid, x in p["firm"].items():
                px = prev["firm"].get(mid, {})
                x["prior_value"], x["prior_status"] = px.get("value"), px.get("status")
            if p["firm_trust"] is not None and prev["firm_trust"] is not None:
                p["firm_trust_delta"] = p["firm_trust"] - prev["firm_trust"]
        periods[m] = p

    data = dict(tpl)
    data["metrics"] = _metric_list(tpl, periods)
    data.update(
        # The firm tolerance threshold is a setting; with no value set, the page leaves out the line and the sentence.
        firm_tolerance=_firm_tolerance(settings),
        min_families_for_threshold=score_month.min_families(settings),      # shown in the dictionary
        behind_peers_flag=score_month.rule_is_on(settings, "behind_peers_flag"),
        automatic_red_rules=score_month.rule_is_on(settings, "automatic_red_rules"),   # owner, 9 Nov 2026
        data_sources=config.data_sources(),            # who owns each data source (owner, 9 Nov 2026)
        caps=scoring.caps_from(settings.get("caps")),  # the current caps; each month keeps its own
        code_links=codelinks.links(),      # where each metric card's code lives (owner, 5 Nov 2026); url is None without code_repo_url
        code_places=codelinks.page_places(),   # where the watch list, feed readers and upload checks live in the code (owner, 16 Nov 2026)
        env_label=env_label(), test_env=is_test_env(), live=True, feeds=list(store.FEEDS), families=families,
        periods=periods,
        all_metrics={m: all_metrics_block(scored[m], periods[m], m) for m in months},     # the All metrics page (owner, 17 Nov 2026)
        trend=dict(months=months,
                   firm=[periods[m]["firm_trust"] for m in months],
                   families={f["id"]: [periods[m]["families"].get(f["id"], {}).get("trust") for m in months]
                             for f in families},
                   incomplete_months=[m for m in months if periods[m]["firm_incomplete"]]))
    return data


RESULT_FIELDS = ("value", "status", "numerator", "denominator", "provisional")    # what the team page's Result cell reads


def _l4_team_names(month):
    """{L4 leader's work email, lower case: the L4 team's name} for a month, from its mapped people. Empty when the
    month has no mapped people."""
    mapped = storage.load_month("mapped", month) or {}
    people = ((mapped.get("feeds") or {}).get("hr") or {}).get("people") or []
    email_of = {person["sam_account"]: (person.get("email") or "").lower() for person in people if person.get("sam_account")}
    names = {}
    for leader_sam, team in linking.l4_teams(people, linking.l3_level(mapped.get("settings_used"))).items():
        if email_of.get(leader_sam):
            names[email_of[leader_sam]] = team["name"]
    return names


def all_metrics_block(scored, period, month):
    """What the "All metrics" page reads for one month (owner, 17 Nov 2026). It is open to every role, so it holds only
    what that page shows for every team: each metric's result as the team page shows it, and each metric's by_l4
    counts (the same by_l4 the team's evidence holds; counts only, never scored).

    {"teams": {team: {metric: {"result": {...}, "by_l4": {...}}}}, "l4_team_names": {leader email: team name}}"""
    by_l4 = evidence.by_l4_of_month(scored)
    teams = {}
    for team_id, team in (period.get("families") or {}).items():
        entries = {}
        for metric_id, result in (team.get("metrics") or {}).items():
            entry = {"result": {field: result[field] for field in RESULT_FIELDS if field in result}}
            split = (by_l4.get(team_id) or {}).get(metric_id)
            if split is not None:
                entry["by_l4"] = split
            entries[metric_id] = entry
        teams[team_id] = entries
    return {"teams": teams, "l4_team_names": _l4_team_names(month)}


def is_test_env():
    """The TEST environment is the same code with the config var TRUST_ENV=test (owner, 4 Nov 2026). Only it may hold
    seed data; the page says so on every screen."""
    return (os.environ.get("TRUST_ENV") or "").strip().lower() == "test"


def env_label():
    return "TEST · synthetic data" if is_test_env() else "Live data"


def _firm_tolerance(settings):
    value = settings.get("firm_tolerance")
    return {"value": value} if isinstance(value, (int, float)) else None


def page_html(data):
    """The front end with this data built in."""
    safe = json.dumps(data, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")   # keep the JSON from closing the script tag
    html = (config.ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    return re.sub(r'(<script type="application/json" id="data">).*?(</script>)',
                  lambda m: m.group(1) + safe + m.group(2), html, count=1, flags=re.S)


def _metric_list(tpl, periods):
    """The page's metric list from the definitions; a metric with no source yet is marked wanted."""
    metrics = []
    wanted_notes = measure.wanted_shown()
    for x in tpl["metrics"]:
        if x["id"] in wanted_notes:
            x = dict(x, wanted_shown=True)
        metrics.append(x)
    return metrics


def with_current_definitions(data):
    """The metrics and their dictionary cards as deployed now (config/metrics.json), not the copy saved at the
    last update (owner, 8 Nov 2026: a changed definition shows as soon as it is deployed). Scores and every
    month's results are left exactly as published; only Update changes those."""
    tpl = score_month.template()
    data = dict(data)
    data["metrics"] = _metric_list(tpl, data.get("periods") or {})
    data["dictionary"] = dict(data.get("dictionary") or {}, metrics=tpl["dictionary"]["metrics"])
    settings = score_month.thresholds_config()
    data["behind_peers_flag"] = score_month.rule_is_on(settings, "behind_peers_flag")
    data["automatic_red_rules"] = score_month.rule_is_on(settings, "automatic_red_rules")
    data["data_sources"] = config.data_sources()
    # The files the running code reads, not the list saved at the last update (owner, 17 Nov 2026: a file added in
    # a newer version, Repo contributors, had no upload row until someone pressed Update).
    data["feeds"] = list(store.FEEDS)
    data["code_links"] = codelinks.links()
    data["code_places"] = codelinks.page_places()
    return data


_BUILT = {}    # the last page data built for months not yet published, and what it was built from


def site_data(published, current_month):
    """What the website shows: the published data, plus any month with uploads that isn't scored yet; before
    anything is published, the real site for the current month with no data. Built only when needed."""
    shown = set((published or {}).get("periods") or {})
    # Months with uploads, and always the current month, so its files can be uploaded (owner, 4 Nov 2026).
    missing = sorted({m for m in storage.upload_months() + [current_month] if m not in shown})
    # A copy published by a version before 17 Nov 2026 can carry an empty team list while its months have teams
    # (owner, 17 Nov 2026: trustCheck() showed "L3 teams listed: 0" with 13 teams in October). Build it again from
    # the scored months instead of serving it, so the picker, the L3 teams link and the team pages come back.
    stale = bool(published) and not published.get("families") and any(
        (p or {}).get("families") for p in (published.get("periods") or {}).values())
    if published and not missing and not stale:
        return with_current_definitions(published)
    # Building the page data is the slow part, and it was done on every visit while a month had no publish yet
    # (owner, 17 Nov 2026: "super slow"). Keep it until something is uploaded, updated or changed (each of those
    # writes the activity log), and at most a minute.
    newest = (storage.events(limit=1) or [{}])[0]
    key = (tuple(sorted(shown)), tuple(missing), newest.get("at"), newest.get("action"), newest.get("note"))
    kept = _BUILT.get("key") == key and time.monotonic() - _BUILT.get("when", 0) < 60
    if not kept:
        data = build(empty_months=missing)
        if not published:
            data["nothing_published"] = True
        _BUILT.update(key=key, when=time.monotonic(), data=json.dumps(data, ensure_ascii=False))
    return json.loads(_BUILT["data"])


def run(by="command line"):
    data = build()
    text = json.dumps(data, ensure_ascii=False)
    html = page_html(data)
    # The items behind each family's numbers, for the drill-down "What's driving it" (owner, 3 Nov 2026).
    ev = {m: evidence.page_evidence(storage.load_month("scored", m)) for m in data["periods"]}
    out = storage.save_published({"index.html": html, "data.json": text,
                                  "evidence.json": json.dumps(ev, ensure_ascii=False)})
    if isinstance(out, pathlib.Path):      # a folder (no database): the page's own files go with it, so the folder opens on its own
        for folder in ("shared", "pages"):
            shutil.copytree(config.ROOT / "frontend" / folder, out / folder, dirs_exist_ok=True)
    storage.log("publish", by, None, f"{len(data['periods'])} {'month' if len(data['periods']) == 1 else 'months'} on the scorecard")
    return out
