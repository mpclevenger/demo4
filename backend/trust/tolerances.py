"""Tolerance thresholds and caps changed on the site (owner, 15 Nov 2026).

config/thresholds.json holds the starting values. Tech Risk changes them on the Scoring settings page;
each change is a row in the setting_change table (the audit trail, never edited), and the newest row for a
setting is the value in use. A change applies when a month is next updated; locked months keep their figures.

Before a change is saved the page shows every score it would move: each open month is scored twice, with
the values in use and with the proposed ones, and the differences are listed (`preview`).
"""
import copy
import statistics

from . import config, storage
from .numbers import r1

BASES = ("Policy", "Prevailing median")
POLICY_PARTS = ("basis", "green", "red", "set_from")      # a change to any of these re-dates the threshold

# The settings that aren't per metric: path -> (label, group, kind, lowest, highest).
# kind: whole (a whole number), number, blank_or_number (may be left empty), onoff.
GENERAL = {
    "caps.automatic_red_block": ("Building block cap when an automatic Red rule applies", "Caps", "whole", 0, 100),
    "caps.red_metric_block": ("Building block cap with any Red metric", "Caps", "whole", 0, 100),
    "caps.red_block_trust": ("TRUST cap with any Red building block", "Caps", "whole", 0, 100),
    "automatic_red_rules": ("Automatic Red rules", "Rules", "onoff", None, None),
    "behind_peers_flag": ("Behind peers flag on the watch list", "Rules", "onoff", None, None),
    "min_families_for_threshold": ("Families needed for a prevailing median", "Prevailing median", "whole", 1, 50),
    "amber_band_min_points": ("Smallest Amber band", "Prevailing median", "number", 0, 100),
    "amber_band_spread_multiple": ("Amber band, as a multiple of the usual spread between families",
                                   "Prevailing median", "number", 0, 10),
    "coverage.block_min_share": ("Share of a building block's metrics that must be scored (0 = any one)",
                                 "Coverage", "number", 0, 1),
    "coverage.trust_min_blocks": ("Building blocks needed for a TRUST score", "Coverage", "whole", 1, 10),
    "firm_tolerance": ("Firm tolerance for TRUST (empty = not shown)", "Firm", "blank_or_number", 0, 100),
    "large_share_flag_default": ("Note on the firm figure when one family holds more than this share of the items, % "
                                 "(empty = no note)", "Firm", "blank_or_number", 1, 100),
}
METRIC_PARTS = ("basis", "green", "red", "amber_band_min")
NEAR_TOP_PERCENT = 98                   # a middle family at or above this is nearly at the top (where higher is better) ...
NEAR_BOTTOM_PERCENT = 2                 # ... or at or below this (where lower is better)
LARGEST_SETTING_VALUE = 1_000_000      # the biggest number a count or limit setting may be given


def switchable():
    from . import measure
    return measure.SWITCHABLE


def _get(doc, path):
    if path.startswith("switched_on."):                 # one metric's on/off, kept as a list of the ones that are on
        return path.split(".", 1)[1] in (doc.get("switched_on") or [])
    cur = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _set(doc, path, value):
    if path.startswith("switched_on."):
        mid, on = path.split(".", 1)[1], [m for m in doc.get("switched_on") or []]
        doc["switched_on"] = [m for m in on if m != mid] + ([mid] if value else [])
        return
    parts = path.split(".")
    cur = doc
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    if value is None:
        cur.pop(parts[-1], None)
    else:
        cur[parts[-1]] = value


def _same(a, b):
    num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)
    return float(a) == float(b) if num(a) and num(b) else a == b


def effective(doc, extra=None):
    """The thresholds document with every change made on the site in place, then any proposed ones (extra)."""
    out = copy.deepcopy(doc)
    dated = {}
    for c in storage.setting_changes():
        _set(out, c["path"], c["after"])
        parts = c["path"].split(".")
        if parts[0] == "metrics" and len(parts) == 3 and parts[2] in POLICY_PARTS:
            dated[parts[1]] = (c["by"], c["at"][:10])
    for mid, (by, on) in dated.items():           # the card says who set a fixed threshold, and when
        if mid in out.get("metrics", {}):
            out["metrics"][mid].update(set_by=by, set_on=on)
    for path, value in (extra or {}).items():
        _set(out, path, value)
    return out


def current():
    from . import score_month
    return score_month.thresholds_config()


def fields(cfg=None):
    """Every setting the page can change, with its value in use: general settings, then one row per metric."""
    cfg = cfg or current()
    general = [{"path": p, "label": label, "group": group, "kind": kind, "min": lo, "max": hi, "value": _get(cfg, p)}
               for p, (label, group, kind, lo, hi) in GENERAL.items()]
    defs = config.metrics()
    metrics = [{"id": mid, "name": (defs.get(mid) or {}).get("name") or mid, "unit": (defs.get(mid) or {}).get("unit"),
                "higher_is_better": bool((defs.get(mid) or {}).get("higher_is_better", True)),
                "status": (defs.get(mid) or {}).get("status"),
                "basis": "Policy" if mc.get("basis") == "Policy" else "Prevailing median",
                "green": mc.get("green"), "red": mc.get("red"), "amber_band_min": mc.get("amber_band_min"),
                "min_items": (cfg.get("low_confidence_below_items") or {}).get(mid),
                "large_share": (cfg.get("large_share_flag_percent") or {}).get(mid),
                "switchable": mid in switchable(), "switched_on": _get(cfg, f"switched_on.{mid}"),
                "set_by": mc.get("set_by"), "set_on": mc.get("set_on")}
               for mid, mc in (cfg.get("metrics") or {}).items()]
    values = {g["path"]: g["value"] for g in general}
    for m in metrics:
        values.update({f"metrics.{m['id']}.{k}": m[k] for k in METRIC_PARTS})
        values[f"low_confidence_below_items.{m['id']}"] = m["min_items"]
        values[f"large_share_flag_percent.{m['id']}"] = m["large_share"]
        if m["switchable"]:
            values[f"switched_on.{m['id']}"] = m["switched_on"]
    return {"general": general, "metrics": metrics, "values": values}


def _number(value, label, whole=False, lo=None, hi=None, blank_ok=False):
    if value in (None, "") and blank_ok:
        return None
    try:
        if isinstance(value, bool):
            raise ValueError
        n = float(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{label}: give a number.") from None
    if n != n or n in (float("inf"), float("-inf")):
        raise ValueError(f"{label}: give a number.")
    if whole and n != int(n):
        raise ValueError(f"{label}: give a whole number.")
    if (lo is not None and n < lo) or (hi is not None and n > hi):
        raise ValueError(f"{label}: give a number from {lo:g} to {hi:g}.")
    return int(n) if whole or n == int(n) else n


def _onoff(value, label):
    v = str(value).strip().lower() if not isinstance(value, bool) else value
    if v in (True, "true", "on"):
        return True
    if v in (False, "false", "off"):
        return False
    raise ValueError(f"{label}: choose On or Off.")


def check(changes, cfg=None):
    """The proposed changes, tidied, with only the ones that differ from the values in use: {path: value}.
    Raises ValueError with a plain reason when a value can't be used or the result wouldn't make sense."""
    cfg = cfg or current()
    if not isinstance(changes, dict):
        raise ValueError("Nothing to change.")
    defs, clean = config.metrics(), {}
    for path, value in changes.items():
        parts = str(path).split(".")
        if path in GENERAL:
            label, _, kind, lo, hi = GENERAL[path]
            value = _onoff(value, label) if kind == "onoff" else \
                _number(value, label, kind == "whole", lo, hi, blank_ok=kind == "blank_or_number")
        elif parts[0] == "switched_on" and len(parts) == 2 and parts[1] in switchable():
            value = _onoff(value, (defs.get(parts[1]) or {}).get("name") or parts[1])
        elif parts[0] == "low_confidence_below_items" and len(parts) == 2 and parts[1] in (cfg.get("metrics") or {}):
            value = _number(value, f"{(defs.get(parts[1]) or {}).get('name') or parts[1]}, fewest items to score",
                            whole=True, lo=0, hi=LARGEST_SETTING_VALUE, blank_ok=True)
        elif parts[0] == "large_share_flag_percent" and len(parts) == 2 and parts[1] in (cfg.get("metrics") or {}):
            value = _number(value, f"{(defs.get(parts[1]) or {}).get('name') or parts[1]}, largest share for one family",
                            whole=False, lo=1, hi=100, blank_ok=True)
        elif parts[0] == "metrics" and len(parts) == 3 and parts[1] in (cfg.get("metrics") or {}) \
                and parts[2] in METRIC_PARTS:
            name = (defs.get(parts[1]) or {}).get("name") or parts[1]
            if parts[2] == "basis":
                if value not in BASES:
                    raise ValueError(f"{name}: the basis is Policy (fixed) or Prevailing median.")
            else:
                label = {"green": "Green tolerance", "red": "Red limit", "amber_band_min": "Smallest Amber band"}[parts[2]]
                value = _number(value, f"{name}, {label}", lo=0, hi=LARGEST_SETTING_VALUE, blank_ok=True)
        else:
            raise ValueError(f"'{path}' isn't a setting this page can change.")
        if not _same(_get(cfg, path), value):
            clean[path] = value
    after = _apply(cfg, clean)
    for mid, mc in (after.get("metrics") or {}).items():
        if not any(p.startswith(f"metrics.{mid}.") for p in clean) or mc.get("basis") != "Policy":
            continue
        d = defs.get(mid) or {}
        name, g, r = d.get("name") or mid, mc.get("green"), mc.get("red")
        if g is None or r is None:
            raise ValueError(f"{name}: a fixed tolerance threshold needs both a Green tolerance and a Red limit.")
        if d.get("unit") == "%" and not (0 <= g <= 100 and 0 <= r <= 100):
            raise ValueError(f"{name}: a percentage is from 0 to 100.")
        hib = bool(d.get("higher_is_better", True))
        if (hib and not g > r) or (not hib and not g < r):
            raise ValueError(f"{name}: the Green tolerance must be {'higher' if hib else 'lower'} than the Red limit "
                             f"({'higher' if hib else 'lower'} is better for this metric).")
    return clean


def _apply(cfg, changes):
    out = copy.deepcopy(cfg)
    for path, value in changes.items():
        _set(out, path, value)
    return out


def _label(path):
    if path in GENERAL:
        return GENERAL[path][0]
    if path.startswith(("switched_on.", "low_confidence_below_items.", "large_share_flag_percent.")):
        mid = path.split(".", 1)[1]
        return f"{(config.metrics().get(mid) or {}).get('name') or mid}: " + (
            "scored" if path.startswith("switched_on.") else "largest share for one family"
            if path.startswith("large_share_flag_percent.") else "fewest items to score")
    _, mid, part = path.split(".")
    name = (config.metrics().get(mid) or {}).get("name") or mid
    return f"{name}: " + {"basis": "basis", "green": "Green tolerance", "red": "Red limit",
                          "amber_band_min": "smallest Amber band", "set_from": "set from"}.get(part, part)


def _moves(before, after, tpl):
    """What differs between two scorings of the same month: [(who, what, before, after)]."""
    names = {m["id"]: m.get("name") or m["id"] for m in tpl["metrics"]}
    blocks = {b["code"]: b["name"] for b in tpl["blocks"]}
    fam = {f["id"]: f["name"] for f in after["families"]}
    show = lambda v: "Not scored" if v is None else str(v)
    out = []

    def compare(who, b, a):
        for mid in names:
            sb, sa = (b["metrics"].get(mid) or {}).get("status"), (a["metrics"].get(mid) or {}).get("status")
            if sb != sa:
                out.append((who, names[mid], show(sb), show(sa)))
        for code, name in blocks.items():
            vb, va = (b["blocks"].get(code) or {}).get("score"), (a["blocks"].get(code) or {}).get("score")
            if vb != va:
                out.append((who, name, show(vb), show(va)))
        if b["trust"] != a["trust"]:
            out.append((who, "TRUST", show(b["trust"]), show(a["trust"])))

    pb, pa = before["period"], after["period"]
    compare("Firm", {"metrics": pb.get("firm") or {}, "blocks": pb.get("firm_blocks") or {}, "trust": pb.get("firm_trust")},
            {"metrics": pa.get("firm") or {}, "blocks": pa.get("firm_blocks") or {}, "trust": pa.get("firm_trust")})
    for fid in pa["families"]:
        if fid in pb["families"]:
            compare(fam.get(fid, fid), pb["families"][fid], pa["families"][fid])
    return [{"who": w, "what": x, "before": b, "after": a} for w, x, b, a in out]


def preview(changes):
    """What saving these changes would do: the changes themselves, and every score that would move in each open
    month that has been updated. Locked months are listed, and never move."""
    from . import score_month
    cfg = current()
    clean = check(changes, cfg)
    proposed = _apply(cfg, clean)
    tpl = score_month.template()
    months, locked = [], []
    for month in sorted(storage.months("mapped"), reverse=True):
        if storage.month_status(month)["status"] == "locked":
            locked.append(score_month.label(month))
            continue
        mapped = storage.load_month("mapped", month)
        if not clean or mapped is None:
            continue
        months.append({"month": month, "label": score_month.label(month),
                       "moves": _moves(score_month.score_month(mapped, cfg, tpl),
                                       score_month.score_month(mapped, proposed, tpl), tpl)})
    return {"changes": [{"path": p, "label": _label(p), "before": _get(cfg, p), "after": v} for p, v in clean.items()],
            "months": months, "locked": locked}


def compare(month):
    """For one updated month: how each measured metric is judged by the prevailing median, and by its fixed
    tolerance threshold when it has one, side by side (owner, 15 Nov 2026: so the two can be compared before a
    threshold is set). Nothing is saved or changed. Returns {"month", "label", "metrics": [...]} or None when
    the month hasn't been updated."""
    from . import score_month
    mapped = storage.load_month("mapped", month)
    if mapped is None:
        return None
    cfg, tpl = current(), score_month.template()
    median_cfg = copy.deepcopy(cfg)
    for mc in median_cfg.get("metrics", {}).values():
        mc["basis"] = "Prevailing median"
    as_now = score_month.score_month(mapped, cfg, tpl)["period"]
    by_median = score_month.score_month(mapped, median_cfg, tpl)["period"]
    defs = {m["id"]: m for m in tpl["metrics"]}

    def judged(period, mid):
        t = (period.get("thresholds") or {}).get(mid) or {}
        counts = {"Green": 0, "Amber": 0, "Red": 0}
        for fr in period["families"].values():
            st = (fr["metrics"].get(mid) or {}).get("status")
            if st in counts:
                counts[st] += 1
        return {"green": t.get("green"), "red": t.get("red"), "counts": counts, "scored": sum(counts.values())}

    out = []
    for mid, mc in (cfg.get("metrics") or {}).items():
        d = defs.get(mid) or {}
        values = sorted(v for v in ((fr["metrics"].get(mid) or {}).get("value") for fr in as_now["families"].values())
                        if isinstance(v, (int, float)) and not isinstance(v, bool))
        if not values:
            continue                                   # nothing measured for this metric this month: nothing to compare
        higher_is_better = bool(d.get("higher_is_better", True))
        middle = statistics.median(values)
        fixed = mc.get("basis") == "Policy"
        fewest_items = (cfg.get("low_confidence_below_items") or {}).get(mid) or 0
        item_counts = sorted(n for n in ((fr["metrics"].get(mid) or {}).get("denominator") for fr in as_now["families"].values())
                             if isinstance(n, (int, float)) and not isinstance(n, bool) and n > 0)
        # nearly every family at the top: the middle family leaves almost no room below it
        nearly_all_at_top = d.get("unit") == "%" and (middle >= NEAR_TOP_PERCENT if higher_is_better
                                                      else middle <= NEAR_BOTTOM_PERCENT)
        row = {"id": mid, "name": d.get("name") or mid, "unit": d.get("unit"), "higher_is_better": higher_is_better,
               "basis": "Policy" if fixed else "Prevailing median", "families": len(values)}
        # r1 (half up), the same rounding as the real thresholds (owner, 16 Nov 2026)
        row.update({"lowest": values[0], "middle": r1(middle), "highest": values[-1]})
        row.update({"min_items": fewest_items, "too_few": sum(1 for n in item_counts if n < fewest_items),
                    "smallest_count": item_counts[0] if item_counts else None,
                    "largest_count": item_counts[-1] if item_counts else None,
                    "large_share": (as_now.get("large_share") or {}).get(mid)})
        row.update({"by_median": judged(by_median, mid), "by_fixed": judged(as_now, mid) if fixed else None,
                    "near_top": nearly_all_at_top})
        out.append(row)
    return {"month": month, "label": score_month.label(month), "metrics": out}


def save(changes, by, reason):
    """Check and record the changes. Returns what was recorded (nothing when no value differs)."""
    reason = " ".join(str(reason or "").split())
    cfg = current()
    clean = check(changes, cfg)
    if not clean:
        return []
    if not reason:
        raise ValueError("Say why, so the record shows the reason for the change.")
    if len(reason) > 1000:
        raise ValueError("That reason is too long (1,000 characters at most).")
    rows = [(p, _get(cfg, p), v) for p, v in clean.items()]
    # a threshold set by hand is no longer "set from" a calibration run
    for mid in {p.split(".")[1] for p in clean if p.startswith("metrics.")}:
        if _get(cfg, f"metrics.{mid}.set_from") and any(f"metrics.{mid}.{k}" in clean for k in ("basis", "green", "red")):
            rows.append((f"metrics.{mid}.set_from", _get(cfg, f"metrics.{mid}.set_from"), None))
    storage.add_setting_changes(rows, by, reason)
    return [{"path": p, "label": _label(p), "before": b, "after": a} for p, b, a in rows]


def history():
    """The audit trail, newest first, with a plain label for each setting."""
    return [dict(c, label=_label(c["path"])) for c in reversed(storage.setting_changes())]
