"""Button entities that trigger the door relay(s) of the Dahua VTO."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.components.button import ButtonEntity, ButtonDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DahuaVtoDevice
from .client import DahuaVtoError
from .const import DOMAIN
from .entity import build_device_info

_LOGGER = logging.getLogger(__name__)

SERVICE_OPEN_DOOR = "open_door"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    device: DahuaVtoDevice = hass.data[DOMAIN][entry.entry_id]
    entities = [
        DahuaOpenDoorButton(device, entry, channel) for channel in device.door_channels
    ]
    async_add_entities(entities)

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_OPEN_DOOR,
        {vol.Optional("short_number", default="HA"): cv.string},
        "async_press_with_short_number",
    )


class DahuaOpenDoorButton(ButtonEntity):
    """Momentarily unlocks a door relay channel on the VTO."""

    _attr_has_entity_name = True
    _attr_device_class = ButtonDeviceClass.RESTART

    def __init__(self, device: DahuaVtoDevice, entry: ConfigEntry, channel: int) -> None:
        self._device = device
        self._channel = channel
        self._attr_name = (
            "Open door" if len(device.door_channels) == 1 else f"Open door {channel}"
        )
        self._attr_unique_id = f"{entry.entry_id}_open_door_{channel}"
        self._attr_device_info = build_device_info(entry, device)

    async def async_press(self) -> None:
        await self.async_press_with_short_number()

    async def async_press_with_short_number(self, short_number: str = "HA") -> None:
        try:
            # The device expects a zero-based channel index.
            await self._device.client.open_door(
                channel=self._channel - 1, short_number=short_number
            )
        except DahuaVtoError as err:
            raise HomeAssistantError(f"Unable to open door: {err}") from err
