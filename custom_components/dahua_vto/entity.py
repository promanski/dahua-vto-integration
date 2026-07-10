"""Shared entity helpers for the Dahua VTO integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, MANUFACTURER


def build_device_info(entry: ConfigEntry, device) -> DeviceInfo:
    """Build the DeviceInfo shared by all entities of a config entry."""
    info = device.client.device_info or {}
    return DeviceInfo(
        identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
        manufacturer=MANUFACTURER,
        model=info.get("deviceType", "VTO"),
        name=entry.title,
        serial_number=info.get("serialNumber"),
        configuration_url=f"http://{entry.data[CONF_HOST]}",
    )
