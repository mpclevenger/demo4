"""The owner's questionnaire layout (16 Nov 2026): questions keyed by driver code, with question_text, input_type,
enabled, tags, description and applicable_business_processes. Not every driver has a question."""
import pytest

from test_risk_seed import client, seeded, send, write  # noqa: F401  (fixtures and helpers)

OWNER = """questions:
  RD01:
    driver: RD01
    description: Access to confidential data
    question_text: Do members of your team have access to confidential data, including client-provided data sets?
    input_type: Boolean
    enabled: true
    tags:
    - Data
    - Access
    applicable_business_processes: all
  RD12:
    driver: RD12
    description: Number of things
    question_text: How many things?
    input_type: Integer
    enabled: true
    tags: [Change]
    applicable_business_processes: all
"""

SWITCHED_OFF = """
  RD02:
    driver: RD02
    description: Something else
    question_text: Is it switched off?
    input_type: Boolean
    enabled: false
    tags: [Data]
    applicable_business_processes: all
"""


def test_the_owners_layout_reads(seeded, tmp_path):
    answer = send(seeded, "questions", "check", [write(tmp_path, "q.yaml", OWNER)]).json
    assert answer["problems"] == []
    by_field = {item["id"]: item for item in answer["items"]}
    assert {key for key, item in by_field.items() if item["status"] != "Switched off"} == {"RD01", "RD12"}
    assert by_field["RD01"]["name"].startswith("Do members of your team")
    assert by_field["RD01"]["section"] == "Data"                        # the first tag
    assert by_field["RD01"]["switches"] == "Yes"
    assert by_field["RD12"]["section"] == "Change"
    unused = [note for note in answer["notes"] if "not in the map" in note]
    assert {"description", "applicable_business_processes"} == {note.split("'")[1] for note in unused}


def test_switching_off_a_question_on_the_site_retires_it_and_it_can_come_back(seeded, tmp_path):
    """RD02 is on the site already (the driver file gives every driver a question). enabled: false switches it off."""
    off = send(seeded, "questions", "check", [write(tmp_path, "off.yaml", OWNER + SWITCHED_OFF)]).json
    assert off["problems"] == []
    assert {item["id"]: item["status"] for item in off["items"]}["RD02"] == "Switched off"
    assert "1 switched off" in off["summary"]
    assert send(seeded, "questions", "load", [write(tmp_path, "off.yaml", OWNER + SWITCHED_OFF)]).json["ok"]
    listed = seeded.get("/api/edit/questions").json
    entries = {entry["key"]: entry for entry in listed["entries"]}
    assert entries["RD02"]["retired"] and not entries["RD01"]["retired"]
    assert any("enabled: false" in row["reason"] for row in listed["history"])

    again = send(seeded, "questions", "check", [write(tmp_path, "off.yaml", OWNER + SWITCHED_OFF)]).json
    assert "RD02" not in {item["id"] for item in again["items"]}             # already off: nothing to do
    assert any("so not asked: RD02" in note for note in again["notes"])

    on = OWNER + SWITCHED_OFF.replace("enabled: false", "enabled: true")
    back = send(seeded, "questions", "check", [write(tmp_path, "on.yaml", on)]).json
    assert {item["id"]: item["status"] for item in back["items"]}["RD02"] == "Restored"


def test_questions_not_in_the_file_are_switched_off_and_their_drivers_show_not_known(seeded, tmp_path):
    """Owner, 16 Nov 2026: not every driver has a question; the questionnaire decides what is asked."""
    check = send(seeded, "questions", "check", [write(tmp_path, "q.yaml", OWNER)]).json
    off = {item["id"] for item in check["items"] if item["status"] == "Switched off"}
    assert "RD02" in off and "RD01" not in off and "RD12" not in off
    assert "would be switched off" in check["summary"] and "not known" in check["summary"]
    assert send(seeded, "questions", "load", [write(tmp_path, "q.yaml", OWNER)]).json["ok"]
    listed = seeded.get("/api/edit/questions").json
    active = {entry["key"] for entry in listed["entries"] if not entry["retired"]}
    assert active == {"RD01", "RD12"}
    assert any("Not in the questionnaire, so not asked." in row["reason"] for row in listed["history"])


def test_a_question_the_file_has_but_cannot_read_is_never_switched_off(seeded, tmp_path):
    broken = OWNER + "  RD02:\n    driver: RD02\n    input_type: Boolean\n"          # no wording
    check = send(seeded, "questions", "check", [write(tmp_path, "q.yaml", broken)]).json
    assert any("RD02" in problem and "no wording" in problem for problem in check["problems"])
    assert "RD02" not in {item["id"] for item in check["items"]}


def test_a_file_with_no_readable_questions_switches_nothing_off(seeded, tmp_path):
    check = send(seeded, "questions", "check", [write(tmp_path, "q.yaml", "questions:\n  RD01:\n    driver: RD01\n")]).json
    assert check["items_total"] == 0


def test_switch_words_for_a_driver_with_a_full_trigger():
    from trust.risk import seed
    assert seed.switch_words({"kind": "number", "test": None, "number": None}) == "As the driver's trigger says"
    assert seed.switch_words({"kind": "text", "test": None, "number": None}) == "As the driver's trigger says"
