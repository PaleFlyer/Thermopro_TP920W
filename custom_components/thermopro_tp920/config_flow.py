"""Config flow for the ThermoPro TP920 integration."""

from __future__ import annotations

from typing import Any

try:
    import probatio as vol
except ImportError:  # Home Assistant releases that still ship voluptuous
    import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers.selector import BooleanSelector

from .const import (
    ADVERTISED_NAME_PREFIXES,
    CONF_FAHRENHEIT_DISPLAY,
    DEFAULT_FAHRENHEIT_DISPLAY,
    DOMAIN,
)


def _is_supported(discovery_info: BluetoothServiceInfoBleak) -> bool:
    return (discovery_info.name or "").lower().startswith(ADVERTISED_NAME_PREFIXES)


def _title(discovery_info: BluetoothServiceInfoBleak) -> str:
    suffix = discovery_info.address.replace(":", "")[-4:]
    return f"ThermoPro TP920 {suffix}"


class TP920ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the ThermoPro TP920."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, str] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle discovery by the Bluetooth integration."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        if not _is_supported(discovery_info):
            return self.async_abort(reason="not_supported")
        self._discovery_info = discovery_info
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered thermometer."""
        assert self._discovery_info is not None
        title = _title(self._discovery_info)
        if user_input is not None:
            return self.async_create_entry(title=title, data={})

        self._set_confirm_only()
        placeholders = {"name": title}
        self.context["title_placeholders"] = placeholders
        return self.async_show_form(
            step_id="bluetooth_confirm", description_placeholders=placeholders
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a thermometer that is currently advertising."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=self._discovered_devices[address], data={}
            )

        current_addresses = self._async_current_ids(include_ignore=False)
        for discovery_info in async_discovered_service_info(self.hass, True):
            address = discovery_info.address
            if address in current_addresses or address in self._discovered_devices:
                continue
            if _is_supported(discovery_info):
                self._discovered_devices[address] = _title(discovery_info)

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_ADDRESS): vol.In(self._discovered_devices)}
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return TP920OptionsFlow()


class TP920OptionsFlow(OptionsFlow):
    """Options for the ThermoPro TP920."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_FAHRENHEIT_DISPLAY, DEFAULT_FAHRENHEIT_DISPLAY
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_FAHRENHEIT_DISPLAY, default=current
                    ): BooleanSelector()
                }
            ),
        )
