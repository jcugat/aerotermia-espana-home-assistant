"""Config flow: connection, ESPHome device, then the sensor mapping. The options flow reopens the mapping."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector as sel

from .const import (
    COMPRESSOR_HOURS,
    COMPRESSOR_SOURCE,
    CONF_DEVICE_ID,
    CONF_INSTALLATION_ID,
    CONF_MINUTE,
    CONSUMED,
    CONSUMED_ACS,
    CONSUMED_COOLING,
    CONSUMED_HEATING,
    DEFROST_SOURCE,
    DOMAIN,
    ESPHOME_NAMES,
    INDOOR_TEMP,
    OUTDOOR_HUMIDITY,
    OUTDOOR_TEMP,
    PRODUCED,
    PRODUCED_ACS,
    PRODUCED_COOLING,
    PRODUCED_HEATING,
)

ADVANCED = "advanced"
REQUIRED = {CONSUMED, PRODUCED, CONF_API_KEY}


def _entity(domain: str, device_class: str | None = None) -> sel.EntitySelector:
    return sel.EntitySelector(sel.EntitySelectorConfig(domain=domain, device_class=device_class))


_ENERGY = _entity("sensor", "energy")

# Fields users commonly replace (Shelly meter, own thermometer, humidity the machine lacks)
BASIC_FIELDS = {
    CONSUMED: _ENERGY,
    OUTDOOR_TEMP: _entity("sensor", "temperature"),
    INDOOR_TEMP: _entity("sensor", "temperature"),
    OUTDOOR_HUMIDITY: _entity("sensor", "humidity"),
}
# Detected from the machine, rarely changed
ADVANCED_FIELDS = {
    PRODUCED: _ENERGY,
    CONSUMED_HEATING: _ENERGY,
    PRODUCED_HEATING: _ENERGY,
    CONSUMED_ACS: _ENERGY,
    PRODUCED_ACS: _ENERGY,
    CONSUMED_COOLING: _ENERGY,
    PRODUCED_COOLING: _ENERGY,
    COMPRESSOR_HOURS: _entity("sensor"),
    DEFROST_SOURCE: _entity("binary_sensor"),
    COMPRESSOR_SOURCE: _entity("binary_sensor"),
}
_MINUTE = sel.NumberSelector(sel.NumberSelectorConfig(min=0, max=59, mode=sel.NumberSelectorMode.BOX))
_PASSWORD = sel.TextSelector(sel.TextSelectorConfig(type=sel.TextSelectorType.PASSWORD))


def detect_entities(hass: HomeAssistant, device_id: str) -> dict[str, str]:
    """Map payload fields to the device's entities by their firmware name."""
    entries = er.async_entries_for_device(er.async_get(hass), device_id)
    by_name = {(e.domain, (e.original_name or "").lower()): e.entity_id for e in entries}
    return {
        field: by_name[(domain, name.lower())]
        for field, (domain, name) in ESPHOME_NAMES.items()
        if (domain, name.lower()) in by_name
    }


def _fields(selectors: dict, values: dict) -> dict:
    out = {}
    for key, selector in selectors.items():
        marker = vol.Required if key in REQUIRED else vol.Optional
        description = {"suggested_value": values[key]} if values.get(key) is not None else None
        out[marker(key, description=description)] = selector
    return out


def sensors_schema(values: dict, with_connection: bool = False) -> vol.Schema:
    """Basic fields on top, the rest in a section that starts folded when it is complete."""
    advanced = _fields(ADVANCED_FIELDS, values)
    if with_connection:
        advanced |= _fields({CONF_API_KEY: _PASSWORD}, values)
        advanced[vol.Required(CONF_MINUTE, default=values[CONF_MINUTE])] = _MINUTE
    schema = _fields(BASIC_FIELDS, values)
    schema[vol.Required(ADVANCED)] = section(
        vol.Schema(advanced), {"collapsed": bool(values.get(PRODUCED))}
    )
    return vol.Schema(schema)


def flatten(user_input: dict) -> dict:
    data = dict(user_input)
    data |= data.pop(ADVANCED, {})
    if CONF_MINUTE in data:
        data[CONF_MINUTE] = int(data[CONF_MINUTE])
    return data


class AerotermiaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up one machine registered on the web."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._options: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        """API key, machine id and minute, all copied from the web panel."""
        if user_input is not None:
            installation_id = int(user_input[CONF_INSTALLATION_ID])
            await self.async_set_unique_id(str(installation_id))
            self._abort_if_unique_id_configured()
            self._data = {CONF_INSTALLATION_ID: installation_id}
            self._options = {
                CONF_API_KEY: user_input[CONF_API_KEY].strip(),
                CONF_MINUTE: int(user_input[CONF_MINUTE]),
            }
            return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): _PASSWORD,
                    vol.Required(CONF_INSTALLATION_ID): sel.NumberSelector(
                        sel.NumberSelectorConfig(min=1, mode=sel.NumberSelectorMode.BOX)
                    ),
                    vol.Required(CONF_MINUTE): _MINUTE,
                }
            ),
        )

    async def async_step_device(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Pick the ESPHome heat pump so its sensors are found automatically."""
        if user_input is not None:
            if device_id := user_input.get(CONF_DEVICE_ID):
                self._options |= detect_entities(self.hass, device_id)
            return await self.async_step_sensors()

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_DEVICE_ID): sel.DeviceSelector(
                        sel.DeviceSelectorConfig(integration="esphome")
                    )
                }
            ),
        )

    async def async_step_sensors(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Review and adjust the detected sensors."""
        if user_input is not None:
            options = {k: self._options[k] for k in (CONF_API_KEY, CONF_MINUTE)} | flatten(user_input)
            return self.async_create_entry(
                title=f"Aerotermia España #{self._data[CONF_INSTALLATION_ID]}",
                data=self._data,
                options=options,
            )

        return self.async_show_form(
            step_id="sensors",
            data_schema=sensors_schema(self._options),
            description_placeholders={"detected": str(len(self._options) - 2)},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return AerotermiaOptionsFlow()


class AerotermiaOptionsFlow(OptionsFlow):
    """The 'Configure' button: same sensor form, prefilled with the current choice."""

    async def async_step_init(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=flatten(user_input))

        return self.async_show_form(
            step_id="init",
            data_schema=sensors_schema(dict(self.config_entry.options), with_connection=True),
        )
