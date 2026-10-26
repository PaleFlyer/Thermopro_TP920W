"""ThermoPro TP920 BLE thermometer, connected through any Home Assistant Bluetooth adapter or proxy."""

from __future__ import annotations

from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import CONF_FAHRENHEIT_DISPLAY, DEFAULT_FAHRENHEIT_DISPLAY, DOMAIN
from .coordinator import TP920ConfigEntry, TP920Coordinator

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: TP920ConfigEntry) -> bool:
    """Set up a ThermoPro TP920 from a config entry."""
    address = entry.unique_id
    assert address is not None
    coordinator = TP920Coordinator(
        hass,
        entry,
        address.upper(),
        entry.options.get(CONF_FAHRENHEIT_DISPLAY, DEFAULT_FAHRENHEIT_DISPLAY),
    )
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    # Start only after every platform has subscribed, so no update is missed.
    entry.async_on_unload(coordinator.async_start())
    entry.async_on_unload(coordinator.async_shutdown)

    async def _async_stop(event: Event) -> None:
        await coordinator.async_shutdown()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
    )
    return True


async def _async_update_listener(hass: HomeAssistant, entry: TP920ConfigEntry) -> None:
    """Reload when the options change so the new display unit is sent."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: TP920ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
