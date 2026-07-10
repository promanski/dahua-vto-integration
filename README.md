# 🔔 Dahua VTO Intercom for Home Assistant

[![Validate](https://github.com/adaniluk/dahua-vto-integration/actions/workflows/validate.yml/badge.svg)](https://github.com/adaniluk/dahua-vto-integration/actions/workflows/validate.yml)
[![Tests](https://github.com/adaniluk/dahua-vto-integration/actions/workflows/test.yml/badge.svg)](https://github.com/adaniluk/dahua-vto-integration/actions/workflows/test.yml)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/v/release/adaniluk/dahua-vto-integration?include_prereleases)](https://github.com/adaniluk/dahua-vto-integration/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.6%2B-41BDF5?logo=home-assistant&logoColor=white)](https://www.home-assistant.io/)

Turn your **Dahua VTO** door station (and OEM/rebranded clones such as
Dahua‑based Amcrest, Vaultech, Optex, etc.) into a first‑class Home
Assistant citizen — no MQTT bridge, no extra add‑on, no cloud. This
integration talks **directly** to the door station over the local network
using the same binary DHIP protocol used by Dahua's own DMSS mobile app.

Ring the bell, get a push notification, see who's there, and unlock the
door — all from a native Home Assistant automation.

> 🧪 Built and verified against a real **Dahua VTO2111D‑P‑S2** unit.

---

## ✨ Features

- 🔌 **Local push, zero polling** — a persistent TCP connection streams
  events the instant they happen (`iot_class: local_push`).
- 🛎️ **Doorbell, motion & tamper sensors** exposed as native `binary_sensor`
  entities.
- 🔓 **Open Door button** entity per configured relay channel — wire it
  into any automation, dashboard, or voice assistant.
- 🤖 **Native device triggers** — pick "Doorbell pressed", "Motion
  detected", "Call not answered" etc. straight from the Home Assistant
  automation editor, no YAML required.
- 🧭 **UI based config flow** — add your VTO from *Settings → Devices &
  Services*, no `configuration.yaml` editing.
- 🔁 **Automatic reconnect** with a connectivity `binary_sensor` so you
  always know if the door station dropped offline.
- 🛠️ **`dahua_vto.open_door` service** for scripting advanced unlock
  scenarios (custom short numbers, scenes, etc.).

## 📷 Entities created

| Entity | Type | Description |
|---|---|---|
| `binary_sensor.<device>_doorbell` | Binary sensor | Turns on briefly when the doorbell is pressed |
| `binary_sensor.<device>_motion` | Binary sensor | Motion detected by the door station camera |
| `binary_sensor.<device>_tamper` | Binary sensor | Tamper / video-blind alarm |
| `binary_sensor.<device>_connectivity` | Binary sensor | Live connection status to the VTO |
| `button.<device>_open_door` | Button | Momentarily triggers the door relay |
| `sensor.<device>_last_event` | Sensor (diagnostic) | Last normalized event received |

## 🚀 Installation

### Option 1 — HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=adaniluk&repository=dahua-vto-integration&category=integration)

1. Click the button above (or in HACS: **⋮ → Custom repositories** and add
   `https://github.com/adaniluk/dahua-vto-integration` as an *Integration*).
2. Install **Dahua VTO Intercom** from HACS.
3. Restart Home Assistant.

### Option 2 — Manual install

1. Copy `custom_components/dahua_vto` into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.

### Add the integration

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=dahua_vto)

Go to **Settings → Devices & Services → Add Integration**, search for
**Dahua VTO Intercom**, and enter:

| Field | Example | Notes |
|---|---|---|
| Host | `10.0.0.70` | IP or hostname of your VTO |
| Port | `5000` | Default DHIP port, rarely needs changing |
| Username | `admin` | The VTO web/admin username |
| Password | `••••••••` | The VTO web/admin password |

After setup, open the integration's **Configure** dialog to list which
door relay channels (comma separated, e.g. `1,2`) should get an
`Open Door` button.

## 🧑‍💻 Example automations

**Push a notification with a snapshot when the doorbell rings:**

```yaml
automation:
  - alias: "Doorbell pressed"
    trigger:
      - platform: device
        domain: dahua_vto
        device_id: !secret vto_device_id
        type: doorbell_press
    action:
      - service: notify.mobile_app_my_phone
        data:
          title: "🔔 Someone is at the door"
          message: "Tap to view"
          data:
            image: /api/camera_proxy/camera.front_door
```

**Auto-unlock the door when a trusted phone is on the arriving zone and the bell rings:**

```yaml
automation:
  - alias: "Auto unlock for family"
    trigger:
      - platform: device
        domain: dahua_vto
        device_id: !secret vto_device_id
        type: doorbell_press
    condition:
      - condition: state
        entity_id: person.me
        state: "home"
    action:
      - service: button.press
        target:
          entity_id: button.front_door_open_door
```

## 🧰 Advanced service

```yaml
service: dahua_vto.open_door
target:
  entity_id: button.front_door_open_door
data:
  short_number: "HA-AUTOMATION"
```

## 🩺 Troubleshooting

- **Cannot connect / timeout** — verify port `5000` (DHIP) is reachable
  from your Home Assistant host (`nc -vz <vto-ip> 5000`) and not blocked
  by VLAN/firewall rules.
- **Invalid auth** — the DHIP login uses the *same* admin credentials as
  the VTO's local web UI. Ensure the account isn't locked out after failed
  attempts (the VTO temporarily bans an IP after repeated bad logins).
- **No events firing** — some VTO/VTH firmware limits the number of
  concurrent DHIP sessions; make sure no other app (DMSS, another NVR)
  holds an active session, or increase the "Max Connection" setting on
  the device if available.

## 🔬 How it works

Dahua door stations expose a binary, JSON‑over‑TCP protocol on port
`5000` — the same one used by the DMSS app and Dahua NVRs — nicknamed
**DHIP**. Every message is framed with a small fixed header:

```
| 8 bytes magic | 4 bytes session | 4 bytes request id | 8 bytes length | 8 bytes length |
```

followed by a UTF‑8 JSON body. Authentication is a two-step MD5
challenge/response, after which the client attaches to
`eventManager` and receives a live stream of events (`_DoTalkAction_`
doorbell press, `VideoMotion`, `CallNoAnswered`, access control, etc.).
This integration keeps that connection open for the lifetime of the
config entry and automatically reconnects if the door station reboots or
the network blips.

## 🤝 Contributing

Issues and pull requests are welcome! Please run the test suite before
submitting:

```bash
pip install -r requirements_test.txt
pytest
```

## ⚠️ Disclaimer

This is an independent, community-built integration and is not affiliated
with, endorsed by, or supported by Dahua Technology. Use at your own risk.

## 📄 License

[MIT](LICENSE)
