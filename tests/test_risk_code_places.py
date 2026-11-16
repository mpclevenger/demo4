"""The Risk site's "See the code" places: every listed function must still exist (a rename fails here)."""
from trust import codelinks
from trust.risk import code_places, data_drivers


def test_every_rating_rule_resolves():
    for file, function, _what in code_places.RATING_RULES:
        assert codelinks._lines(file, function) is not None, f"{file} {function} not found"
    assert len(code_places.rating_places()) == len(code_places.RATING_RULES)


def test_every_driver_calculation_resolves():
    for calculation in code_places.DRIVER_CALCULATIONS:
        assert codelinks._lines("risk/data_drivers.py", calculation) is not None, calculation
        place = code_places.driver_place(calculation)
        assert place["function"] == calculation and place["from"] <= place["to"]
    assert set(code_places.DRIVER_CALCULATIONS) == set(data_drivers.CALCULATION_FUNCTIONS)


def test_a_driver_code_gets_its_place():
    place = code_places.driver_place_for_code("RD21")
    assert place["function"] == "legacy_languages" and place["file"] == "backend/trust/risk/data_drivers.py"
    carried = code_places.with_places({"RD21": {"on": True}, "RD99": {"on": None}})
    assert carried["RD21"]["place"]["function"] == "legacy_languages" and carried["RD99"]["place"] is None
