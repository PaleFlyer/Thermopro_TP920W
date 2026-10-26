"""Switch to release the thermometer so the phone app can connect."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import TP920ConfigEntry, TP920Coordinator
from .entity import TP920Entity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TP920ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the connection switch."""
    async_add_entities([TP920ConnectionSwitch(entry.runtime_data)])


class TP920ConnectionSwitch(TP920Entity, SwitchEntity, RestoreEntity):
    """Turn off to disconnect, which frees the thermometer for the phone app."""

    _attr_name = "Bluetooth connection"
    _attr_icon = "mdi:bluetooth-connect"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: TP920Coordinator) -> None:
        super().__init__(coordinator, "connection")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.enabled

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state == STATE_OFF:
            await self.coordinator.async_set_enabled(False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_enabled(False)
        self.async_write_ha_state()
