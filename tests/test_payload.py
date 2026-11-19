"""Payload tests. Run with: python3 -m pytest tests (or python3 tests/test_payload.py)."""

import importlib.util
from pathlib import Path

_path = Path(__file__).parents[1] / "custom_components/aerotermia_espana/payload.py"
_spec = importlib.util.spec_from_file_location("payload", _path)
payload = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(payload)

STATES = {"consumed_kwh": "3168.2", "produced_kwh": "26618.9", "outdoor_temp": "unavailable"}


def test_builds_payload_with_nulls_and_counters():
    body = payload.build_payload(24, "2026-11-19 10:05:12", STATES, {"defrost_cycles": 3})
    assert body == {
        "installation_id": 24,
        "energy_mode": "cumulative",
        "local_datetime": "2026-11-19 10:05:12",
        "consumed_kwh": 3168.2,
        "produced_kwh": 26618.9,
        "outdoor_temp": None,
        "defrost_cycles": 3,
    }


def test_unavailable_energy_skips_push():
    states = {**STATES, "produced_heating_kwh": "unknown"}
    try:
        payload.build_payload(24, "x", states, {})
    except payload.MissingData as err:
        assert err.fields == ["produced_heating_kwh"]
    else:
        raise AssertionError("expected MissingData")


def test_unmapped_required_skips_push():
    try:
        payload.build_payload(24, "x", {"consumed_kwh": "1"}, {})
    except payload.MissingData as err:
        assert err.fields == ["produced_kwh"]
    else:
        raise AssertionError("expected MissingData")


def test_nan_is_null():
    assert payload.to_number("nan") is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
