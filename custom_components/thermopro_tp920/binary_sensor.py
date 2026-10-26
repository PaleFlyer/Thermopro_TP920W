"""Connection status for the ThermoPro TP920."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import TP920ConfigEntry, TP920Coordinator
from .entity import TP920Entity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TP920ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the connection sensor."""
    async_add_entities([TP920ConnectedSensor(entry.runtime_data)])


class TP920ConnectedSensor(TP920Entity, BinarySensorEntity):
    """On while Home Assistant is connected to the thermometer."""

    _attr_name = "Connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: TP920Coordinator) -> None:
        super().__init__(coordinator, "connected")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.connected
