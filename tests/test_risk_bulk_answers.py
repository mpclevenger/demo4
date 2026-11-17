"""Questionnaire answers in bulk, as a CSV (owner, 17 Nov 2026): download, fill in, upload back as drafts; the team's
results then show as Proposed until the form is submitted."""
import csv
import io
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from test_risk_site import GROUP, HEADERS, WORKED_ANSWERS, client, post, test_files  # noqa: E402,F401
from trust import storage  # noqa: E402
from trust.risk import team_results  # noqa: E402


def download(client):
    reply = client.get("/api/risk/answers.csv")
    assert reply.status_code == 200
    return list(csv.DictReader(io.StringIO(reply.data.decode("utf-8-sig"))))


def upload(client, step, rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    data = {"file": (io.BytesIO(out.getvalue().encode("utf-8")), "answers.csv"), "by": "Rita Tester"}
    return client.post(f"/api/risk/answers/{step}", data=data, headers=HEADERS, content_type="multipart/form-data")


def filled(rows, answers, group=GROUP):
    return [{**row, "answer": answers.get(row["question_code"], row["answer"]) if row["team_id"] == group else row["answer"]}
            for row in rows]


def test_the_download_has_a_row_per_team_and_question(client):
    rows = download(client)
    assert rows and set(rows[0]) >= {"team_id", "team", "question_code", "question", "answer"}
    teams = {row["team_id"] for row in rows}
    questions = {row["question_code"] for row in rows}
    assert GROUP in teams and len(rows) == len(teams) * len(questions)


def test_check_saves_nothing_and_load_saves_drafts_that_show_as_proposed(client):
    rows = filled(download(client), WORKED_ANSWERS)
    checked = upload(client, "check", rows).json
    assert checked["ok"] and checked["counts"]["to_save"] == len(WORKED_ANSWERS) and not checked["problems"]
    assert storage.risk_answers(GROUP) == []                                   # check saves nothing
    loaded = upload(client, "load", rows).json
    assert loaded["ok"] and len(storage.risk_answers(GROUP)) == len(WORKED_ANSWERS)
    assert storage.risk_assessments(GROUP) == []                               # nothing is submitted
    assert all("(bulk upload)" in row["by"] for row in storage.risk_answers(GROUP))
    team_results.work_out_all("command line")                                  # python manage.py risk_results
    results = client.get(f"/api/risk/teams/{GROUP}/results").json
    assert results["assessed"] and results["team"]["proposed"] and results["message"].startswith("Proposed")
    again = upload(client, "check", rows).json                                 # the same file again: nothing new
    assert again["counts"]["to_save"] == 0 and again["counts"]["same"] == len(WORKED_ANSWERS)


def test_after_submit_the_results_are_no_longer_proposed(client):
    upload(client, "load", filled(download(client), WORKED_ANSWERS))
    team_results.work_out_all("command line")
    post(client, f"/api/risk/groups/{GROUP}/submit", {"confirm_unanswered": True})
    kept = client.get(f"/api/risk/teams/{GROUP}/results").json
    assert kept["team"]["proposed"]                                             # kept until risk_results runs again
    team_results.work_out_all("command line")
    results = client.get(f"/api/risk/teams/{GROUP}/results").json
    assert results["assessed"] and not results["team"]["proposed"]


def test_rows_the_file_cant_use_are_listed_and_the_rest_still_count(client):
    rows = download(client)
    first = next(row for row in rows if row["team_id"] == GROUP)
    bad = [{**first, "team_id": "no-such-team", "answer": "yes"},
           {**first, "question_code": "RD999", "answer": "yes"},
           {**first, "question_code": "RD12", "answer": "lots"},
           {**first, "question_code": "RD01", "answer": "yes"}]
    checked = upload(client, "check", bad).json
    assert checked["counts"]["to_save"] == 1 and len(checked["problems"]) == 3
    assert any("no team 'no-such-team'" in p for p in checked["problems"]) and any("RD999" in p for p in checked["problems"])


def test_a_file_without_the_needed_columns_is_refused_in_plain_words(client):
    reply = upload(client, "check", [{"team": "x", "answer": "yes"}])
    assert reply.status_code == 400 and "missing the column team_id and question_code" in reply.json["error"]
