"""Which TRUST building block (Security, Releases, ...) each risk belongs to, for display on the Risk site.

Display only: nothing here changes a TRUST score. The placement is in config/risk_building_blocks.json:
a risk's own ID first, then its domain. While TRUST_RISKS points at a made-up folder, that folder's own
risk_building_blocks.json is read instead.
"""
import json
import pathlib

from trust import config

BLOCKS_FILE = "risk_building_blocks.json"
NOT_PLACED = "Not placed yet"


def blocks_path():
    in_risk_files = pathlib.Path(config.risks_dir()) / BLOCKS_FILE
    if in_risk_files.is_file():
        return in_risk_files
    return pathlib.Path(__file__).resolve().parents[3] / "config" / BLOCKS_FILE


def load():
    """{"by_domain": {...}, "by_risk": {...}}; both empty when there is no file."""
    path = blocks_path()
    if not path.is_file():
        return {"by_domain": {}, "by_risk": {}}
    document = json.loads(path.read_text(encoding="utf-8"))
    return {"by_domain": document.get("by_domain") or {}, "by_risk": document.get("by_risk") or {}}


def block_of(risk_id, risk, placements):
    """The building block for one risk: its own placement, else its domain's, else NOT_PLACED."""
    if risk_id in placements["by_risk"]:
        return placements["by_risk"][risk_id]
    return placements["by_domain"].get(risk.get("domain"), NOT_PLACED)
