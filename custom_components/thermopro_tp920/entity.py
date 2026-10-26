"""Base entity for the ThermoPro TP920."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import MANUFACTURER, MODEL
from .coordinator import TP920Coordinator


class TP920Entity(Entity):
    """Entity that is updated by pushes from the coordinator."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: TP920Coordinator, key: str) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=coordinator.name,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.connected

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )
