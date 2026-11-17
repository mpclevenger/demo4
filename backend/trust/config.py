"""Owner-editable settings (config/settings.json, or the file named by TRUST_SETTINGS), and the metric
definitions (config/metrics.json, or the file named by TRUST_METRICS).

Keys starting with _ are notes for people and are ignored. Also holds `ROOT` (the repo folder) and
`config_file`, the one way every part of TRUST finds a file in config/.
"""
import json
import os
import pathlib
import re

from .intake.common import loads_tolerant

ROOT = pathlib.Path(__file__).resolve().parents[2]       # the repo folder


def config_file(variable, file_name):
    """The path of a file in config/: the one the environment variable `variable` names, else config/<file_name>."""
    return pathlib.Path(os.environ.get(variable) or ROOT / "config" / file_name)


def settings():
    path = config_file("TRUST_SETTINGS", "settings.json")
    try:
        doc = loads_tolerant(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        doc = {}
    out = {k: v for k, v in doc.items() if not k.startswith("_")}
    # A config var can stand in for the CTO's SAM_ACCOUNT (owner, 4 Nov 2026): the TEST environment sets
    # TRUST_HR_ROOT_SAM_ACCOUNT to the seed data's made-up CTO without editing the file.
    if os.environ.get("TRUST_HR_ROOT_SAM_ACCOUNT", "").strip():
        out["hr_root_sam_account"] = os.environ["TRUST_HR_ROOT_SAM_ACCOUNT"].strip()
    return out


def metrics_path():
    return config_file("TRUST_METRICS", "metrics.json")


_METRICS_READ = {}    # (path, modified time, size) -> the parsed metrics: read once, again only when the file changes


def metrics():
    """Every metric's definition (config/metrics.json, owner 8 Nov 2026): name, wording, dictionary card, known
    limits and how it is counted, in display order. Keys starting with _ are notes and are ignored.
    The file is read once and kept until it changes (it was read thousands of times per page; 17 Nov 2026).
    Callers get their own copy, so changing what they get never changes the kept one."""
    return json.loads(_metrics_read()[0])


def _metrics_read():
    """(text, parsed) of the metrics, kept until config/metrics.json changes. The parsed one is shared: read only."""
    path = metrics_path()
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key not in _METRICS_READ:
        doc = loads_tolerant(path.read_text(encoding="utf-8")) or {}
        kept = {k: v for k, v in (doc.get("metrics") or {}).items() if not k.startswith("_")}
        _METRICS_READ.clear()
        _METRICS_READ[key] = (json.dumps(kept), kept)
    return _METRICS_READ[key]


def counting_all():
    """{metric id: how it is counted}, from the kept metrics (read only; used for every item, so no copying)."""
    return {mid: x["counting"] for mid, x in _metrics_read()[1].items() if x.get("counting")}


def counting(mid):
    """The 'counting' part of one metric's definition ({} for a metric that isn't measured yet)."""
    return dict(_metrics_read()[1].get(mid, {}).get("counting") or {})


def risks_dir():
    return config_file("TRUST_RISKS", "risks")


RISK_FIELDS = ("domain", "category", "name", "description")


def _is_risk(d):
    return isinstance(d, dict) and any(k in d for k in RISK_FIELDS)


DRIVER_LIST_FIELDS = ("likelihood_drivers", "impact_drivers")
DRIVER_ID_KEYS = ("id", "code", "driver", "driver_id", "rd")   # names a driver block may give its code under
DRIVER_CODE = re.compile(r"^RD\d+$", re.IGNORECASE)


def driver_code(item):
    """One entry of a risk's driver list as its code (RD01), or None when it can't be read. Engine files write the
    list as plain codes ([RD01, RD36]); some write a block per driver (- id: RD01 ..., or - RD01: {...})."""
    if isinstance(item, str):
        return item.strip().upper()                       # rd01 and RD01 are the same driver; the rules write RD01
    if isinstance(item, dict):
        for key in DRIVER_ID_KEYS:
            if isinstance(item.get(key), str):
                return item[key].strip().upper()
        codes = [key for key in item if isinstance(key, str) and DRIVER_CODE.match(key.strip())]
        if len(codes) == 1:
            return codes[0].strip().upper()
    return None


def tidy_driver_lists(risk_id, risk):
    """The risk with its likelihood and impact drivers as plain lists of codes, plus plain sentences for anything
    that couldn't be read (shown by the upload check; the risk is still loaded with the codes that could)."""
    tidy, problems = dict(risk), []
    for field in DRIVER_LIST_FIELDS:
        value = risk.get(field)
        if value is None:
            continue
        entries = list(value.items()) if isinstance(value, dict) else value
        if isinstance(value, dict):                       # a map keyed by code: {RD01: {...}, RD36: {...}}
            entries = [code for code, _details in entries]
        if not isinstance(entries, list):
            problems.append(f"In {risk_id}, {field} isn't a list of driver codes (found {str(value)[:80]!r}).")
            tidy[field] = []
            continue
        codes = []
        for item in entries:
            code = driver_code(item)
            if code:
                codes.append(code)
            else:
                problems.append(f"In {risk_id}, one entry in {field} isn't a driver code (found {str(item)[:80]!r}).")
        tidy[field] = codes
    return tidy, problems


def risks_in_file(stem, doc):
    """(risk id, risk) pairs in one file. A domain file (e.g. air.cyber.yaml) holds several risks (owner, 9 Nov
    2026), keyed by ID (air.cyber.01: {...}, or 01: {...} -> air.cyber.01), as a list (each with an id, else
    numbered air.cyber.01, .02 in order), or under a "risks" key; a file holding one risk is keyed by its own id,
    else by the file name."""
    if isinstance(doc, dict) and "risks" in doc and not _is_risk(doc):
        doc = doc["risks"]
    if _is_risk(doc):
        yield str(doc.get("id") or stem), doc
    elif isinstance(doc, dict):
        for k, v in doc.items():
            if _is_risk(v):
                k = str(v.get("id") or k)
                yield (k if k.startswith(stem + ".") or "." in k else f"{stem}.{k}"), v
    elif isinstance(doc, list):
        for i, v in enumerate(doc, start=1):
            if _is_risk(v):
                yield str(v.get("id") or f"{stem}.{i:02d}"), v


def risks():
    """The risk assessment engine's risks (owner, 9 Nov 2026): copies of its risk files in config/risks/ (one file
    per domain, e.g. air.cyber.yaml, with several risks inside), keyed by risk ID (air.cyber.01). Metrics link to
    them by ID in card.risks (config/metrics.json)."""
    import yaml                                          # pyyaml; only needed here
    out = {}
    folder = risks_dir()
    files = sorted(folder.glob("*.yaml")) + sorted(folder.glob("*.yml")) if folder.exists() else []
    for f in files:
        for doc in yaml.safe_load_all(f.read_text(encoding="utf-8")):
            for rid, r in risks_in_file(f.stem, doc):
                out[rid], _problems = tidy_driver_lists(rid, r)
    return out


def data_sources():
    """Facts about each data source TRUST receives (config/data_sources.json, owner 9 Nov 2026): who owns it.
    Keyed by feed id; keys starting with _ are notes."""
    path = config_file("TRUST_DATA_SOURCES", "data_sources.json")
    doc = {}
    if path.exists():
        doc = loads_tolerant(path.read_text(encoding="utf-8")) or {}
    return {k: {f: v for f, v in (x or {}).items() if not f.startswith("_")}
            for k, x in (doc.get("sources") or {}).items() if not k.startswith("_")}
