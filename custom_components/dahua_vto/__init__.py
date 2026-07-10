"""The Dahua VTO Intercom integration."""
from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .client import DahuaAuthError, DahuaVtoClient, DahuaVtoError
from .const import (
    CONF_DOOR_CHANNELS,
    DAHUA_EVENT_CODE_MAP,
    DOMAIN,
    RECONNECT_INTERVAL,
    SIGNAL_AVAILABILITY,
    SIGNAL_EVENT,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]


class DahuaVtoDevice:
    """Owns the connection to a single Dahua VTO unit for a config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.available = False
        self.door_channels: list[int] = entry.options.get(
            CONF_DOOR_CHANNELS, entry.data.get(CONF_DOOR_CHANNELS, [1])
        )
        self.client = DahuaVtoClient(
            entry.data[CONF_HOST],
            entry.data.get(CONF_PORT, 5000),
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            event_callback=self._on_event,
            availability_callback=self._on_availability,
        )
        self._reconnect_task = None

    async def async_connect(self) -> None:
        await self.client.connect()
        self.available = True

    async def async_shutdown(self) -> None:
        if self._reconnect_task:
            self._reconnect_task.cancel()
        await self.client.disconnect()

    def _on_event(self, event: dict) -> None:
        async_dispatcher_send(self.hass, f"{SIGNAL_EVENT}_{self.entry.entry_id}", event)

        normalized_type = DAHUA_EVENT_CODE_MAP.get(event.get("Code"))
        if normalized_type is None or event.get("Action") == "Stop":
            return
        registry = dr.async_get(self.hass)
        device_entry = registry.async_get_device(
            identifiers={(DOMAIN, self.entry.unique_id or self.entry.entry_id)}
        )
        self.hass.bus.async_fire(
            DOMAIN,
            {
                "device_id": device_entry.id if device_entry else None,
                "type": normalized_type,
                "raw_code": event.get("Code"),
            },
        )

    def _on_availability(self, available: bool) -> None:
        self.available = available
        async_dispatcher_send(
            self.hass, f"{SIGNAL_AVAILABILITY}_{self.entry.entry_id}", available
        )
        if not available:
            self._reconnect_task = self.hass.loop.create_task(self._reconnect())

    async def _reconnect(self) -> None:
        while not self.available:
            await asyncio.sleep(RECONNECT_INTERVAL)
            try:
                await self.async_connect()
                _LOGGER.info("Reconnected to Dahua VTO %s", self.entry.data[CONF_HOST])
            except DahuaVtoError as err:
                _LOGGER.debug("Reconnect attempt failed: %s", err)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Dahua VTO from a config entry."""
    device = DahuaVtoDevice(hass, entry)

    try:
        await device.async_connect()
    except DahuaAuthError as err:
        raise ConfigEntryNotReady(f"Authentication failed: {err}") from err
    except DahuaVtoError as err:
        raise ConfigEntryNotReady(f"Cannot connect to {entry.data[CONF_HOST]}: {err}") from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = device

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        device: DahuaVtoDevice = hass.data[DOMAIN].pop(entry.entry_id)
        await device.async_shutdown()
    return unload_ok
