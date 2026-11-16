"""The registers the Risk site reads: its risks, drivers and questions, and the rating settings and building blocks.

Where they come from, in this order:
  1. The newest upload of each kind (Tech Risk's "Upload risk files" page, seed.py). Once risks or drivers have been
     loaded from an upload, the site holds them and the risk files folder is not read for that kind.
  2. Otherwise the risk files folder (TRUST_RISKS, else config/risks/).
  3. On top of both, the changes saved on the editing pages (editable.py).
"""
from trust import config, editable, storage
from trust.risk import blocks, files, questions as question_list, rating

RISKS, DRIVERS = "risks", "drivers"                      # the two kinds of upload that fill the registers


def uploaded_registers():
    """(risks, driver rules) from the newest load of each kind, or None for a kind never loaded."""
    return storage.risk_seed_newest_registers(RISKS), storage.risk_seed_newest_registers(DRIVERS)


def load_registers():
    """The risks, drivers and questions as the site reads them now, with the `from_files` copy of what the files and
    uploads alone said (the editing pages show it). `notes` are plain sentences about anything missing or worth a look."""
    notes = []
    uploaded_risks, uploaded_drivers = uploaded_registers()
    risks = uploaded_risks if uploaded_risks is not None else config.risks()
    driver_rules = uploaded_drivers
    if driver_rules is None:
        try:
            driver_rules = files.driver_rules(config.risks_dir())
        except FileNotFoundError:
            driver_rules = {}
            notes.append(f"There is no {files.DRIVERS_FILE} in the risk files folder, so there are no drivers and no questions yet.")
    if not risks:
        notes.append("There are no risk files in the risk files folder yet.")
    notes.extend(files.check_risks(risks, driver_rules))
    loaded = {"risks": risks, "driver_rules": driver_rules,
              "questions": question_list.build(driver_rules, risks),
              "settings": rating.starting_settings(), "placements": blocks.load(), "notes": notes}
    return editable.with_saved_changes(loaded)
