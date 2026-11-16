"""Metric cards link to the code behind them (owner, 5 Nov 2026), with real line numbers, only when code_repo_url is set."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import codelinks  # noqa: E402


def _settings(tmp_path, monkeypatch, **extra):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"hr_root_sam_account": "x", **extra}))
    monkeypatch.setenv("TRUST_SETTINGS", str(p))


def test_no_repo_address_still_gives_places_without_urls(tmp_path, monkeypatch):
    _settings(tmp_path, monkeypatch)
    out = codelinks.links()
    assert out["metrics"] and out["repo"] is None
    for rows in out["metrics"].values():
        assert rows
        for r in rows:
            assert r["url"] is None and 0 < r["from"] <= r["to"] and r["file"] and r["function"]


def test_every_code_entry_and_shared_step_is_a_real_function():
    """A renamed function fails here, so the cards can't point at code that moved."""
    for mid, places in codelinks.metric_code().items():
        for file, func, *_ in places:
            assert codelinks._lines(file, func), f"{mid}: {file} {func}() not found"
    for file, func, _ in codelinks.SHARED:
        assert codelinks._lines(file, func), f"shared: {file} {func}() not found"


def test_every_measured_metric_has_code_entries():
    from trust import config
    for mid, x in config.metrics().items():
        if x.get("status") == "Measured":
            assert (x.get("counting") or {}).get("code"), mid


def test_every_mapped_function_resolves_to_real_lines(tmp_path, monkeypatch):
    _settings(tmp_path, monkeypatch, code_repo_url="https://github.example.com/tech-risk/trust/")
    monkeypatch.setenv("TRUST_GIT_SHA", "abc1234")
    out = codelinks.links()
    assert out["ref"] == "abc1234" and out["repo"].endswith("/trust")
    for mid, places in codelinks.metric_code().items():
        rows = out["metrics"][mid]
        assert len(rows) == len(places) + len(codelinks.SHARED), mid
        for r in rows:
            assert 0 < r["from"] <= r["to"]
            assert r["url"] == f"https://github.example.com/tech-risk/trust/blob/abc1234/{r['file']}#L{r['from']}-L{r['to']}"
    rule = next(r for r in out["metrics"]["TE-02"] if "client impact" in r["what"])
    src = (pathlib.Path(__file__).resolve().parents[1] / "backend/trust/score_month.py").read_text().splitlines()
    assert any('client_impact' in src[n - 1] for n in range(rule["from"], rule["to"] + 1))
    assert rule["to"] - rule["from"] <= 4                      # the rule, not the whole function


def test_ref_falls_back_to_code_ref(tmp_path, monkeypatch):
    _settings(tmp_path, monkeypatch, code_repo_url="https://x.example/r", code_ref="release")
    monkeypatch.delenv("TRUST_GIT_SHA", raising=False)
    monkeypatch.setattr(codelinks.storage, "git_sha", lambda: None)
    assert codelinks.links()["ref"] == "release"


def test_every_page_place_resolves():
    """The places pages point at (watch list, feed readers, upload checks, mapping) are real functions: a renamed one fails here."""
    wanted = {"watch_list": 4, "upload_checks": 2, "mapping": 1}
    out = codelinks.page_places()
    for key, count in wanted.items():
        assert len(out[key]) == count, f"{key}: a place in codelinks.page_places() is not found in the code"
    assert set(out["feed_readers"]) == set(codelinks.FEED_READERS), "a feed reader is not found in the code"
    for row in [*out["watch_list"], *out["upload_checks"], *out["mapping"], *out["feed_readers"].values()]:
        assert 0 < row["from"] <= row["to"] and row["url"] is None or row["url"]
