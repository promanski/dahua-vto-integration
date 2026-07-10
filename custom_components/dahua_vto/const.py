"""Constants for the Dahua VTO Intercom integration."""
from __future__ import annotations

DOMAIN = "dahua_vto"

CONF_DOOR_CHANNELS = "door_channels"

DEFAULT_PORT = 5000
DEFAULT_DOOR_CHANNEL = 1
RECONNECT_INTERVAL = 10
KEEPALIVE_DEFAULT_INTERVAL = 60
COMMAND_TIMEOUT = 10

# Dahua "DHIP" binary/TCP protocol constants (reverse engineered, used by the
# official DMSS app, NVRs and the community). Every packet is prefixed by a
# fixed size header followed by a UTF-8 JSON payload.
DHIP_PROTO_MAGIC = 0x5049484400000020
DHIP_HEADER_FORMAT = "<QLLQQ"
DHIP_REALM_CHALLENGE_ERROR_CODE = 268632079

# Event codes exposed as Home Assistant events / device triggers.
EVENT_DOORBELL = "doorbell_press"
EVENT_CALL_NO_ANSWER = "call_no_answer"
EVENT_CALL_STATUS = "call_status"
EVENT_DOOR_OPENED = "door_opened"
EVENT_MOTION = "motion_detected"
EVENT_TAMPER = "tamper_alarm"
EVENT_UNRECOGNIZED = "unrecognized"

# Mapping between raw Dahua event "Code" values and the normalized events
# fired on the Home Assistant event bus / used as device automation triggers.
DAHUA_EVENT_CODE_MAP: dict[str, str] = {
    "_DoTalkAction_": EVENT_DOORBELL,
    "CallNoAnswered": EVENT_CALL_NO_ANSWER,
    "CallStatus": EVENT_CALL_STATUS,
    "AccessControl": EVENT_DOOR_OPENED,
    "VideoMotion": EVENT_MOTION,
    "VideoBlind": EVENT_TAMPER,
    "TakeSnapshot": "snapshot_taken",
}

SIGNAL_EVENT = f"{DOMAIN}_event"
SIGNAL_AVAILABILITY = f"{DOMAIN}_availability"

MANUFACTURER = "Dahua"
