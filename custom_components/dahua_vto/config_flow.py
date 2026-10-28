"""Config flow for the Dahua VTO Intercom integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .client import DahuaAuthError, DahuaVtoClient, DahuaVtoError
from .const import CONF_DOOR_CHANNELS, DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        ),
        vol.Required(CONF_PORT, default=DEFAULT_PORT): NumberSelector(
            NumberSelectorConfig(
                min=1,
                max=65535,
                mode=NumberSelectorMode.BOX,
            )
        ),
        vol.Required(CONF_USERNAME, default="admin"): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


async def _validate_connection(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate connection and retrieve device information."""
    client = DahuaVtoClient(
        data[CONF_HOST],
        int(data[CONF_PORT]),
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
    )

    try:
        await client.connect()
        return await client.get_system_info()
    finally:
        await client.disconnect()


class DahuaVtoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dahua VTO Intercom."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input = dict(user_input)
            user_input[CONF_PORT] = int(user_input[CONF_PORT])

            self._async_abort_entries_match(
                {
                    CONF_HOST: user_input[CONF_HOST],
                    CONF_PORT: user_input[CONF_PORT],
                }
            )

            try:
                info = await _validate_connection(self.hass, user_input)
            except DahuaAuthError:
                errors["base"] = "invalid_auth"
            except DahuaVtoError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception(
                    "Unexpected error validating Dahua VTO connection"
                )
                errors["base"] = "unknown"
            else:
                serial = info.get("serialNumber", user_input[CONF_HOST])
                await self.async_set_unique_id(str(serial))
                self._abort_if_unique_id_configured()

                title = info.get("deviceType", "Dahua VTO")

                return self.async_create_entry(
                    title=f"{title} ({user_input[CONF_HOST]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return DahuaVtoOptionsFlow()


class DahuaVtoOptionsFlow(OptionsFlow):
    """Handle options such as the relay channels to expose."""

    def _get_schema(self) -> vol.Schema:
        """Build the options schema."""
        current = self.config_entry.options.get(
            CONF_DOOR_CHANNELS,
            self.config_entry.data.get(CONF_DOOR_CHANNELS, [1]),
        )

        if isinstance(current, str):
            default_channels = current
        else:
            default_channels = ",".join(str(channel) for channel in current)

        return vol.Schema(
            {
                vol.Required(
                    CONF_DOOR_CHANNELS,
                    default=default_channels,
                ): str
            }
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage relay channel options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                raw_channels = str(user_input[CONF_DOOR_CHANNELS])
                channels = [
                    int(channel.strip())
                    for channel in raw_channels.split(",")
                    if channel.strip()
                ]

                if not channels:
                    raise ValueError("At least one channel is required")

                if any(channel < 1 for channel in channels):
                    raise ValueError("Channels must be positive integers")

                if len(channels) != len(set(channels)):
                    raise ValueError("Duplicate channels are not allowed")

            except (ValueError, KeyError):
                errors["base"] = "invalid_channels"
            else:
                return self.async_create_entry(
                    title="",
                    data={CONF_DOOR_CHANNELS: channels},
                )

        return self.async_show_form(
            step_id="init",
            data_schema=self._get_schema(),
            errors=errors,
        )
