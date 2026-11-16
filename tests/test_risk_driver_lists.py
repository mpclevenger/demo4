"""A risk file may list its drivers as plain codes or as a block per driver; anything else is explained, not a crash."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))

from trust import config  # noqa: E402
from trust.risk import seed  # noqa: E402

RISK_WITH_BLOCKS = """
air.cyber.01:
  domain: Cyber
  name: External data breach
  likelihood_drivers:
    - id: RD01
      weight: 2
    - RD36: {note: tool access}
    - RD54
  impact_drivers: {RD02: {why: client data}, RD54: {}}
"""

RISK_WITH_ODD_ENTRY = """
air.cyber.02:
  domain: Cyber
  name: Something else
  likelihood_drivers:
    - {weight: 2, note: no code here}
    - RD01
  impact_drivers: 7
"""


def test_blocks_per_driver_are_read_as_codes():
    problems, notes = [], []
    risks = seed.read_risks([("air.cyber.yaml", RISK_WITH_BLOCKS)], problems, notes)
    assert risks["air.cyber.01"]["likelihood_drivers"] == ["RD01", "RD36", "RD54"]
    assert risks["air.cyber.01"]["impact_drivers"] == ["RD02", "RD54"]
    assert problems == []


def test_an_entry_that_is_not_a_code_is_explained_not_a_crash():
    problems, notes = [], []
    risks = seed.read_risks([("air.cyber.yaml", RISK_WITH_ODD_ENTRY)], problems, notes)
    assert risks["air.cyber.02"]["likelihood_drivers"] == ["RD01"]
    assert risks["air.cyber.02"]["impact_drivers"] == []
    assert any("one entry in likelihood_drivers isn't a driver code" in p for p in problems)
    assert any("impact_drivers isn't a list of driver codes" in p for p in problems)


def test_the_whole_upload_check_answers_in_plain_words():
    result, _keep = seed.check_risk_upload([("air.cyber.yaml", RISK_WITH_ODD_ENTRY.encode())])
    assert any("air.cyber.02" in p and "isn't a driver code" in p for p in result["problems"])


def test_plain_codes_still_work():
    tidy, problems = config.tidy_driver_lists("x", {"likelihood_drivers": ["RD01", "RD36"]})
    assert tidy["likelihood_drivers"] == ["RD01", "RD36"] and problems == []


def test_an_unexpected_file_gets_a_plain_answer_not_a_server_error(monkeypatch, tmp_path):
    import io
    from trust.risk import seed as seed_module
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path))
    from trust import web
    monkeypatch.setattr(seed_module, "check", lambda kind, uploads: (_ for _ in ()).throw(TypeError("unhashable type: 'dict'")))
    client = web.app.test_client()
    answer = client.post("/api/risk/seed/risks/check", headers={"X-TRUST": "1"},
                         data={"by": "Pat", "file": (io.BytesIO(b"a: 1"), "air.cyber.yaml")},
                         content_type="multipart/form-data")
    assert answer.status_code == 400
    assert "nothing was saved" in (answer.get_json().get("error") or answer.get_json().get("message") or str(answer.get_json()))


# The owner's real layout (16 Nov 2026): lowercase codes in the lists, capitals in the rules, ">= 0.80" shares.
OWNERS_LAYOUT = """
air.cyber.01:
  domain: cyber
  category: unauthorized access
  name: external data breach
  likelihood_scoring:
    critical: '>= 0.80 and (RD01 in ad or RD02 in ad or RD03 in ad)'
    high: '>= 0.60 and (RD01 in ad or RD02 in ad or RD03 in ad)'
  likelihood_drivers:
  - rd01
  - rd02
  - rd03
  impact_drivers:
  - rd01
  - rd02
  impact_scoring:
    financial_impact:
      critical: null
      high: RD50 in ad
      medium: RD02 in ad
      low: dc >= 1
    client_impact:
      critical: null
      high: RD48 in ad
      medium: RD25 in ad
      low: dc >= 1
    regulatory_impact:
      critical: null
      high: RD43 in ad
      medium: RD51 in ad
      low: dc >= 1
  description: words here
  example: of the risk occurring
  framework_mappings:
    iso_25010:
    - characteristic: security
      sub-characteristic: Confidentiality
    nist_sp_800_30:
    - threat_source: null
      threat_event: null
"""


def test_the_owners_layout_reads_and_rates():
    from trust.risk import rating
    problems, notes = [], []
    risks = seed.read_risks([("air.cyber.yaml", OWNERS_LAYOUT)], problems, notes)
    risk = risks["air.cyber.01"]
    assert problems == []
    assert risk["likelihood_drivers"] == ["RD01", "RD02", "RD03"]
    assert risk["impact_drivers"] == ["RD01", "RD02"]
    SETTINGS = {"medium_share_above": 0.3, "elevated_likelihood_at_least": "HIGH", "elevated_impact_at_least": "HIGH"}
    all_on = rating.rate_risk(risk, {"RD01", "RD02", "RD03"}, SETTINGS)
    assert all_on["applicable"] is True
    assert rating.likelihood(risk, {"RD01", "RD02", "RD03"}, SETTINGS) == "CRITICAL"


def test_lowercase_driver_codes_in_the_drivers_file_match_the_rules():
    problems, notes = [], []
    rules = seed.read_driver_rules([("driver_mapping.yaml", """
risk_drivers:
  rd01:
    trigger: "(get(rd01)==TRUE)"
    questionnaire_fields: [rd01]
    rationale: A plain sentence.
""")], problems, notes)
    assert "RD01" in rules


def test_the_owners_trigger_layout_is_read():
    """Owner, 16 Nov 2026: the real driver file writes (get('RD01') == True)."""
    problems, notes = [], []
    rules = seed.read_driver_rules([("driver_mapping.yaml", """
risk_drivers:
  RD01:
    trigger: (get('RD01') == True)
    questionnaire_fields: [RD01]
    rationale: A plain sentence.
  RD22:
    trigger: (get('RD22') > prevailing('RD22'))
    questionnaire_fields: []
    rationale: Another sentence.
""")], problems, notes)
    assert problems == []
    assert rules["RD01"]["test"] == "is yes" and rules["RD01"]["field"] == "RD01"
    assert rules["RD22"]["test"] == "above the prevailing median"
