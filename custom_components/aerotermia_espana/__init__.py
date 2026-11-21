"""Aerotermia España: hourly push of heat pump data to aerotermiaespana.sytes.net."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import (
    CONF_INSTALLATION_ID,
    CONF_MINUTE,
    CONF_MODEL,
    COUNTER_SOURCES,
    DASHBOARD_URL,
    DOMAIN,
    MODEL_OTHER,
    PUSH_URL,
    SENSOR_FIELDS,
    SIGNAL_STATUS,
)
from .payload import MissingData, build_payload, to_count

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.BUTTON, Platform.SENSOR]


class Pusher:
    """Builds and sends the payload for one installation."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.installation_id: int = entry.data[CONF_INSTALLATION_ID]
        self.counters: dict[str, int | None] = {}  # filled by the counter sensors
        self.status: str | None = None
        self.attributes: dict = {}
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, str(self.installation_id))},
            name=f"Aerotermia España #{self.installation_id}",
            manufacturer="Aerotermia España",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=DASHBOARD_URL.format(self.installation_id),
        )

    def _states(self) -> dict[str, str | None]:
        options = self.entry.options
        states = {}
        for field in SENSOR_FIELDS:
            if entity_id := options.get(field):
                state = self.hass.states.get(entity_id)
                states[field] = state.state if state else None
        return states

    def _counters(self) -> dict[str, int | None]:
        options = self.entry.options
        if self.entry.data[CONF_MODEL] != MODEL_OTHER:
            return dict(self.counters)
        # "Other": the user picked entities that already hold the totals
        counters = {}
        for field in COUNTER_SOURCES:
            if entity_id := options.get(field):
                state = self.hass.states.get(entity_id)
                counters[field] = to_count(state.state if state else None)
        return counters

    async def push(self, delay: int = 0) -> None:
        """Send one payload, after an optional delay (the web requires a random one)."""
        await asyncio.sleep(delay)
        attempt = dt_util.now()
        try:
            body = build_payload(
                self.installation_id,
                attempt.strftime("%Y-%m-%d %H:%M:%S"),
                self._states(),
                self._counters(),
            )
        except MissingData as err:
            _LOGGER.warning("Push skipped, no value for: %s", err)
            self._set_status("skipped", attempt, missing=err.fields)
            return

        session = async_get_clientsession(self.hass)
        try:
            async with session.post(
                PUSH_URL,
                json=body,
                headers={"Authorization": f"Bearer {self.entry.options[CONF_API_KEY]}"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                text = (await resp.text())[:500]
                http_status = resp.status
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.warning("Push failed: %s", err)
            self._set_status("error", attempt, response=str(err))
            return

        if http_status == 200:
            status = "ok"
        elif http_status == 429:
            status = "rate_limited"
        elif http_status in (401, 403):
            status = "auth_error"
        else:
            status = "error"
        if status != "ok":
            _LOGGER.warning("Push returned HTTP %s: %s", http_status, text)
        self._set_status(status, attempt, http_status=http_status, response=text, payload=body)

    def _set_status(self, status: str, attempt: datetime, **attributes) -> None:
        self.status = status
        self.attributes = {"last_attempt": attempt.isoformat(), **attributes}
        async_dispatcher_send(self.hass, SIGNAL_STATUS.format(self.entry.entry_id))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one installation."""
    pusher = Pusher(hass, entry)
    entry.runtime_data = pusher
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    @callback
    def _scheduled(_now: datetime) -> None:
        # The web demands the assigned minute plus a random 1-59 s delay, to spread the load
        entry.async_create_background_task(
            hass, pusher.push(random.randint(1, 59)), f"{DOMAIN}_push_{pusher.installation_id}"
        )

    entry.async_on_unload(
        async_track_time_change(hass, _scheduled, minute=entry.options[CONF_MINUTE], second=0)
    )
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload one installation."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
