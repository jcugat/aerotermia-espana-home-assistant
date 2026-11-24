"""Counter sensors for defrosts and compressor starts, and the push status sensor."""

from __future__ import annotations

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_state_change_event

from . import Pusher, detect_entities, device_of
from .const import (
    COMPRESSOR_STARTS,
    COUNTER_INITIAL,
    COUNTER_SOURCES,
    DEFROST_CYCLES,
    SIGNAL_STATUS,
    TARGET_SOURCES,
)
from .payload import target_flow_temp

# The slug is the translation key and the entity_id suffix
COUNTERS = {
    DEFROST_CYCLES: ("defrost_cycles_total", "mdi:snowflake-melt"),
    COMPRESSOR_STARTS: ("compressor_starts_total", "mdi:counter"),
}
STATUSES = ["ok", "skipped", "rate_limited", "auth_error", "error"]


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    pusher: Pusher = entry.runtime_data
    entities: list[SensorEntity] = [PushStatusSensor(pusher)]
    for field, source_key in COUNTER_SOURCES.items():
        if source := entry.options.get(source_key):
            entities.append(CounterSensor(pusher, field, source))
    if pusher.midea:
        sources = detect_entities(hass, device_of(hass, entry), TARGET_SOURCES)
        # Needs the machine's state and at least one setpoint to work anything out
        if "state" in sources and ({"fixed", "curve"} & sources.keys()):
            entities.append(TargetFlowTempSensor(pusher, sources))
    async_add_entities(entities)


class CounterSensor(RestoreSensor):
    """Lifetime count of off->on transitions of a binary sensor. Never resets."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_value = 0

    def __init__(self, pusher: Pusher, field: str, source: str) -> None:
        slug, icon = COUNTERS[field]
        self._pusher = pusher
        self._field = field
        self._source = source
        self._attr_translation_key = slug
        self._attr_icon = icon
        self._attr_unique_id = f"{pusher.installation_id}_{slug}"
        self._attr_device_info = pusher.device_info
        # Fixed id so several machines never collide: sensor.aerotermia_24_defrost_cycles_total
        self.entity_id = f"sensor.aerotermia_{pusher.installation_id}_{slug}"
        self._attr_extra_state_attributes = {"source": source}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) and last.native_value is not None:
            self._attr_native_value = int(last.native_value)
        # The user's floor only raises the count, so it can never go down on the web
        floor = self._pusher.entry.options.get(COUNTER_INITIAL[self._field], 0)
        self._attr_native_value = max(self._attr_native_value, floor)
        self._pusher.counters[self._field] = self._attr_native_value
        self.async_on_remove(
            async_track_state_change_event(self.hass, self._source, self._on_source_change)
        )

    @callback
    def _on_source_change(self, event: Event[EventStateChangedData]) -> None:
        old, new = event.data["old_state"], event.data["new_state"]
        # Only off->on counts, so an ESPHome reconnect (unavailable->on) is not a start
        if old is None or new is None or old.state != "off" or new.state != "on":
            return
        self._attr_native_value += 1
        self._pusher.counters[self._field] = self._attr_native_value
        self.async_write_ha_state()


class TargetFlowTempSensor(SensorEntity):
    """Midea: the flow temperature the machine aims for, worked out as the web expects it."""

    _attr_has_entity_name = True
    _attr_translation_key = "target_flow_temp"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, pusher: Pusher, sources: dict[str, str]) -> None:
        self._pusher = pusher
        self._sources = sources
        self._attr_unique_id = f"{pusher.installation_id}_target_flow_temp"
        self._attr_device_info = pusher.device_info
        self.entity_id = f"sensor.aerotermia_{pusher.installation_id}_target_flow_temp"
        self._attr_extra_state_attributes = {"sources": sources}

    async def async_added_to_hass(self) -> None:
        self._pusher.has_target = True
        self._update()
        self.async_on_remove(
            async_track_state_change_event(self.hass, list(self._sources.values()), self._on_change)
        )

    async def async_will_remove_from_hass(self) -> None:
        self._pusher.has_target = False

    def _state(self, key: str) -> str | None:
        state = self.hass.states.get(self._sources.get(key, ""))
        return state.state if state else None

    def _update(self) -> None:
        value = target_flow_temp(
            self._state("state"),
            self._state("curve_switch") == "on",
            self._state("fixed"),
            self._state("curve"),
            self._attr_native_value,
        )
        self._attr_native_value = value
        self._pusher.target = value

    @callback
    def _on_change(self, _event: Event[EventStateChangedData]) -> None:
        self._update()
        self.async_write_ha_state()


class PushStatusSensor(SensorEntity):
    """Result of the last push, with the request and response as attributes."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:cloud-upload-outline"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUSES
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "push_status"

    def __init__(self, pusher: Pusher) -> None:
        self._pusher = pusher
        self._attr_unique_id = f"{pusher.installation_id}_push_status"
        self._attr_device_info = pusher.device_info
        self.entity_id = f"sensor.aerotermia_{pusher.installation_id}_push_status"

    @property
    def native_value(self) -> str | None:
        return self._pusher.status

    @property
    def extra_state_attributes(self) -> dict:
        return self._pusher.attributes

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_STATUS.format(self._pusher.entry.entry_id),
                self.async_write_ha_state,
            )
        )
