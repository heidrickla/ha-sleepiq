"""Support for SleepIQ switches."""

from collections.abc import Sequence
from typing import Any, override

from asyncsleepiq.bed import SleepIQBed

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import PAUSE_MODE
from .coordinator import SleepIQConfigEntry, SleepIQPauseUpdateCoordinator
from .entity import SleepIQBedEntity, async_add_beds, async_write_to_bed

# The switch writes to the bed; the cloud API is happiest with one request in
# flight per account.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SleepIQConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sleep number switches."""
    data = entry.runtime_data

    def build(bed: SleepIQBed) -> Sequence[Entity]:
        return [SleepNumberPrivateSwitch(data.pause_coordinator, bed)]

    async_add_beds(entry, data.data_coordinator, async_add_entities, build)


class SleepNumberPrivateSwitch(
    SleepIQBedEntity[SleepIQPauseUpdateCoordinator], SwitchEntity
):
    """Representation of SleepIQ privacy mode."""

    _attr_translation_key = PAUSE_MODE

    def __init__(
        self, coordinator: SleepIQPauseUpdateCoordinator, bed: SleepIQBed
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, bed)
        self._attr_unique_id = f"{bed.id}-pause-mode"

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on switch."""
        await async_write_to_bed(self.bed.set_pause_mode(True), "write_failed")
        self._handle_coordinator_update()

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off switch."""
        await async_write_to_bed(self.bed.set_pause_mode(False), "write_failed")
        self._handle_coordinator_update()

    @callback
    @override
    def _async_update_attrs(self) -> None:
        """Update switch attributes."""
        self._attr_is_on = self.bed.paused
