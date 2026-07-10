"""Device automation triggers for the Dahua VTO integration.

Exposes doorbell press, motion, tamper and call events as native device
triggers so they can be used directly in the Home Assistant automation
editor without needing to know the underlying event bus payloads.
"""
from __future__ import annotations

import voluptuous as vol
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo

from .const import (
    DOMAIN,
    EVENT_CALL_NO_ANSWER,
    EVENT_CALL_STATUS,
    EVENT_DOOR_OPENED,
    EVENT_DOORBELL,
    EVENT_MOTION,
    EVENT_TAMPER,
)

TRIGGER_TYPES = {
    EVENT_DOORBELL,
    EVENT_MOTION,
    EVENT_TAMPER,
    EVENT_CALL_NO_ANSWER,
    EVENT_CALL_STATUS,
    EVENT_DOOR_OPENED,
}

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES)}
)


async def async_get_triggers(hass: HomeAssistant, device_id: str) -> list[dict]:
    registry = dr.async_get(hass)
    device = registry.async_get(device_id)
    if device is None:
        return []
    return [
        {
            CONF_PLATFORM: "device",
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: trigger_type,
        }
        for trigger_type in TRIGGER_TYPES
    ]


async def async_attach_trigger(
    hass: HomeAssistant,
    config: dict,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    event_config = event_trigger.TRIGGER_SCHEMA(
        {
            event_trigger.CONF_PLATFORM: "event",
            event_trigger.CONF_EVENT_TYPE: DOMAIN,
            event_trigger.CONF_EVENT_DATA: {
                "device_id": config[CONF_DEVICE_ID],
                "type": config[CONF_TYPE],
            },
        }
    )
    return await event_trigger.async_attach_trigger(
        hass, event_config, action, trigger_info, platform_type="device"
    )
