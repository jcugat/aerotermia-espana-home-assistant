"""Counter sensors for defrosts and compressor starts, and the push status sensor."""

from __future__ import annotations

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_state_change_event

from . import Pusher
from .const import COMPRESSOR_STARTS, COUNTER_SOURCES, DEFROST_CYCLES, SIGNAL_STATUS

COUNTERS = {
    DEFROST_CYCLES: ("Defrost Cycles Total", "defrost_cycles_total", "mdi:snowflake-melt"),
    COMPRESSOR_STARTS: ("Compressor Starts Total", "compressor_starts_total", "mdi:counter"),
}
STATUSES = ["ok", "skipped", "rate_limited", "auth_error", "error"]


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    pusher: Pusher = entry.runtime_data
    entities: list[SensorEntity] = [PushStatusSensor(pusher)]
    for field, source_key in COUNTER_SOURCES.items():
        if source := entry.options.get(source_key):
            entities.append(CounterSensor(pusher, field, source))
    async_add_entities(entities)


class CounterSensor(RestoreSensor):
    """Lifetime count of off->on transitions of a binary sensor. Never resets."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_value = 0

    def __init__(self, pusher: Pusher, field: str, source: str) -> None:
        name, slug, icon = COUNTERS[field]
        self._pusher = pusher
        self._field = field
        self._source = source
        self._attr_name = name
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


class PushStatusSensor(SensorEntity):
    """Result of the last push, with the request and response as attributes."""

    _attr_has_entity_name = True
    _attr_name = "Push Status"
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
