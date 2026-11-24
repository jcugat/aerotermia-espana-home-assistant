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
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector as sel

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
    CONF_TARGET_MODE,
    COUNTER_INITIAL,
    CURVE_SWITCH,
    DEFROST_CYCLES,
    DEFROST_SOURCE,
    DOMAIN,
    ESPHOME_NAMES,
    INDOOR_TEMP,
    MODEL_MIDEA_ESPHOME,
    MODEL_OTHER,
    OUTDOOR_HUMIDITY,
    OUTDOOR_TEMP,
    PRODUCED,
    PRODUCED_ACS,
    PRODUCED_COOLING,
    PRODUCED_HEATING,
    TARGET_CURVE,
    TARGET_CUSTOM,
    TARGET_FIXED,
    TARGET_FLOW_TEMP,
    TARGET_NAMES,
    TARGET_NONE,
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
_TARGET_MODE = sel.SelectSelector(
    sel.SelectSelectorConfig(
        options=[TARGET_FIXED, TARGET_CURVE, TARGET_CUSTOM, TARGET_NONE],
        mode=sel.SelectSelectorMode.LIST,
        translation_key=CONF_TARGET_MODE,
    )
)
_MODEL = sel.SelectSelector(
    sel.SelectSelectorConfig(
        options=[MODEL_MIDEA_ESPHOME, MODEL_OTHER],
        mode=sel.SelectSelectorMode.LIST,
        translation_key=CONF_MODEL,
    )
)


def detect_entities(hass: HomeAssistant, device_id: str, names: dict = ESPHOME_NAMES) -> dict[str, str]:
    """Map each key to the device's entity with that firmware name."""
    entries = er.async_entries_for_device(er.async_get(hass), device_id)
    by_name = {(e.domain, (e.original_name or "").lower()): e.entity_id for e in entries}
    return {
        key: by_name[(domain, name.lower())]
        for key, (domain, name) in names.items()
        if (domain, name.lower()) in by_name
    }


def detect_target(hass: HomeAssistant, device_id: str) -> tuple[dict[str, str], str]:
    """The fixed and curve setpoint entities, and the mode the machine uses right now."""
    found = detect_entities(hass, device_id, TARGET_NAMES | {"switch": CURVE_SWITCH})
    switch = hass.states.get(found.pop("switch", ""))
    mode = TARGET_CURVE if switch and switch.state == "on" else TARGET_FIXED
    return found, mode if mode in found else TARGET_NONE


def target_mode_of(entity_id: str | None, targets: dict[str, str]) -> str:
    """The mode matching an entity chosen before modes existed (entries made with 1.0.0)."""
    if not entity_id:
        return TARGET_NONE
    return next((mode for mode, target in targets.items() if target == entity_id), TARGET_CUSTOM)


def apply_target(data: dict, targets: dict[str, str]) -> dict[str, str]:
    """Turn the chosen target mode into the entity to send, in place. Returns the form errors."""
    mode = data[CONF_TARGET_MODE]
    if mode == TARGET_CUSTOM:
        return {} if data.get(TARGET_FLOW_TEMP) else {TARGET_FLOW_TEMP: "target_flow_temp_missing"}
    data.pop(TARGET_FLOW_TEMP, None)
    if mode == TARGET_NONE:
        return {}
    if mode not in targets:
        return {CONF_TARGET_MODE: "target_not_found"}
    data[TARGET_FLOW_TEMP] = targets[mode]
    return {}


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
    mode = values[CONF_TARGET_MODE]
    schema[vol.Required(CONF_TARGET_MODE, default=mode)] = _TARGET_MODE
    # Always shown, as a form cannot hide it, but only used with the custom mode
    custom = values.get(TARGET_FLOW_TEMP) if mode == TARGET_CUSTOM else None
    schema[vol.Optional(TARGET_FLOW_TEMP, description={"suggested_value": custom} if custom else None)] = _TARGET
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
        self._targets: dict[str, str] = {}
        self._detected = 0

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
            device_id = user_input[CONF_DEVICE_ID]
            self._data[CONF_DEVICE_ID] = device_id
            found = detect_entities(self.hass, device_id)
            self._detected = len(found)
            self._targets, self._options[CONF_TARGET_MODE] = detect_target(self.hass, device_id)
            self._options |= found
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
        errors: dict[str, str] = {}
        values = self._options
        if user_input is not None:
            data = flatten(user_input)
            if not (errors := apply_target(data, self._targets)):
                return self._create(data)
            values = self._options | data

        return self.async_show_form(
            step_id="sensors",
            data_schema=sensors_schema(values),
            description_placeholders={"detected": str(self._detected)},
            errors=errors,
        )

    async def async_step_manual(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Other: pick every sensor by hand."""
        if user_input is not None:
            return self._create(flatten(user_input))

        return self.async_show_form(step_id="manual", data_schema=manual_schema(self._options))

    def _create(self, data: dict) -> ConfigFlowResult:
        options = {k: self._options[k] for k in (CONF_API_KEY, CONF_MINUTE)} | data
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
        errors: dict[str, str] = {}
        targets, _ = detect_target(self.hass, self._device_id())
        if user_input is not None:
            data = flatten(user_input)
            if not (errors := apply_target(data, targets)):
                return self.async_create_entry(data=data)
            values = data
        else:
            values = dict(self.config_entry.options)
            if CONF_TARGET_MODE not in values:
                values[CONF_TARGET_MODE] = target_mode_of(values.get(TARGET_FLOW_TEMP), targets)
            # Show each counter's current value, so raising it starts from what it holds now
            if pusher := getattr(self.config_entry, "runtime_data", None):
                values |= {COUNTER_INITIAL[k]: v for k, v in pusher.counters.items() if v is not None}
        return self.async_show_form(
            step_id="init", data_schema=sensors_schema(values, with_connection=True), errors=errors
        )

    def _device_id(self) -> str | None:
        """The ESPHome device. Entries made with 1.0.0 did not store it, so take it from the produced energy sensor."""
        if device_id := self.config_entry.data.get(CONF_DEVICE_ID):
            return device_id
        entity = er.async_get(self.hass).async_get(self.config_entry.options.get(PRODUCED, ""))
        return entity.device_id if entity else None

    async def async_step_manual(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=flatten(user_input))

        return self.async_show_form(
            step_id="manual",
            data_schema=manual_schema(dict(self.config_entry.options), with_connection=True),
        )
