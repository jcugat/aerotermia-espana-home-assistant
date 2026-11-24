"""Config flow: connection, heat pump type, then the sensors (found on the ESPHome device or picked by hand).

The options flow reopens the sensors form of the type chosen at setup, which cannot be changed.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector as sel

from . import detect_entities
from .const import (
    COMPRESSOR_HOURS,
    COMPRESSOR_SOURCE,
    COMPRESSOR_STARTS,
    CONF_DEVICE_ID,
    CONF_INSTALLATION_ID,
    CONF_MINUTE,
    CONF_MODEL,
    CONSUMED,
    CONSUMED_ACS,
    CONSUMED_COOLING,
    CONSUMED_HEATING,
    COUNTER_INITIAL,
    DEFROST_CYCLES,
    DEFROST_SOURCE,
    DOMAIN,
    INDOOR_TEMP,
    MODEL_MIDEA_ESPHOME,
    MODEL_OTHER,
    OUTDOOR_HUMIDITY,
    OUTDOOR_TEMP,
    PRODUCED,
    PRODUCED_ACS,
    PRODUCED_COOLING,
    PRODUCED_HEATING,
    TARGET_FLOW_TEMP,
)

ADVANCED = "advanced"
BREAKDOWN = "breakdown"
CONNECTION = "connection"
REQUIRED = {CONSUMED, PRODUCED, CONF_API_KEY}


def _entity(domain: str | list[str], **device_class: str) -> sel.EntitySelector:
    # Passing device_class=None would become an empty list, which the frontend reads as "matches nothing"
    return sel.EntitySelector(sel.EntitySelectorConfig(domain=domain, **device_class))


_ENERGY = _entity("sensor", device_class="energy")
# Lifetime totals: a sensor or a Counter helper raised by an automation, never a hand-set number
_TOTAL = _entity(["sensor", "counter"])

_TEMPERATURE = _entity("sensor", device_class="temperature")
# The target can be a number entity too, such as the Midea firmware's own setpoint
_TARGET = _entity(["sensor", "number"], device_class="temperature")

# Every block follows the order of the web's sensor form (panel step 2).
# Midea, top: the fields users commonly replace (Shelly meter, own thermometer, humidity the machine lacks)
BASIC_FIELDS = {
    CONSUMED: _ENERGY,
    OUTDOOR_TEMP: _TEMPERATURE,
    INDOOR_TEMP: _TEMPERATURE,
    OUTDOOR_HUMIDITY: _entity("sensor", device_class="humidity"),
}
# Midea, folded: detected from the machine, rarely changed
ADVANCED_FIELDS = {
    PRODUCED: _ENERGY,
    CONSUMED_HEATING: _ENERGY,
    PRODUCED_HEATING: _ENERGY,
    CONSUMED_COOLING: _ENERGY,
    PRODUCED_COOLING: _ENERGY,
    CONSUMED_ACS: _ENERGY,
    PRODUCED_ACS: _ENERGY,
    COMPRESSOR_HOURS: _TOTAL,
    DEFROST_SOURCE: _entity("binary_sensor"),
    COMPRESSOR_SOURCE: _entity("binary_sensor"),
}
# "Other": everything by hand, with the per-service breakdown in its own section as on the web
MANUAL_HEAD = {CONSUMED: _ENERGY, PRODUCED: _ENERGY}
BREAKDOWN_FIELDS = {
    CONSUMED_HEATING: _ENERGY,
    PRODUCED_HEATING: _ENERGY,
    CONSUMED_COOLING: _ENERGY,
    PRODUCED_COOLING: _ENERGY,
    CONSUMED_ACS: _ENERGY,
    PRODUCED_ACS: _ENERGY,
}
MANUAL_TAIL = {
    COMPRESSOR_HOURS: _TOTAL,
    OUTDOOR_TEMP: _TEMPERATURE,
    INDOOR_TEMP: _TEMPERATURE,
    OUTDOOR_HUMIDITY: _entity("sensor", device_class="humidity"),
    DEFROST_CYCLES: _TOTAL,
    COMPRESSOR_STARTS: _TOTAL,
    TARGET_FLOW_TEMP: _TARGET,
}
_COUNT = sel.NumberSelector(sel.NumberSelectorConfig(min=0, mode=sel.NumberSelectorMode.BOX))
_MINUTE = sel.NumberSelector(sel.NumberSelectorConfig(min=0, max=59, mode=sel.NumberSelectorMode.BOX))
_PASSWORD = sel.TextSelector(sel.TextSelectorConfig(type=sel.TextSelectorType.PASSWORD))
_MODEL = sel.SelectSelector(
    sel.SelectSelectorConfig(
        options=[MODEL_MIDEA_ESPHOME, MODEL_OTHER],
        mode=sel.SelectSelectorMode.LIST,
        translation_key=CONF_MODEL,
    )
)


def _fields(selectors: dict, values: dict) -> dict:
    out = {}
    for key, selector in selectors.items():
        marker = vol.Required if key in REQUIRED else vol.Optional
        description = {"suggested_value": values[key]} if values.get(key) is not None else None
        out[marker(key, description=description)] = selector
    return out


def _connection(values: dict) -> dict:
    out = _fields({CONF_API_KEY: _PASSWORD}, values)
    out[vol.Required(CONF_MINUTE, default=values[CONF_MINUTE])] = _MINUTE
    return out


def sensors_schema(values: dict, with_connection: bool = False) -> vol.Schema:
    """Midea: basic fields on top, the rest in a section that starts folded when it is complete."""
    advanced = _fields(ADVANCED_FIELDS, values)
    advanced |= _fields(dict.fromkeys(COUNTER_INITIAL.values(), _COUNT), values)
    if with_connection:
        advanced |= _connection(values)
    schema = _fields(BASIC_FIELDS, values)
    schema[vol.Required(ADVANCED)] = section(
        vol.Schema(advanced), {"collapsed": bool(values.get(PRODUCED))}
    )
    return vol.Schema(schema)


def manual_schema(values: dict, with_connection: bool = False) -> vol.Schema:
    """Other: every field by hand, the breakdown folded until used, the connection folded at the end."""
    schema = _fields(MANUAL_HEAD, values)
    schema[vol.Required(BREAKDOWN)] = section(
        vol.Schema(_fields(BREAKDOWN_FIELDS, values)),
        {"collapsed": not any(values.get(k) for k in BREAKDOWN_FIELDS)},
    )
    schema |= _fields(MANUAL_TAIL, values)
    if with_connection:
        schema[vol.Required(CONNECTION)] = section(vol.Schema(_connection(values)), {"collapsed": True})
    return vol.Schema(schema)


def flatten(user_input: dict) -> dict:
    data = dict(user_input)
    for key in (ADVANCED, BREAKDOWN, CONNECTION):
        data |= data.pop(key, {})
    for key in (CONF_MINUTE, *COUNTER_INITIAL.values()):
        if data.get(key) is not None:
            data[key] = int(data[key])
    return data


class AerotermiaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up one machine registered on the web."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._options: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        """API key, machine id and minute, all copied from the web panel."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Optional in the schema so the frontend leaves them empty, but both must be typed in.
            errors = {
                key: f"{key}_missing"
                for key in (CONF_INSTALLATION_ID, CONF_MINUTE)
                if user_input.get(key) is None
            }
            if not errors:
                installation_id = int(user_input[CONF_INSTALLATION_ID])
                await self.async_set_unique_id(str(installation_id))
                self._abort_if_unique_id_configured()
                self._data = {CONF_INSTALLATION_ID: installation_id}
                self._options = {
                    CONF_API_KEY: user_input[CONF_API_KEY].strip(),
                    CONF_MINUTE: int(user_input[CONF_MINUTE]),
                }
                return await self.async_step_model()

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): _PASSWORD,
                vol.Optional(CONF_INSTALLATION_ID): sel.NumberSelector(
                    sel.NumberSelectorConfig(min=1, mode=sel.NumberSelectorMode.BOX)
                ),
                vol.Optional(CONF_MINUTE): _MINUTE,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or {}),
            errors=errors,
        )

    async def async_step_model(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Which heat pump, which decides how its sensors are found."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not (model := user_input.get(CONF_MODEL)):
                errors[CONF_MODEL] = "model_missing"
            else:
                self._data[CONF_MODEL] = model
                if model == MODEL_OTHER:
                    return await self.async_step_manual()
                return await self.async_step_device()

        # Optional so the frontend leaves every option unticked, but one must be chosen.
        return self.async_show_form(
            step_id="model",
            data_schema=vol.Schema({vol.Optional(CONF_MODEL): _MODEL}),
            errors=errors,
        )

    async def async_step_device(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Pick the ESPHome heat pump so its sensors are found automatically."""
        if user_input is not None:
            # Kept so the target flow temperature sensor can find the machine's entities
            self._data[CONF_DEVICE_ID] = user_input[CONF_DEVICE_ID]
            self._options |= detect_entities(self.hass, user_input[CONF_DEVICE_ID])
            return await self.async_step_sensors()

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): sel.DeviceSelector(
                        sel.DeviceSelectorConfig(integration="esphome")
                    )
                }
            ),
        )

    async def async_step_sensors(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Midea: review and adjust the detected sensors."""
        if user_input is not None:
            return self._create(user_input)

        return self.async_show_form(
            step_id="sensors",
            data_schema=sensors_schema(self._options),
            description_placeholders={"detected": str(len(self._options) - 2)},
        )

    async def async_step_manual(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Other: pick every sensor by hand."""
        if user_input is not None:
            return self._create(user_input)

        return self.async_show_form(step_id="manual", data_schema=manual_schema(self._options))

    def _create(self, user_input: dict) -> ConfigFlowResult:
        options = {k: self._options[k] for k in (CONF_API_KEY, CONF_MINUTE)} | flatten(user_input)
        return self.async_create_entry(
            title=f"Aerotermia España #{self._data[CONF_INSTALLATION_ID]}",
            data=self._data,
            options=options,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return AerotermiaOptionsFlow()


class AerotermiaOptionsFlow(OptionsFlow):
    """The 'Configure' button: the sensors form of the entry's type, prefilled with the current choice."""

    async def async_step_init(self, user_input: dict | None = None) -> ConfigFlowResult:
        if self.config_entry.data[CONF_MODEL] == MODEL_OTHER:
            return await self.async_step_manual()
        if user_input is not None:
            return self.async_create_entry(data=flatten(user_input))

        values = dict(self.config_entry.options)
        # Show each counter's current value, so raising it starts from what it holds now
        if pusher := getattr(self.config_entry, "runtime_data", None):
            values |= {COUNTER_INITIAL[k]: v for k, v in pusher.counters.items() if v is not None}
        return self.async_show_form(
            step_id="init", data_schema=sensors_schema(values, with_connection=True)
        )

    async def async_step_manual(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=flatten(user_input))

        return self.async_show_form(
            step_id="manual",
            data_schema=manual_schema(dict(self.config_entry.options), with_connection=True),
        )
