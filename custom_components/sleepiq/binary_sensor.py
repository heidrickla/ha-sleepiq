"""Support for SleepIQ sensors."""

from collections.abc import Sequence
from typing import override

from asyncsleepiq.bed import SleepIQBed
from asyncsleepiq.sleeper import SleepIQSleeper

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import IS_IN_BED
from .coordinator import SleepIQConfigEntry, SleepIQDataUpdateCoordinator
from .entity import SleepIQSleeperEntity, async_add_beds

# Read-only and coordinator-driven: the coordinator does the polling, so
# nothing here needs limiting.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SleepIQConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the SleepIQ bed binary sensors."""
    data = entry.runtime_data

    def build(bed: SleepIQBed) -> Sequence[Entity]:
        return [
            IsInBedBinarySensor(data.data_coordinator, bed, sleeper)
            for sleeper in bed.sleepers
        ]

    async_add_beds(entry, data.data_coordinator, async_add_entities, build)


class IsInBedBinarySensor(
    SleepIQSleeperEntity[SleepIQDataUpdateCoordinator], BinarySensorEntity
):
    """Implementation of a SleepIQ presence sensor."""

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_translation_key = IS_IN_BED

    def __init__(
        self,
        coordinator: SleepIQDataUpdateCoordinator,
        bed: SleepIQBed,
        sleeper: SleepIQSleeper,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, bed, sleeper, IS_IN_BED)

    @callback
    @override
    def _async_update_attrs(self) -> None:
        """Update sensor attributes."""
        self._attr_is_on = self.sleeper.in_bed
