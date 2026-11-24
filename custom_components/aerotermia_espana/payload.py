"""Build the push payload. Pure Python, no Home Assistant imports, so it is testable alone."""

from __future__ import annotations

import math

REQUIRED = ("consumed_kwh", "produced_kwh")
ENERGY = REQUIRED + (
    "consumed_heating_kwh",
    "produced_heating_kwh",
    "consumed_acs_kwh",
    "produced_acs_kwh",
    "consumed_cooling_kwh",
    "produced_cooling_kwh",
)


class MissingData(Exception):
    """A mapped energy sensor has no value, so the push must be skipped."""

    def __init__(self, fields: list[str]) -> None:
        super().__init__(", ".join(fields))
        self.fields = fields


def to_number(state: str | None) -> float | None:
    """Return the state as a finite float, or None for unknown/unavailable/garbage."""
    try:
        value = float(state)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def to_count(state: str | None) -> int | None:
    """Return a counter state as an int, or None when it has no value."""
    value = to_number(state)
    return None if value is None else int(value)


# Midea "Active State" values with no heating or cooling demand. DHW covers "DHW" and "DHW Heating".
NO_DEMAND = ("Idle", "Inactive", "DHW")
# Short pauses inside a heating cycle, which keep the target the machine had
PAUSES = ("Defrosting", "Oil return")


def target_flow_temp(
    state: str | None, curve_on: bool, fixed: str | None, curve: str | None, last: float | None
) -> float | None:
    """The water temperature the machine is aiming for, as the web wants it.

    0 when it is off, idle or heating DHW. The climate curve's value when the curve is on,
    the fixed setpoint otherwise. Unchanged during a defrost or oil return.
    """
    if state is None or state in ("unknown", "unavailable"):
        return None
    if state.startswith(NO_DEMAND):
        return 0.0
    if state in PAUSES:
        return last
    return to_number(curve if curve_on else fixed)


def build_payload(
    installation_id: int,
    local_datetime: str,
    states: dict[str, str | None],
    counters: dict[str, int | None],
) -> dict:
    """Return the JSON body for push.php.

    states holds the raw state of every mapped sensor, keyed by payload field.
    Unmapped fields are left out, as the web's own YAML does.
    A mapped energy field without a value raises MissingData, like the web's automation condition.
    """
    missing = [f for f in REQUIRED if f not in states]
    missing += [f for f in ENERGY if f in states and to_number(states[f]) is None]
    if missing:
        raise MissingData(missing)

    payload: dict = {
        "installation_id": installation_id,
        "energy_mode": "cumulative",
        "local_datetime": local_datetime,
    }
    payload.update({field: to_number(state) for field, state in states.items()})
    payload.update(counters)
    return payload
