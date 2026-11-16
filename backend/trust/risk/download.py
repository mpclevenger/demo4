"""The Risk site's risks and drivers, in the shape the risk engine's files have, as one .zip.

The zip holds exactly what TRAC keeps in its content/engine/ folder, so it can be unzipped there and loaded with
TRAC's sync_engine command:

    driver_mapping.yaml        every driver: trigger, questionnaire_fields, rationale
    risks/<risk id>.yaml       one file for each risk (air.ops.02.yaml), with the engine's risk fields

Only the engine's own fields are written. Anything the Risk site adds for itself (building blocks, groups) stays out.
"""
import io
import pathlib
import re
import zipfile

import yaml

from trust import config
from trust.risk import drivers, files

DRIVERS_PATH_IN_ZIP = files.DRIVERS_FILE
RISKS_FOLDER_IN_ZIP = "risks"
RISK_FIELDS_IN_ORDER = ("domain", "category", "name", "likelihood_scoring", "likelihood_drivers", "impact_drivers",
                        "impact_scoring", "description", "example", "framework_mappings")
FIXED_TIME_IN_ZIP = (2026, 1, 1, 0, 0, 0)    # the same registers always make the same zip


def risk_file_name(risk_id):
    """The file name for a risk's id. Anything but letters, digits, dots, dashes and underscores becomes an underscore,
    so an odd id can't place a file outside the folder it is unzipped into. A name can't start with a dot."""
    name = re.sub(r"[^A-Za-z0-9._-]", "_", str(risk_id))
    return "_" + name[1:] if name.startswith(".") else name or "_"


def _field_name(raw_key):
    """'framework mappings' and 'framework-mappings' are read as framework_mappings, as TRAC reads them."""
    return str(raw_key).strip().lower().replace(" ", "_").replace("-", "_")


def _dump(document, first_line):
    text = yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=110, default_flow_style=False)
    return f"# {first_line}\n{text}"


def risk_file_text(risk_id, risk):
    """One risk as the engine's file shape. Keys are the engine's own; missing ones are left out."""
    by_name = {_field_name(key): value for key, value in risk.items()}
    document = {name: by_name[name] for name in RISK_FIELDS_IN_ORDER if by_name.get(name) is not None}
    return _dump(document, f"Risk {risk_id}, downloaded from the Risk site.")


def _raw_drivers():
    """The drivers file as it was written, so a trigger keeps its own wording. {} when the file isn't there."""
    path = pathlib.Path(config.risks_dir()) / files.DRIVERS_FILE
    if not path.exists():
        return {}
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("risk_drivers") or {}


def driver_entry(rule, raw_entry):
    """One driver as the engine writes it. The file's own trigger wording is kept while it still means the rule."""
    trigger = drivers.trigger_from_rule(rule)
    if raw_entry:
        try:
            same_keys = ("field", "test", "value", "trigger")
            as_written = drivers.rule_from_trigger(raw_entry["trigger"])
            if {key: as_written.get(key) for key in same_keys} == {key: rule.get(key) for key in same_keys}:
                trigger = raw_entry["trigger"]
        except (ValueError, KeyError):
            pass
    return {"trigger": trigger, "questionnaire_fields": list(rule.get("questionnaire_fields") or []),
            "rationale": rule.get("rationale") or ""}


def drivers_file_text(driver_rules):
    raw = _raw_drivers()
    entries = {code: driver_entry(rule, raw.get(code)) for code, rule in sorted(driver_rules.items())}
    return _dump({"risk_drivers": entries}, "Risk drivers, downloaded from the Risk site.")


def build_zip(loaded):
    """The zip, as bytes, from the registers as the site reads them (load_registers())."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        def add(name, text):
            info = zipfile.ZipInfo(name, FIXED_TIME_IN_ZIP)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, text.encode("utf-8"))
        add(DRIVERS_PATH_IN_ZIP, drivers_file_text(loaded["driver_rules"]))
        for risk_id, risk in sorted(loaded["risks"].items()):
            add(f"{RISKS_FOLDER_IN_ZIP}/{risk_file_name(risk_id)}.yaml", risk_file_text(risk_id, risk))
    return buffer.getvalue()
