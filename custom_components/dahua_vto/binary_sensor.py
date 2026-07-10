"""Binary sensors for the Dahua VTO integration (doorbell, motion, connectivity)."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from . import DahuaVtoDevice
from .const import (
    DAHUA_EVENT_CODE_MAP,
    DOMAIN,
    EVENT_DOORBELL,
    EVENT_MOTION,
    EVENT_TAMPER,
    SIGNAL_AVAILABILITY,
    SIGNAL_EVENT,
)
from .entity import build_device_info

# How long a momentary sensor (doorbell/motion) stays "on" after being triggered.
_PULSE_SECONDS = 5


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    device: DahuaVtoDevice = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            DahuaVtoConnectivitySensor(device, entry),
            DahuaVtoPulseSensor(
                device, entry, EVENT_DOORBELL, "Doorbell", BinarySensorDeviceClass.OCCUPANCY
            ),
            DahuaVtoPulseSensor(
                device, entry, EVENT_MOTION, "Motion", BinarySensorDeviceClass.MOTION
            ),
            DahuaVtoPulseSensor(
                device, entry, EVENT_TAMPER, "Tamper", BinarySensorDeviceClass.TAMPER
            ),
        ]
    )


def _device_info(entry: ConfigEntry, device: DahuaVtoDevice) -> DeviceInfo:
    return build_device_info(entry, device)


class DahuaVtoConnectivitySensor(BinarySensorEntity):
    """Reports whether the persistent DHIP connection is alive."""

    _attr_has_entity_name = True
    _attr_name = "Connectivity"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_should_poll = False

    def __init__(self, device: DahuaVtoDevice, entry: ConfigEntry) -> None:
        self._device = device
        self._attr_unique_id = f"{entry.entry_id}_connectivity"
        self._attr_device_info = _device_info(entry, device)
        self._entry = entry

    @property
    def is_on(self) -> bool:
        return self._device.available

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_AVAILABILITY}_{self._entry.entry_id}",
                self._handle_availability,
            )
        )

    @callback
    def _handle_availability(self, _available: bool) -> None:
        self.async_write_ha_state()


class DahuaVtoPulseSensor(BinarySensorEntity):
    """A binary sensor that pulses on for a few seconds when its event fires."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        device: DahuaVtoDevice,
        entry: ConfigEntry,
        event_type: str,
        name: str,
        device_class: BinarySensorDeviceClass,
    ) -> None:
        self._device = device
        self._entry = entry
        self._event_type = event_type
        self._attr_name = name
        self._attr_device_class = device_class
        self._attr_unique_id = f"{entry.entry_id}_{event_type}"
        self._attr_device_info = _device_info(entry, device)
        self._is_on = False
        self._unsub_timer = None

    @property
    def is_on(self) -> bool:
        return self._is_on

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
        action = event.get("Action")
        if DAHUA_EVENT_CODE_MAP.get(code) != self._event_type:
            return
        if action == "Stop":
            return
        self._is_on = True
        self.async_write_ha_state()
        if self._unsub_timer:
            self._unsub_timer()
        self._unsub_timer = async_call_later(
            self.hass, timedelta(seconds=_PULSE_SECONDS), self._reset
        )

    @callback
    def _reset(self, _now) -> None:
        self._is_on = False
        self._unsub_timer = None
        self.async_write_ha_state()
