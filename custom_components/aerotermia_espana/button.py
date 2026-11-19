"""Button to push right away, for testing with the web's debug mode."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory

from . import Pusher


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([PushNowButton(entry.runtime_data)])


class PushNowButton(ButtonEntity):
    """Push now. Outside the web's debug mode the server answers 429."""

    _attr_has_entity_name = True
    _attr_name = "Push Now"
    _attr_icon = "mdi:cloud-upload"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, pusher: Pusher) -> None:
        self._pusher = pusher
        self._attr_unique_id = f"{pusher.installation_id}_push_now"
        self._attr_device_info = pusher.device_info
        self.entity_id = f"button.aerotermia_{pusher.installation_id}_push_now"

    async def async_press(self) -> None:
        await self._pusher.push()
