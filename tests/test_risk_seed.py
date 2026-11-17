"""Uploading the risk files (owner, 16 Nov 2026): risk files, driver rules and the questionnaire seed the Risk site.

Every file here is made up (tools/test_risks). The site starts with an EMPTY risk files folder, so an upload is
what seeds it; the made-up teams are the ones in tests/risk_teams.py.
"""
import io
import json
import pathlib
import sys
import zipfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import config, web  # noqa: E402
from trust.risk import seed, site  # noqa: E402
from risk_teams import put_made_up_teams  # noqa: E402
from test_risk_site import GROUP, HEADERS, WORKED_ANSWERS, answer_all, post  # noqa: E402,F401

TEST_RISKS = pathlib.Path(__file__).resolve().parents[1] / "tools" / "test_risks"
RISK_FILES = sorted(TEST_RISKS.glob("air.*.yaml"))
DRIVER_FILE = TEST_RISKS / "driver_mapping.yaml"
QUESTIONNAIRE = TEST_RISKS / "questionnaire_example.yaml"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A Risk site whose risk files folder is empty, so nothing is there until something is uploaded."""
    empty = tmp_path / "no-risks"
    empty.mkdir()
    monkeypatch.setenv("TRUST_RISKS", str(empty))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    put_made_up_teams()
    return web.app.test_client()


def send(client, kind, step, paths, by="Rita Tester", extra=None):
    """Upload files to /api/risk/seed/<kind>/<step> the way the page does: a form with one or more files."""
    data = {"by": by, "file": [(io.BytesIO(pathlib.Path(path).read_bytes() if not isinstance(path, tuple) else path[1]),
                                pathlib.Path(path).name if not isinstance(path, tuple) else path[0]) for path in paths]}
    return client.post(f"/api/risk/seed/{kind}/{step}", data=data, headers=HEADERS, content_type="multipart/form-data")


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return path


# ----------------------------------------------------------------------------- the risk files

def test_the_made_up_risk_files_read_as_8_risks(client):
    answer = send(client, "risks", "check", RISK_FILES).json
    assert answer["ok"] and answer["items_total"] == 8
    assert answer["counts"]["New"] == 8                       # the site's folder is empty, so every risk is new
    assert answer["can_load"] and answer["problems"] == []
    assert answer["summary"] == "8 risks read: 8 new, 0 changed, 0 the same as now."


def test_a_zip_of_the_risk_files_reads_the_same_and_leaves_out_what_is_not_yaml(client, tmp_path):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        for path in RISK_FILES:
            zipped.writestr(f"risks/{path.name}", path.read_bytes())
        zipped.writestr("risks/readme.txt", "hello")
        zipped.writestr("driver_mapping.yaml", DRIVER_FILE.read_bytes())
    answer = send(client, "risks", "check", [("risks.zip", archive.getvalue())]).json
    assert answer["items_total"] == 8
    assert any("not YAML" in note for note in answer["notes"])
    assert any("drivers file" in note for note in answer["notes"])


def test_a_file_that_is_not_yaml_is_a_plain_problem(client, tmp_path):
    broken = write(tmp_path, "bad.yaml", "air.x.01: [unclosed\n  name: x")
    answer = send(client, "risks", "check", [broken]).json
    assert answer["ok"] and answer["items_total"] == 0 and not answer["can_load"]
    assert "bad.yaml can't be read as YAML" in answer["problems"][0]


def test_a_yaml_file_with_aliases_is_refused_before_it_can_grow(client, tmp_path):
    """The "billion laughs" file: a few lines of aliases that would expand to gigabytes if they were read."""
    lines = ["a: &a [x, x, x, x, x, x, x, x, x, x]"]
    for step, (before, now) in enumerate(zip("abcdefgh", "bcdefghi")):
        lines.append(f"{now}: &{now} [{', '.join(['*' + before] * 10)}]")
    bomb = write(tmp_path, "bomb.yaml", "\n".join(lines) + "\n")
    answer = send(client, "risks", "check", [bomb]).json
    assert answer["ok"] and answer["items_total"] == 0 and not answer["can_load"]
    assert "anchors or aliases" in answer["problems"][0]


def test_a_zip_that_unpacks_to_too_much_is_stopped(client, monkeypatch):
    monkeypatch.setattr(seed, "MOST_UNPACKED_BYTES", 3_000)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        for number in range(5):
            zipped.writestr(f"risks/air.big.{number}.yaml", "air.big.01:\n  name: " + "x" * 1_000 + "\n")
    answer = send(client, "risks", "check", [("big.zip", archive.getvalue())]).json
    assert any("unpacks to more than" in problem for problem in answer["problems"])
    assert 0 < answer["items_total"] < 5                      # the files read before the limit are still read


@pytest.mark.parametrize("trouble", [zipfile.BadZipFile("Bad CRC-32"), NotImplementedError("compression type 99"),
                                     RuntimeError("File is encrypted, password required")])
def test_a_file_in_a_zip_that_cannot_be_read_is_a_plain_problem_not_an_error(client, monkeypatch, trouble):
    def cannot_read(self, name, pwd=None):
        raise trouble
    monkeypatch.setattr(zipfile.ZipFile, "read", cannot_read)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("risks/air.ops.yaml", RISK_FILES[0].read_bytes())
    reply = send(client, "risks", "check", [("risks.zip", archive.getvalue())])
    assert reply.status_code == 200
    assert "can't be read from the .zip" in reply.json["problems"][0]


def test_a_damaged_zip_is_a_plain_problem(client):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as zipped:
        zipped.writestr("risks/air.ops.yaml", "air.ops.01:\n  name: Jobs fail\n")
    damaged = bytearray(archive.getvalue())
    damaged[damaged.index(b"Jobs fail")] ^= 0xFF               # one byte of the file's text changed: its check fails
    reply = send(client, "risks", "check", [("risks.zip", bytes(damaged))])
    assert reply.status_code == 200 and "can't be read from the .zip" in reply.json["problems"][0]


def test_loading_makes_the_uploaded_risks_the_sites_own(client):
    assert site.load_registers()["risks"] == {}
    loaded = send(client, "risks", "load", RISK_FILES).json
    assert loaded["ok"] and loaded["kept"]["by"] == "Rita Tester" and len(loaded["kept"]["file_hash"]) == 64
    assert len(site.load_registers()["risks"]) == 8
    again = send(client, "risks", "check", RISK_FILES).json            # now every one is the same as the site's
    assert again["counts"]["Same"] == 8 and not again["can_load"]
    history = client.get("/api/risk/seed").json
    assert [row["kind"] for row in history["earlier"]] == ["risks"]


# ----------------------------------------------------------------------------- the driver rules

def test_the_made_up_drivers_file_reads_as_21_drivers(client):
    answer = send(client, "drivers", "check", [DRIVER_FILE]).json
    assert answer["items_total"] == 21 and answer["counts"]["New"] == 21 and answer["problems"] == []
    assert "4 of them are answered from data" in answer["summary"]


def test_a_trigger_that_cannot_be_read_is_one_problem_and_the_rest_load(client, tmp_path):
    text = DRIVER_FILE.read_text().replace("(get(RD12)>=3)", "when twelve is big").replace("rationale: \"The team handles", "owner: Ann\n    rationale: \"The team handles", 1)
    path = write(tmp_path, "driver_mapping.yaml", text)
    answer = send(client, "drivers", "check", [path]).json
    assert answer["items_total"] == 20
    assert any(problem.startswith("RD12: the trigger") for problem in answer["problems"])
    assert any("'owner'" in note for note in answer["notes"])
    assert send(client, "drivers", "load", [path]).json["ok"]
    assert "RD12" not in site.load_registers()["driver_rules"] and "RD01" in site.load_registers()["driver_rules"]


def test_loading_the_drivers_and_the_risks_gives_the_form_its_questions(client):
    send(client, "risks", "load", RISK_FILES)
    send(client, "drivers", "load", [DRIVER_FILE])
    loaded = site.load_registers()
    assert len(loaded["driver_rules"]) == 21 and len(loaded["questions"]) == 17     # 4 are answered from data


# ----------------------------------------------------------------------------- the questionnaire

@pytest.fixture
def seeded(client):
    send(client, "risks", "load", RISK_FILES)
    send(client, "drivers", "load", [DRIVER_FILE])
    return client


def test_the_example_questionnaire_reads_with_the_map_and_lists_the_key_it_does_not_know(seeded):
    answer = send(seeded, "questions", "check", [QUESTIONNAIRE]).json
    assert answer["problems"] == []
    assert any("'weight' is in 1 question and is not in the map" in note for note in answer["notes"])
    in_file = [item for item in answer["items"] if item["status"] != "Switched off"]
    assert len(in_file) == 6 and answer["items_total"] == 17          # the other 11 on the site aren't in the file
    assert answer["summary"].startswith("6 questions read") and "11 questions on the site are not in the file" in answer["summary"]
    by_field = {item["id"]: item for item in answer["items"]}
    assert by_field["RD31"]["switches"] == "No"                         # the file says a no turns it on
    assert by_field["RD12"]["switches"] == "At least 3"                 # ">= 3"
    assert by_field["RD14_pct"]["switches"] == "More than 0.4"          # "more than 40%" is a part of one
    assert by_field["RD41_days"]["switches"] == "More than 365"
    assert by_field["RD01"]["help"].startswith("Say yes")
    assert by_field["RD02"]["section"] == "Data" and by_field["RD12"]["order"] == 40


def test_a_question_for_a_driver_that_is_not_there_is_a_problem_and_is_left_out(seeded, tmp_path):
    text = QUESTIONNAIRE.read_text() + "  - field: RD99\n    question: A question for nothing\n    type: yes/no\n    switches_on: yes\n"
    answer = send(seeded, "questions", "check", [write(tmp_path, "q.yaml", text)]).json
    assert len([item for item in answer["items"] if item["status"] != "Switched off"]) == 6
    assert answer["problems"] == ["Question 7 (RD99) feeds RD99, and there is no driver with that field in the driver rules, so it was left out."]


def test_a_question_for_a_driver_answered_from_data_is_a_plain_problem(seeded, tmp_path):
    text = "questions:\n  - field: RD22\n    question: How often do you release?\n    type: number\n    switches_on: 3\n"
    answer = send(seeded, "questions", "check", [write(tmp_path, "q.yaml", text)]).json
    assert answer["items_total"] == 0 and "prevailing median" in answer["problems"][0]


def test_other_names_in_the_map_work_and_the_map_can_be_edited(seeded, tmp_path, monkeypatch):
    """The owner's file can use other key names, and a name added to the map is found."""
    text = ("Form:\n  Sections:\n    - Title: Access\n      Items:\n        - Driver Code: rd01\n          Prompt: Own accounts?\n"
            "          Answer Type: boolean\n          Turns On: true\n")
    mine = write(tmp_path, "mine.yaml", text)
    assert "was not found" in send(seeded, "questions", "check", [mine]).json["problems"][0]
    mapping = json.loads(seeded.get("/api/risk/seed").json and (seed.map_path()).read_text())
    mapping["question_list"] = ["form.sections"] + mapping["question_list"]
    mapping["field"] = ["driver_code"] + mapping["field"]
    mapping["text"] = ["prompt"] + mapping["text"]
    mapping["kind"] = ["answer_type"] + mapping["kind"]
    mapping["switches_on"] = ["turns_on"] + mapping["switches_on"]
    changed = tmp_path / "map.json"
    changed.write_text(json.dumps(mapping))
    monkeypatch.setenv("TRUST_RISK_QUESTIONNAIRE_MAP", str(changed))
    answer = send(seeded, "questions", "check", [mine]).json
    assert answer["problems"] == [] and answer["items"][0]["section"] == "Access" and answer["items"][0]["switches"] == "Yes"


def test_loading_the_questionnaire_puts_the_questions_in_the_list_with_history(seeded):
    answer = send(seeded, "questions", "load", [QUESTIONNAIRE]).json
    assert answer["ok"] and answer["held"]["questions"] == 6           # the 11 not in the file are switched off
    listed = seeded.get("/api/edit/questions").json
    by_key = {entry["key"]: entry for entry in listed["entries"]}
    assert by_key["RD31"]["values"]["switches_on"] == "no" and by_key["RD31"]["values"]["section"] == "Change"
    assert by_key["RD14_pct"]["values"]["number"] == 0.4
    reasons = [(row["by"], row["reason"]) for row in listed["history"]]
    assert ("Rita Tester", "Loaded from the uploaded questionnaire questionnaire_example.yaml.") in reasons
    assert any(row["reason"] == "First load from the file." for row in listed["history"])
    again = send(seeded, "questions", "check", [QUESTIONNAIRE]).json
    assert again["counts"]["Same"] == 6 and not again["can_load"]


def test_see_what_would_move_uses_the_newest_ratings_of_each_team(seeded, tmp_path):
    """The Lending team answered RD12 = 2 (not 3 or more). A questionnaire saying 2 is enough switches RD12 on.
    The questionnaire is loaded first, so the questions it doesn't have are already switched off."""
    same_as_the_files = QUESTIONNAIRE.read_text().replace('switches_on: "no"', "switches_on: yes")     # the files' own reading of RD31
    assert send(seeded, "questions", "load", [write(tmp_path, "same.yaml", same_as_the_files)]).json["ok"]
    asked = {entry["key"] for entry in seeded.get("/api/edit/questions").json["entries"] if not entry["retired"]}
    answer_all(seeded, {field: answer for field, answer in WORKED_ANSWERS.items() if field in asked})
    assert post(seeded, f"/api/risk/groups/{GROUP}/submit", {"confirm_unanswered": True}).status_code == 200
    quiet = send(seeded, "questions", "preview", [write(tmp_path, "same.yaml", same_as_the_files)]).json
    assert quiet["moves"] == [] and quiet["moves_summary"] == "No team's newest ratings would change."
    text = same_as_the_files.replace('switches_on: ">= 3"', 'switches_on: "at least 2"')
    moved = send(seeded, "questions", "preview", [write(tmp_path, "q.yaml", text)]).json
    assert moved["moves"] and {move["group"] for move in moved["moves"]} == {"Lending Platform"}
    assert moved["moves_summary"].endswith("in 1 team.")
    history = seeded.get("/api/edit/questions").json["history"]
    assert not any("q.yaml" in row["reason"] for row in history)        # previewing keeps nothing


def test_a_changed_driver_rule_moves_ratings_too(seeded, tmp_path):
    answer_all(seeded, WORKED_ANSWERS)
    post(seeded, f"/api/risk/groups/{GROUP}/submit", {"confirm_unanswered": True})
    text = DRIVER_FILE.read_text().replace("(get(RD12)>=3)", "(get(RD12)>=2)")
    moved = send(seeded, "drivers", "preview", [write(tmp_path, "driver_mapping.yaml", text)]).json
    assert moved["counts"]["Changed"] == 1 and moved["moves"]


# ----------------------------------------------------------------------------- who may, and the mapping file

def test_only_tech_risk_may_upload_once_access_is_set_up(client, tmp_path, monkeypatch):
    access = tmp_path / "access.json"
    access.write_text(json.dumps({"user_header": "X-User", "groups_header": "X-Groups", "groups": {"tech_risk": ["TRUST-TR"]}}))
    monkeypatch.setenv("TRUST_ACCESS", str(access))
    put_made_up_teams()
    files = {"file": [(io.BytesIO(RISK_FILES[0].read_bytes()), "air.cyber.yaml")]}
    other = client.post("/api/risk/seed/risks/load", data=files, headers={"X-TRUST": "1", "X-User": "pat1", "X-Groups": ""},
                        content_type="multipart/form-data")
    assert other.status_code == 403
    files = {"file": [(io.BytesIO(RISK_FILES[0].read_bytes()), "air.cyber.yaml")]}
    tech = client.post("/api/risk/seed/risks/load", data=files, headers={"X-TRUST": "1", "X-User": "trisk", "X-Groups": "TRUST-TR"},
                       content_type="multipart/form-data")
    assert tech.status_code == 200 and tech.json["kept"]["by"] == "trisk"


def test_a_name_is_needed_while_open_and_the_header_always(client):
    nameless = send(client, "risks", "check", RISK_FILES, by="")
    assert nameless.status_code == 400 and "name" in nameless.json["error"]
    no_header = client.post("/api/risk/seed/risks/check", data={"by": "x"}, content_type="multipart/form-data")
    assert no_header.status_code == 403


def test_the_shipped_map_has_how_to_and_every_part_of_a_question():
    mapping = seed.read_map()
    assert mapping["_how_to"]
    for part in ("question_list", "field", "text", "section", "order", "kind", "switches_on", "help", "kind_words"):
        assert mapping[part]


def test_the_status_page_shows_the_kept_controls_copy_and_the_map(client):
    status = client.get("/api/risk/seed").json
    assert status["can_upload"] and status["controls"]["copy"] is None
    assert status["mapping"]["file"] == "config/risk_questionnaire_map.json" and status["mapping"]["content"]["field"]
