"""Temperature and battery sensors for the ThermoPro TP920."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import TP920ConfigEntry, TP920Coordinator
from .entity import TP920Entity
from .protocol import Reading


@dataclass(frozen=True, kw_only=True)
class TP920SensorDescription(SensorEntityDescription):
    """Sensor description with a value extractor."""

    value_fn: Callable[[Reading], float | int | None]


SENSORS: tuple[TP920SensorDescription, ...] = (
    TP920SensorDescription(
        key="probe_1",
        name="Probe 1",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda reading: reading.probe1,
    ),
    TP920SensorDescription(
        key="probe_2",
        name="Probe 2",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda reading: reading.probe2,
    ),
    TP920SensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda reading: reading.battery,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TP920ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        TP920Sensor(coordinator, description) for description in SENSORS
    )


class TP920Sensor(TP920Entity, SensorEntity):
    """A probe temperature or battery sensor."""

    entity_description: TP920SensorDescription

    def __init__(
        self, coordinator: TP920Coordinator, description: TP920SensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | None:
        reading = self.coordinator.data
        if reading is None:
            return None
        return self.entity_description.value_fn(reading)
