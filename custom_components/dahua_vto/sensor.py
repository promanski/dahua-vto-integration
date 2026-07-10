"""Diagnostic sensors for the Dahua VTO integration."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DahuaVtoDevice
from .const import DAHUA_EVENT_CODE_MAP, DOMAIN, SIGNAL_EVENT
from .entity import build_device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    device: DahuaVtoDevice = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DahuaVtoLastEventSensor(device, entry)])


class DahuaVtoLastEventSensor(SensorEntity):
    """Shows the most recent normalized event received from the VTO."""

    _attr_has_entity_name = True
    _attr_name = "Last event"
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, device: DahuaVtoDevice, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_last_event"
        self._attr_device_info = build_device_info(entry, device)
        self._state = None
        self._attrs: dict = {}

    @property
    def native_value(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attrs

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_EVENT}_{self._entry.entry_id}",
                self._handle_event,
            )
        )

    @callback
    def _handle_event(self, event: dict) -> None:
        code = event.get("Code")
        self._state = DAHUA_EVENT_CODE_MAP.get(code, code)
        self._attrs = {
            "raw_code": code,
            "action": event.get("Action"),
            "index": event.get("Index"),
        }
        self.async_write_ha_state()
