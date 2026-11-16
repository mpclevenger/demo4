"""Reads the engine's drivers file (driver_mapping.yaml) for the first load.

The risks themselves are read by trust.config.risks(), which already reads the engine's risk files.
"""
import pathlib

import yaml

from trust.risk import drivers, expressions, rating

DRIVERS_FILE = "driver_mapping.yaml"
IMPACT_LEVELS_IN_FILES = tuple(level.lower() for level in rating.LEVELS)


def driver_rules(folder):
    """Every driver in the folder's driver_mapping.yaml, with its rule:

        {"RD12": {"field": "RD12", "test": "at least", "value": 3.0,
                  "rationale": "...", "questionnaire_fields": ["RD12"]}, ...}

    A driver with no questionnaire field is answered from data.
    """
    path = pathlib.Path(folder) / DRIVERS_FILE
    saved = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    result = {}
    for code, details in (saved.get("risk_drivers") or {}).items():
        rule = drivers.rule_from_trigger(details["trigger"])
        rule["rationale"] = details.get("rationale") or ""
        rule["questionnaire_fields"] = list(details.get("questionnaire_fields") or [])
        result[str(code)] = rule
    return result


def answered_from_data(rule):
    """True when the site fills this driver in from data (the drivers file gives it no questionnaire field)."""
    return not rule.get("questionnaire_fields")


def check_risks(risks, rules):
    """Things worth a person's look before the risks are used. Returns plain sentences; an empty list
    means nothing was found. Nothing is refused here.

    - a rule that can't be read
    - a level or kind of impact written in a way that is not read (CRITICAL instead of critical)
    - a rule naming a driver that isn't in the drivers file
    - a rule naming a driver that isn't in the risk's own driver lists
    """
    notes = []
    for risk_id in sorted(risks):
        risk = risks[risk_id]
        listed = rating.own_drivers(risk)
        for driver in sorted(listed - set(rules)):
            notes.append(f"{risk_id} lists {driver}, which is not in the drivers file.")

        rule_texts = {}
        for level, text in (risk.get("likelihood_scoring") or {}).items():
            if level not in rating.LIKELIHOOD_LEVELS_IN_FILES:
                notes.append(f"{risk_id}: likelihood level {level!r} is not read. Use critical or high.")
            rule_texts[f"likelihood {level}"] = text
        for kind, by_level in (risk.get("impact_scoring") or {}).items():
            if kind not in rating.IMPACT_KINDS:
                notes.append(f"{risk_id}: impact kind {kind!r} is not read. Use {', '.join(rating.IMPACT_KINDS)}.")
            for level, text in (by_level or {}).items():
                if level not in IMPACT_LEVELS_IN_FILES:
                    notes.append(f"{risk_id}, {kind}: level {level!r} is not read. Use critical, high, medium or low.")
                rule_texts[f"{kind} {level}"] = text

        for where, text in rule_texts.items():
            if text is None:
                continue
            try:
                expressions.read_rule(text)
            except ValueError as problem:
                notes.append(f"{risk_id}, {where}: {problem}")
                continue
            for driver in sorted(expressions.drivers_named(text)):
                if driver not in rules:
                    notes.append(f"{risk_id}, {where}: names {driver}, which is not in the drivers file.")
                elif driver not in listed:
                    notes.append(f"{risk_id}, {where}: names {driver}, which is not in the risk's driver lists.")
    return notes
