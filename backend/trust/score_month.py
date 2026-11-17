"""Step 3b, SCORE: turn a mapped month into results, statuses, building-block and TRUST scores.

    measured counts (measure.py)  ->  value per family  ->  tolerance thresholds (config/thresholds.json)
    ->  Green / Amber / Red  ->  blocks and TRUST (scoring.py)  ->  store/scored/<month>.json

Each month stands alone: nothing here needs another month. A metric whose file hasn't arrived is
'No data' (DNR) and left out of its block. Rows not placed with a family count in the firm totals
and in 'Not yet mapped', never in a family.
"""
import calendar
import json
import re
import statistics
from datetime import date, datetime, timedelta

from . import config, measure, scoring, storage, tolerances
from .numbers import percent, r1
from .intake.common import loads_tolerant
from .linking import UNATTRIBUTED

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
FEED_PROVIDER = {"tcc": "Change", "ntcc": "Change", "actions": "Ops", "postmortems": "Ops",
                 "cx_sast": "Cyber", "cx_sca": "Cyber", "hr": "HR", "hr_mapping": "Tech Risk"}


# Starting numbers the rules use when a setting is missing.
DEFAULT_MIN_FAMILIES = 5         # family results needed to set a prevailing median (setting min_families_for_threshold)
QUARTILES = 4                    # the usual spread between families is the gap between the first and last quarter
INCIDENTS_LISTED = 10            # incident ids named in a note before it stops listing
PERCENT_UNIT_WORD = "points"     # the unit word of a percentage metric: its limits are kept between 0 and 100
FULL_PERCENT = 100.0


def incidents_per_10_apps(incidents, apps):
    """Incidents for every 10 confirmed apps, one decimal, half up: 3 incidents on 12 apps gives 2.5."""
    return r1(measure.APPS_PER_RATE * incidents / apps)


def meets(value, limit, higher_is_better):
    """True when the value is at the limit or on the better side of it."""
    return value >= limit if higher_is_better else value <= limit


def rule_is_on(settings, rule_name):
    """Whether a switchable rule (automatic_red_rules, behind_peers_flag) is on: on unless its setting says off."""
    return bool(settings.get(rule_name, True))


def label(month):
    year, month_number = month.split("-")
    return f"{MONTHS[int(month_number) - 1]} {year}"


def template():
    """The front end's built-in data (building blocks, method page) plus every metric and its dictionary card,
    which come from config/metrics.json (owner, 8 Nov 2026: one place to edit a metric)."""
    html = (config.ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    data_block = re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S)
    tpl = json.loads(data_block.group(1))
    defs = config.metrics()
    parts = ("card", "known_limits", "wording", "counting", "status_note")
    tpl["metrics"] = [dict(id=mid, **{k: v for k, v in x.items() if k not in parts and not k.startswith("_")})
                      for mid, x in defs.items()]
    from trust import editable
    from trust.risk import registers
    uploaded_risks, _uploaded_drivers = registers.uploaded_registers()
    risks = uploaded_risks if uploaded_risks is not None else config.risks()      # the Risk site's current risks
    watched = editable.all_metric_risks()                # as Tech Risk has them on the site
    tpl.setdefault("dictionary", {})["metrics"] = {mid: dictionary_card(x, risks, watched.get(mid)) for mid, x in defs.items()}
    return tpl


def dictionary_card(x, risks=None, watched=None):
    """One metric's dictionary card as the page reads it: the card, its known limitations, its wording and the
    risks it watches (from the risk assessment engine's files in config/risks/)."""
    c = {k: v for k, v in (x.get("card") or {}).items() if not k.startswith("_")}
    c.setdefault("override_rule", x.get("override_rule"))
    c["status"] = x.get("status") or "Measured"
    if c["status"] != "Measured":              # In progress or Wanted: counts in no score, shows No data
        c["not_measured"] = True
    c.setdefault("thresholds", [])
    c.setdefault("proposed_fields", None)
    limits = x.get("known_limits") or []
    c["limitations"] = [r.get("limit", "") for r in limits]
    c["countermeasures"] = [r.get("mitigation", "") for r in limits]
    c["limitations_table"] = [dict(limitation=r.get("limit", ""), mitigation=r.get("mitigation", ""),
                                   status=r.get("status") or "No mitigation yet") for r in limits]
    if x.get("wording"):
        c["wording"] = x["wording"]
    if watched is not None:                              # the list on the site wins over the file's card.risks
        c["risks"] = list(watched)
    c["risks_detail"] = []
    for rid in c.get("risks") or []:
        r = (risks or {}).get(rid)
        c["risks_detail"].append({"id": rid, "missing": True} if r is None else
                                 {"id": rid, **{k: str(r.get(k) or "").strip() for k in ("domain", "category", "name", "description")}})
    return c


def thresholds_config():
    path = config.config_file("TRUST_THRESHOLDS", "thresholds.json")
    doc = loads_tolerant(path.read_text(encoding="utf-8"))
    # the file's values, with any tolerance threshold or cap changed on the site in its place (owner, 15 Nov 2026)
    return tolerances.effective({k: v for k, v in doc.items() if not k.startswith("_")})


def plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


def _day(iso):
    """'2026-11-03' -> '3 Nov 2026' for the reasons people read."""
    try:
        d = datetime.strptime(str(iso), "%Y-%m-%d")
        return f"{d.day} {d.strftime('%b %Y')}"
    except (TypeError, ValueError):
        return str(iso or "")


def min_families(cfg):
    """Fewest family results needed to set a tolerance threshold from the median (setting; 5 unless set)."""
    fewest = cfg.get("min_families_for_threshold", DEFAULT_MIN_FAMILIES)
    if isinstance(fewest, int) and not isinstance(fewest, bool) and fewest >= 1:
        return fewest
    return DEFAULT_MIN_FAMILIES


def no_threshold_reason(n, cfg):
    need = min_families(cfg)
    if n < need:
        return (f"No tolerance threshold yet: {plural(n, 'L3 team has', 'L3 teams have')} a result and "
                f"{need} are needed. Not scored this month")
    return "No tolerance threshold for this metric yet: not scored"


def thresholds_for(mid, values, higher_is_better, cfg, unit_word=PERCENT_UNIT_WORD):
    """Green tolerance and Red limit for one metric this month. values: family results that count.

    Owner, 3 Nov 2026: a prevailing-median threshold is calculated from the month's own data; there are no
    static starting values. Owner, 4 Nov 2026: it needs at least `min_families_for_threshold` family results
    (a setting, 5); with fewer there is no threshold and the metric isn't scored that month."""
    metric_settings = cfg["metrics"].get(mid, {})
    if metric_settings.get("basis") == "Policy":
        set_from = metric_settings.get("set_from")
        reason = (f"Set from the {set_from} (set {_day(metric_settings.get('set_on'))}); reviewed quarterly" if set_from
                  else f"Set by {metric_settings['set_by']} on {_day(metric_settings.get('set_on'))}" if metric_settings.get("set_by")
                  else "Initial tolerance thresholds for go-live")
        return dict(green=metric_settings["green"], red=metric_settings["red"], basis="Policy", provisional=False,
                    reason=reason, set_from=set_from, set_on=metric_settings.get("set_on"),
                    set_by=metric_settings.get("set_by"))
    if not values or len(values) < min_families(cfg):
        return None
    median = r1(statistics.median(values))
    spread = 0.0
    if len(values) >= QUARTILES:
        first_quartile, _, third_quartile = statistics.quantiles(values, n=QUARTILES, method="inclusive")
        spread = third_quartile - first_quartile
    band = r1(max(metric_settings.get("amber_band_min", cfg["amber_band_min_points"]),
                  cfg["amber_band_spread_multiple"] * spread))
    red = r1(median - band) if higher_is_better else r1(median + band)
    if unit_word == PERCENT_UNIT_WORD:            # a percentage: a limit can't go below 0% or above 100%
        red = min(FULL_PERCENT, max(0.0, red))
    return dict(green=median, red=red, band=band, basis="Calibrated", provisional=True, unit_word=unit_word,
                reason=f"Prevailing median of {plural(len(values), 'family', 'families')} ({{month}}); "
                       f"Amber band {band:g} {unit_word}; provisional")


def _amt(x):
    """A number for a reason: no '.0' on whole numbers (0.5 stays 0.5)."""
    return f"{x:g}" if abs(x - round(x)) > 1e-9 else f"{int(round(x))}"


def _qty(x, word):
    """'1 incident', '1.5 incidents', '1 point': the unit word follows the number."""
    return f"{_amt(x)} {word[:-1] if x == 1 and word.endswith('s') else word}"


def status_of(value, threshold, higher_is_better, unit):
    """Green / Amber / Red against the thresholds, with the plain reason shown on the page."""
    percent_sign = "%" if unit == "%" else ""
    green, red = threshold["green"], threshold["red"]
    if threshold["basis"] == "Policy":
        if meets(value, green, higher_is_better):
            return "Green", f"Within Green tolerance ({'≥' if higher_is_better else '≤'} {green:.1f}{percent_sign})"
        if meets(value, red, higher_is_better):
            return "Amber", "Between tolerance and Red limit"
        return "Red", f"Past the Red limit ({'<' if higher_is_better else '>'} {red:.1f}{percent_sign})"
    word = "median"
    band, band_word = threshold.get("band", 5), threshold.get("unit_word", PERCENT_UNIT_WORD)
    # a percentage metric shows its limits as 12.5%; a count metric shows them in its unit ("2 incidents")
    show = (lambda x: f"{x:.1f}{percent_sign}") if percent_sign else (lambda x: _qty(x, band_word))
    amber = _qty(band, band_word)
    if meets(value, green, higher_is_better):
        return "Green", (f"At or {'above' if higher_is_better else 'below'} the prevailing {word} "
                         f"(Green tolerance: {'at least' if higher_is_better else 'at most'} {show(green)})")
    if meets(value, red, higher_is_better):
        return "Amber", (f"{'Below' if higher_is_better else 'Above'} the prevailing {word}, within the Amber band of {amber} "
                         f"(Red limit: {'less' if higher_is_better else 'more'} than {show(red)})")
    return "Red", (f"More than the Amber band of {amber} {'below' if higher_is_better else 'above'} the prevailing {word} "
                   f"(Red limit: {'less' if higher_is_better else 'more'} than {show(red)})")


# The behind-peers flag needs at least this many families with a scored result (02_metric_dictionary §1.3). It starts
# at the same number as the prevailing-median setting but is its own rule: it does not follow that setting.
PEER_MIN_FAMILIES = DEFAULT_MIN_FAMILIES


def flag_behind_peers(results, tpl, thresholds, flag_on):
    """Typical value and the behind-peers flag, per metric, across families (owner, 3 Nov 2026).

    Typical = the median of the families' scored results this month (the middle family). It is shown as
    context, so it is the real median even where a policy sets the Green tolerance. A family is behind
    peers when its result is worse than typical by at least the metric's gap (dictionary peer_flag_gap).
    The flag puts an item on the watch list only: it never changes a status or a score.
    Flagged only where a policy sets the tolerance threshold: a metric judged against the prevailing
    median already compares each family with the median, so a flag would say the same thing twice (the
    v1 design's dictionary card). Not flagged either: metrics with no gap (pass/fail, information only),
    and plain counts (UN-01 until the app inventory arrives), whose gap is written per 10 apps."""
    gaps = {mid: x.get("peer_flag_gap") for mid, x in tpl["dictionary"]["metrics"].items()}
    higher_is_better = {m["id"]: m["higher_is_better"] for m in tpl["metrics"]}
    for mid in higher_is_better:
        rows = [r[mid] for r in results.values()
                if mid in r and r[mid]["status"] in scoring.POINTS_BY_STATUS and not r[mid].get("provisional")
                and r[mid].get("value") is not None]
        if not rows:
            continue
        typical = r1(statistics.median(r["value"] for r in rows))
        for r in results.values():
            if mid in r and r[mid].get("typical") is not None:
                r[mid]["typical"] = typical
        gap = gaps.get(mid)
        if (not flag_on or gap is None or higher_is_better[mid] is None or mid in measure.PER_10_APPS or len(rows) < PEER_MIN_FAMILIES
                or (thresholds.get(mid) or {}).get("basis") != "Policy"):
            continue
        for r in rows:
            worse = typical - r["value"] if higher_is_better[mid] else r["value"] - typical
            if worse >= gap:
                r["behind_peers"] = True


def own_date_of(stored_file):
    """The date a file states for itself, or None. A Checkmarx file with no report date records the upload date as
    its date; that is not the file's own date, so it does not count."""
    if stored_file.get("as_of_source") == "upload date":
        return None
    return stored_file.get("as_of")


def data_as_of(file_as_of, uploaded_at, month):
    """The date a file's data is good to, shown on the pages as "Data as of".

    Never later than the data really is (owner, 15 Nov 2026): providers reconcile their own numbers, so the page
    must not say the data is newer than it is.
    - A file that states its own date: that date.
    - A file that states none: the last day of its month, or the day it was uploaded if that came first.
    Worked example: an October 2026 file with no date of its own, uploaded on 5 Nov 2026, gives 31 Oct 2026.
    """
    if file_as_of:
        return str(file_as_of)[:10]
    year, month_number = int(month[:4]), int(month[5:7])
    last_day_of_month = date(year, month_number, calendar.monthrange(year, month_number)[1])
    if not uploaded_at:
        return last_day_of_month.isoformat()
    upload_day = date.fromisoformat(str(uploaded_at)[:10])
    return min(last_day_of_month, upload_day).isoformat()


def contract_blocks(mid, contracts=None):
    """The reason a metric may not be scored from its feed under the feed's approved data contract, or None."""
    feeds = [f for m, f in measure.needs().items() if m == mid] + ([measure.needs_also()[mid]] if mid in measure.needs_also() else [])
    if contracts is None:
        contracts = storage.approved_contracts()
    for feed in feeds:
        c = contracts.get(feed)
        if c and mid not in (c.get("metrics") or []):
            return (f"Not in the data contract for the {feed} file (version {c['version']}): the provider has not "
                    f"approved its use for {mid}. Request a new contract version on the Data dictionary page")
    return None


def blank_result(status, reason, **kw):
    r = dict(value=None, numerator=None, denominator=None, status=status, points=scoring.POINTS_BY_STATUS.get(status),
             reason=reason, provisional=False, carried_from=None, override=False, behind_peers=False,
             typical=None, history=[], prior_value=None, prior_status=None)
    r.update(kw)
    return r


def empty_reason(mid, all_unplaced):
    """Why a family has nothing to count: counting.empty_reason in config/metrics.json (empty_reason_unplaced
    when none of the items could be placed with a family)."""
    c = config.counting(mid)
    return (all_unplaced and c.get("empty_reason_unplaced")) or c.get("empty_reason") or "No items: not scored"


def _merge(a, b):
    """Add one set of counts to another (numbers summed, lists joined, flags or-ed)."""
    if a is None:
        return {k: (list(v) if isinstance(v, list) else v) for k, v in b.items()}
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, bool):
            out[k] = bool(a.get(k)) or v
        elif isinstance(v, (int, float)) and isinstance(a.get(k, 0), (int, float)) and not isinstance(a.get(k), bool):
            out[k] = a.get(k, 0) + v
        elif isinstance(v, list):
            out[k] = list(a.get(k) or []) + v
        else:
            out.setdefault(k, v)
    return out


def expand_shared(counts, shared):
    """Per-family counts with each shared group's counts added to every family its lead leads (owner, 6 Nov 2026:
    a lead of several families rolls up to each of them; the same numbers show for each until the data is more
    granular). The firm keeps using the original counts, so the group is counted once there. A count-only metric
    (UN-01) has a unique count: an incident already in the family isn't counted twice."""
    if not shared:
        return counts
    out = {}
    for mid, by_fam in counts.items():
        fam = {k: v for k, v in by_fam.items() if k not in shared}
        for g, fids in shared.items():
            if g not in by_fam or not isinstance(by_fam[g], dict):
                continue
            for fid in fids:
                fam[fid] = _merge(fam.get(fid), by_fam[g])
                if mid in measure.PER_10_APPS:
                    seen, items = set(), []
                    for it in fam[fid].get("items") or []:
                        if it.get("id") not in seen:
                            seen.add(it.get("id"))
                            items.append(it)
                    fam[fid]["items"], fam[fid]["numerator"] = items, len(items)
        out[mid] = fam
    return out


def family_tiers(feeds):
    """{family_id: (Tier 0/1 applications, all applications)} from the ITDR application file (owner, 4 Nov 2026).
    The ITDR application file is the only source of a tier: a DR test's own Tier is never used (a difference is
    a mapping warning). None when the ITDR file isn't mapped for the month, so the tier isn't known yet."""
    itdr_feed = feeds.get("itdr") or {}
    if itdr_feed.get("status") != "mapped":
        return None
    out = {}
    shared = (feeds.get("hr_mapping") or {}).get("shared") or {}
    for a in itdr_feed.get("rows") or []:
        for fid in shared.get(a.get("family_id"), [a.get("family_id")] if a.get("family_id") else []):
            t01, total = out.get(fid, (0, 0))
            out[fid] = (t01 + (a.get("recovery_tier") in measure.RE01_TIERS), total + 1)
    return out


def _scored(results, tpl, cfg):
    """Blocks, TRUST and status for one set of metric results (a family's, or the firm's pooled ones)."""
    blocks, trust, st, capped = scoring.score_family({"metrics": results}, tpl["metrics"], cfg.get("caps"),
                                               cfg.get("coverage"))
    for block in blocks.values():
        block["delta"] = None
    return dict(trust=trust, status=st, delta=None, capped=capped, declining=[], blocks=blocks,
                blocks_scored=sum(1 for block in blocks.values() if block.get("score") is not None),
                metrics=results, incomplete=any(r["status"] == "DNR" for r in results.values()))


def large_share(period, cfg):
    """Owner, 15 Nov 2026: a large team can skew the firm's figure. For each metric, the family that holds more
    than the set share of the firm's items: {metric: {family, percent, limit}}. A note only; nothing is scored."""
    default, per, out = cfg.get("large_share_flag_default"), cfg.get("large_share_flag_percent") or {}, {}
    for mid, firm_result in (period.get("firm") or {}).items():
        limit, firm_items = per.get(mid, default), (firm_result or {}).get("denominator")
        if not limit or not isinstance(firm_items, (int, float)) or isinstance(firm_items, bool) or firm_items <= 0:
            continue
        sizes = [(x.get("denominator"), fid) for fid, fr in period["families"].items()
                 for x in [(fr.get("metrics") or {}).get(mid) or {}]
                 if isinstance(x.get("denominator"), (int, float)) and not isinstance(x.get("denominator"), bool)]
        if not sizes:
            continue
        largest_items, largest_family = max(sizes)
        if 100 * largest_items / firm_items > limit:
            out[mid] = {"family": largest_family, "percent": percent(largest_items, firm_items), "limit": limit}
    return out


def _page_threshold(threshold, month):
    """A threshold as the page reads it: what thresholds_for worked out, with the month's name in its reason."""
    return dict(green=threshold["green"], red=threshold["red"], basis=threshold["basis"],
                reason=threshold["reason"].replace("{month}", label(month)), provisional=threshold["provisional"],
                band=threshold.get("band"), set_from=threshold.get("set_from"), set_on=threshold.get("set_on"),
                set_by=threshold.get("set_by"))


def _families_in(feeds):
    """The product families, from the product family owners file (doc 13 §8); none yet without it."""
    people = {p["email"]: p for p in feeds.get("hr", {}).get("people") or [] if p.get("email")}
    family_rows = feeds.get("hr_mapping", {}).get("families") or feeds.get("hr_mapping", {}).get("rows") or []
    tiers = family_tiers(feeds)
    families = []
    for row in family_rows:
        leads = [people[email]["worker"] if email in people and people[email].get("worker") else email
                 for email in row["owner_emails"]]
        tier01_apps, apps_total = tiers.get(row["family_id"], (0, 0)) if tiers is not None else (None, None)
        families.append(dict(id=row["family_id"], name=row["family"], band=row.get("band") or "product",
                             tier01=None if tiers is None else tier01_apps > 0, tier01_apps=tier01_apps,
                             apps_total=apps_total, leads=leads, accountable=leads[0] if leads else None))
    return families


def _incident_rate_results(mid, metric, counts, fids, cfg, month):
    """UN-01 (owner, 9 Nov 2026): Critical and SWE incidents per 10 confirmed apps (app inventory), against the
    prevailing median of the families that had incidents. No incident = shown, not scored (Low confidence): a rate of
    0 can't be scored with confidence. No apps = no rate. Returns (the month's threshold or None, {family: result})."""
    incidents_and_apps = {fid: ((counts.get(fid) or {}).get("numerator", 0), (counts.get(fid) or {}).get("denominator", 0))
                          for fid in fids}
    rates = {fid: incidents_per_10_apps(incidents, apps)
             for fid, (incidents, apps) in incidents_and_apps.items() if incidents and apps}
    threshold = thresholds_for(mid, list(rates.values()), metric["higher_is_better"], cfg, unit_word="per 10 apps")
    results = {}
    for fid in fids:
        (incidents, apps), unrated = incidents_and_apps[fid], (counts.get(fid) or {}).get("unrated", 0)
        result = blank_result(None, None)
        result.update(numerator=incidents, denominator=apps, unrated=unrated)
        if not apps:
            result.update(status="N/A", reason=f"No confirmed apps in the app inventory for this L3 team, so no rate "
                                               f"({plural(incidents, 'incident', 'incidents')}): not scored", points=None)
        elif not incidents:
            result.update(value=0.0, status="Low confidence", points=None,
                          reason="No Critical or SWE incidents this month: shown, not scored")
        elif threshold is None:
            result.update(value=rates[fid], status="N/A", reason=no_threshold_reason(len(rates), cfg), points=None)
        else:
            status, why = status_of(rates[fid], threshold, metric["higher_is_better"], metric["unit"])
            result.update(value=rates[fid], status=status, reason=why, points=scoring.POINTS_BY_STATUS[status],
                          typical=threshold["green"])
        if unrated:
            result["reason"] += (f". Also {plural(unrated, 'incident', 'incidents')} with no rating (DEFCON Not "
                                 f"Available or blank): shown, not counted")
        results[fid] = result
    return (_page_threshold(threshold, month) if threshold else None), results


def _percent_results(mid, metric, counts, fids, not_tier01, cfg, month):
    """A metric counted as a percent: each family's numerator out of its denominator, judged against the month's
    tolerance thresholds. Returns (the month's threshold or None, {family: result})."""
    auto_red = rule_is_on(cfg, "automatic_red_rules")      # owner, 9 Nov 2026: off for now (setting)
    fewest_items = cfg.get("low_confidence_below_items", {}).get(mid, 0)
    values = {}
    for fid in fids:
        if fid in not_tier01 and mid.startswith("RE-"):
            continue                                       # not scored on Resiliency: kept out of the median
        family_counts = counts.get(fid)
        if family_counts and family_counts["denominator"] and family_counts["denominator"] >= fewest_items:
            values[fid] = percent(family_counts["numerator"], family_counts["denominator"])
    threshold = thresholds_for(mid, list(values.values()), metric["higher_is_better"], cfg)
    all_unplaced = all(k == UNATTRIBUTED for k in counts if not k.startswith("_"))
    results = {}
    for fid in fids:
        family_counts = counts.get(fid)
        if not family_counts or not family_counts["denominator"]:
            # Owner, 9 Nov 2026 (replaces D-100's "nothing open = Green"): nothing to count is not scored,
            # UN-02 included, so a family with no open actions isn't shown as 100%.
            results[fid] = blank_result("N/A", empty_reason(mid, all_unplaced))
            continue
        value = percent(family_counts["numerator"], family_counts["denominator"])
        result = blank_result(None, None)
        result.update(value=value, numerator=family_counts["numerator"], denominator=family_counts["denominator"])
        if family_counts["denominator"] < fewest_items:
            result.update(status="Low confidence", reason=f"Fewer than {fewest_items} items: shown, not scored", points=None)
        elif mid == "TE-02" and family_counts.get("client_impact") and auto_red:   # R-TCC-12, when automatic Red rules are on
            # Owner, 3 Nov 2026: an automatic Red rule, so it also caps the Releases block at 49.
            result.update(status="Red", points=0, override=True,
                          reason=f"Automatic Red rule: {plural(family_counts['client_impact'], 'release', 'releases')} with client impact")
        elif threshold is None:
            result.update(status="N/A", reason=no_threshold_reason(len(values), cfg))
        else:
            status, why = status_of(value, threshold, metric["higher_is_better"], metric["unit"])
            # 'provisional' on a result means "an earlier month's result reused" in the front end,
            # so it stays False here; a provisional threshold says so in its own reason.
            result.update(status=status, reason=why, points=scoring.POINTS_BY_STATUS[status])
        if threshold:
            result["typical"] = threshold["green"]
        results[fid] = result
    return (_page_threshold(threshold, month) if threshold else None), results


def _family_results(metrics, meas, fcounts, cfg, month, families):
    """Step 1: every metric's result for every family, and the tolerance thresholds they were judged against.
    Returns ({metric: threshold}, {family: {metric: result}})."""
    fids = [f["id"] for f in families]
    # Not Tier 0/1 (owner, 4 Nov 2026): a family with no Tier 0 or 1 application in the ITDR application file is
    # not scored on Resilient. Only when the ITDR file is mapped for the month; otherwise the tier isn't known.
    not_tier01 = {f["id"] for f in families if f["tier01"] is False}
    thresholds, results = {}, {fid: {} for fid in fids}

    def give_all(mid, **blank):
        for fid in fids:
            results[fid][mid] = blank_result(**blank)

    wanted_notes = measure.wanted_shown()
    for mid, metric in metrics.items():
        if mid in wanted_notes:
            give_all(mid, status="Wanted", reason=wanted_notes[mid])
            continue
        if mid in measure.SWITCHABLE and mid not in (cfg.get("switched_on") or []):
            give_all(mid, status="DNR", reason="Not switched on yet: counted from its files, but not scored "
                                              "(setting switched_on in config/thresholds.json)")
            continue
        if mid not in meas["received"]:
            give_all(mid, status="DNR", reason=f"No data: {metric['provider']}’s {MONTHS[int(month[5:]) - 1]} data was not received")
            continue
        # Data contract (owner, 4 Nov 2026): once a feed's contract is approved, TRUST may use the file only for the
        # metrics the contract lists. Anything else waits for a new contract version the provider approves.
        blocked = contract_blocks(mid)
        if blocked:
            give_all(mid, status="DNR", reason=blocked)
            continue
        if mid in measure.PER_10_APPS:
            threshold, metric_results = _incident_rate_results(mid, metric, fcounts[mid], fids, cfg, month)
        else:
            threshold, metric_results = _percent_results(mid, metric, fcounts[mid], fids, not_tier01, cfg, month)
        if threshold:
            thresholds[mid] = threshold
        for fid in fids:
            results[fid][mid] = metric_results[fid]

    for fid in not_tier01:
        family = next(f for f in families if f["id"] == fid)
        why = (f"Not Tier 0/1: no Tier 0 or 1 applications in the ITDR application file "
               f"({plural(family['apps_total'], 'application', 'applications')} placed with this L3 team). "
               "Not scored on Resiliency")
        for mid in metrics:
            if mid.startswith("RE-"):
                kept = {k: results[fid][mid].get(k) for k in ("value", "numerator", "denominator")}
                results[fid][mid] = blank_result("Not Tier 0/1", why, **kept)

    # Actions on incidents with no rating are shown, never hidden, and kept out of the score (owner, 2 Nov 2026).
    if "UN-02" in meas["received"]:
        for fid in fids:
            counts = fcounts["UN-02"].get(fid) or {}
            unrated_open, unrated_overdue = counts.get("unrated_open", 0), counts.get("unrated_overdue", 0)
            if unrated_open:
                result = results[fid]["UN-02"]
                result["reason"] = (f"{result['reason']}. Not in the score: {plural(unrated_open, 'open action', 'open actions')} "
                                    f"({unrated_overdue} overdue) on incidents with no rating (DEFCON Not Available or blank)")
                result.update(unrated_open=unrated_open, unrated_overdue=unrated_overdue)
    return thresholds, results


def _count_unplaced(unplaced_by_provider, unplaced_by_feed, metric, unplaced_count, total):
    """Add one metric's rows with no family, out of all its rows, to its provider's and its file's not-yet-mapped share."""
    provider_counts = unplaced_by_provider.setdefault(metric["provider"], [0, 0])
    provider_counts[0] += unplaced_count
    provider_counts[1] += total
    feed = measure.needs().get(metric["id"])
    if feed:
        feed_counts = unplaced_by_feed.setdefault(feed, [0, 0])
        feed_counts[0] += unplaced_count
        feed_counts[1] += total


def _firm_incident_status(mid, rate, incidents, thresholds, metric):
    """The firm's status for the incident rate: not scored without a rate or a threshold; no incident is Low confidence."""
    if rate is None:
        return "N/A"
    if not incidents:
        return "Low confidence"
    if mid not in thresholds:
        return "N/A"
    return status_of(rate, thresholds[mid], metric["higher_is_better"], metric["unit"])[0]


def _firm_roll_up(metrics, meas, cfg, thresholds, results, fids):
    """Step 3: firm-wide results, where every row counts, placed or not.
    Returns (firm_totals, firm results, unplaced share per provider, unplaced share per file)."""
    firm_totals, firm, unplaced, unplaced_feed = {}, {}, {}, {}
    wanted_notes = measure.wanted_shown()
    for mid, metric in metrics.items():
        if mid in wanted_notes:
            firm_totals[mid] = None
            firm[mid] = dict(value=None, status="Wanted", prior_value=None, prior_status=None)
            continue
        if mid not in meas["received"] or (mid in measure.SWITCHABLE and mid not in (cfg.get("switched_on") or [])):
            firm_totals[mid] = None
            firm[mid] = dict(value=None, status="DNR", prior_value=None, prior_status=None)
            continue
        counts = meas["counts"][mid]
        if mid in measure.PER_10_APPS:
            incidents, apps = counts["_firm"]["numerator"], counts["_firm"].get("apps", 0)
            rate = incidents_per_10_apps(incidents, apps) if apps else None
            firm_totals[mid] = rate
            firm[mid] = dict(value=rate, status=_firm_incident_status(mid, rate, incidents, thresholds, metric),
                             prior_value=None, prior_status=None, numerator=incidents, denominator=apps)
            _count_unplaced(unplaced, unplaced_feed, metric, counts.get(UNATTRIBUTED, {}).get("numerator", 0), incidents)
            continue
        numerator = sum(c["numerator"] for c in counts.values())
        denominator = sum(c["denominator"] for c in counts.values())
        value = percent(numerator, denominator) if denominator else None
        firm_totals[mid] = value
        status = "N/A"
        if value is not None and mid in thresholds:
            status = status_of(value, thresholds[mid], metric["higher_is_better"], metric["unit"])[0]
        firm[mid] = dict(value=value, status=status, prior_value=None, prior_status=None,
                         numerator=numerator, denominator=denominator)
        _count_unplaced(unplaced, unplaced_feed, metric, counts.get(UNATTRIBUTED, {}).get("denominator", 0), denominator)
        if status == "N/A" and value is not None:
            firm[mid]["reason"] = ("No tolerance threshold this month: no L3 team had enough results to set a prevailing "
                                   "median, so the firm result is shown but not scored")

    # An automatic Red rule that fired for any family (e.g. TE-02 client impact) holds for the firm too (owner, 4 Nov 2026).
    for mid in firm:
        if any(results[fid].get(mid, {}).get("override") and results[fid][mid]["status"] == "Red" for fid in fids):
            firm[mid].update(status="Red", override=True,
                             reason="Red by an automatic Red rule that applied to at least one L3 team")
    return firm_totals, firm, unplaced, unplaced_feed


def _files_needed(feeds, metrics, dictionary):
    """One definition of "files received" for every page (owner, 5 Nov 2026): the files the measured metrics
    need this month, plus HR and the owners file that place every row. Other feeds are optional."""
    is_measured = {mid for mid in metrics if not dictionary.get(mid, {}).get("not_measured")}
    wanted_notes = measure.wanted_shown()
    first_files = {file for mid, file in measure.needs().items() if mid in is_measured and mid not in wanted_notes}
    second_files = {file for mid, file in measure.needs_also().items() if mid in is_measured}
    needed = ["hr", "hr_mapping"] + sorted(first_files | second_files)
    got = {f for f, v in feeds.items() if v.get("status") not in (None, "not received")}
    return {"needed": needed, "received": [f for f in needed if f in got],
            "missing": [f for f in needed if f not in got], "optional_received": sorted(f for f in got if f not in needed)}


def _submissions(feeds, month, unplaced_feed):
    """One entry per file the page lists on Data sources: who sent it, its warnings and its share not yet mapped."""
    submissions = []
    needs_by_metric = measure.needs()
    for feed, v in feeds.items():
        if v.get("status") in (None, "not received") or feed not in FEED_PROVIDER:
            continue
        unplaced = unplaced_feed.get(feed)
        submissions.append(dict(
            id=f"{month}-{feed}", feed=feed, provider=FEED_PROVIDER[feed], status="Accepted" if v["status"] == "mapped" else v["status"],
            as_of=v.get("as_of") or v.get("uploaded_at"),
            data_as_of=data_as_of(own_date_of(v), v.get("uploaded_at"), month), rows=len(v.get("rows") or v.get("people") or []),
            # this file's own share of rows not yet mapped to a family (None when no metric reads this file)
            unattributed_pct=percent(unplaced[0], unplaced[1]) if unplaced and unplaced[1] else None,
            # the front end reads each warning as {rule, detail} and keys acknowledgements by rule, so number them
            warnings=[dict(rule=f"Mapping note {i}", detail=str(n)) for i, n in enumerate(v.get("notes", []), 1)],
            metrics=[mid for mid, f in needs_by_metric.items() if f == feed]))
    return submissions


def _incident_notes(meas):
    """Plain notes about incidents UN-01 could not count."""
    firm_incidents = meas["counts"].get("UN-01", {}).get("_firm", {})
    notes = []
    if firm_incidents.get("no_end_date"):
        without_date = firm_incidents["no_end_date"]
        notes.append(f"{plural(len(without_date), 'incident has', 'incidents have')} no end_datetime, so "
                     f"UN-01 can't place them in a month: {', '.join(without_date[:INCIDENTS_LISTED])}")
    if firm_incidents.get("not_critical_or_swe"):
        not_counted = firm_incidents["not_critical_or_swe"]
        notes.append(f"{plural(len(not_counted), 'incident is', 'incidents are')} neither Critical nor SWE (DEFCON Not Available "
                     f"or blank), so not counted in UN-01: {', '.join(not_counted[:INCIDENTS_LISTED])}")
    return notes


def score_month(mapped, cfg=None, tpl=None):
    """Score one mapped month. Returns the period block the front end reads, plus the family list."""
    cfg = cfg or thresholds_config()
    tpl = tpl or template()
    month = mapped["month"]
    feeds = mapped["feeds"]
    meas = measure.measure(mapped)
    metrics = {m["id"]: m for m in tpl["metrics"]}
    # Per-family counts, with a shared lead's group added to each of their families; the firm uses meas["counts"].
    fcounts = expand_shared(meas["counts"], (feeds.get("hr_mapping") or {}).get("shared") or {})
    families = _families_in(feeds)
    fids = [f["id"] for f in families]

    # 1. Values per family, and the thresholds they are judged against.
    thresholds, results = _family_results(metrics, meas, fcounts, cfg, month, families)
    flag_behind_peers(results, tpl, thresholds, rule_is_on(cfg, "behind_peers_flag"))

    # 2. Building blocks and TRUST per family (scoring.py: points, caps, rounding).
    fam_out = {fid: _scored(results[fid], tpl, cfg) for fid in fids}
    trusts = [fam_out[fid]["trust"] for fid in fids]

    # 3. Firm-wide: every row counts, placed or not. Firm TRUST is scored from the pooled firm-wide results, the same
    # way as a family (owner, 4 Nov 2026), not as the average of the family scores. The average is kept beside it.
    firm_totals, firm, unplaced, unplaced_feed = _firm_roll_up(metrics, meas, cfg, thresholds, results, fids)
    firm_scored = _scored(firm, tpl, cfg)

    received_providers = {metrics[mid]["provider"] for mid in meas["received"]}
    wanted_notes = measure.wanted_shown()
    dnr = sorted({m["provider"] for k, m in metrics.items() if k not in wanted_notes} - received_providers)
    # "Data missing" (which hides the firm's change arrows and trend) means a provider with a measured metric
    # didn't send. A provider whose metrics are all still wanted, with no source yet, isn't missing data
    # (5 Nov 2026, from review: wanted metrics kept the firm change hidden every month).
    dictionary = (tpl.get("dictionary") or {}).get("metrics") or {}
    expected = {m["provider"] for k, m in metrics.items()
                if k not in wanted_notes and not dictionary.get(k, {}).get("not_measured")}
    firm_incomplete = bool(expected - received_providers)

    period = dict(
        meta=dict(id=month, label=label(month), current_bd=None,
                  last_day=(measure.month_end(month) - timedelta(days=1)).date().isoformat()),
        thresholds=thresholds, families=fam_out, firm_trust=firm_scored["trust"], firm_status=firm_scored["status"],
        firm_capped=firm_scored["capped"], firm_blocks=firm_scored["blocks"], firm_blocks_scored=firm_scored["blocks_scored"],
        firm_trust_average=scoring.average_trust(trusts), firm_trust_delta=None,
        firm_totals=firm_totals, firm=firm, watch_list=[], most_improved=None, dnr=dnr,
        unattributed_pct={p: percent(unplaced_count, total) for p, (unplaced_count, total) in unplaced.items() if total},
        submissions=_submissions(feeds, month, unplaced_feed), firm_incomplete=firm_incomplete,
        files_needed=_files_needed(feeds, metrics, dictionary))
    period["large_share"] = large_share(period, cfg)          # a note on the firm figure, never a score (a setting)
    period["caps"] = scoring.caps_from(cfg.get("caps"))       # the caps this month was scored with (a setting)
    period["coverage"] = scoring.coverage_from(cfg.get("coverage"), scoring.block_codes(tpl["metrics"]))   # and how much had to be measured (a setting)
    notes = _incident_notes(meas)
    if notes:
        period["notes"] = notes
    # The items behind each family's numbers, for the drill-down and the family download.
    items = {}
    for mid, by_fam in fcounts.items():
        for fid, c in by_fam.items():
            if fid.startswith("_") or not isinstance(c, dict) or not c.get("items"):
                continue
            items.setdefault(fid, {})[mid] = c["items"]
    return dict(period=period, families=families, items=items)


def run(month, by="command line"):
    """Map is assumed done for the month. Saves the scored month (database or store/scored/)."""
    mapped = storage.load_month("mapped", month)
    if mapped is None:
        raise ValueError(f"{month} hasn't been mapped yet: run  python manage.py map {month}")
    out = score_month(mapped)
    out["based_on_mapped_sha256"] = storage.doc_sha256(mapped)     # shows which mapping this score was worked out from
    storage.save_month("scored", month, out, by)
    ft = out["period"]["firm_trust"]
    storage.log("score", by, month, f"firm TRUST {ft if ft is not None else 'not scored'}")
    return out
