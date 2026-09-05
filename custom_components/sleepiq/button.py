"""Support for SleepIQ buttons."""

from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass
from typing import Any, override

from asyncsleepiq.bed import SleepIQBed

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SleepIQConfigEntry
from .entity import SleepIQEntity, async_add_beds, async_write_to_bed

# Both buttons write to the bed; the cloud API is happiest with one request in
# flight per account.
PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class SleepIQButtonEntityDescription(ButtonEntityDescription):
    """Class to describe a Button entity."""

    press_action: Callable[[SleepIQBed], Coroutine[Any, Any, None]]


ENTITY_DESCRIPTIONS = [
    SleepIQButtonEntityDescription(
        key="calibrate",
        translation_key="calibrate",
        # Re-baselining the pressure sensors sets the bed up rather than
        # operating it.
        entity_category=EntityCategory.CONFIG,
        press_action=lambda client: client.calibrate(),
    ),
    SleepIQButtonEntityDescription(
        key="stop-pump",
        translation_key="stop_pump",
        press_action=lambda client: client.stop_pump(),
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SleepIQConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sleep number buttons."""
    data = entry.runtime_data

    def build(bed: SleepIQBed) -> Sequence[Entity]:
        return [SleepNumberButton(bed, ed) for ed in ENTITY_DESCRIPTIONS]

    async_add_beds(entry, data.data_coordinator, async_add_entities, build)


class SleepNumberButton(SleepIQEntity, ButtonEntity):
    """Representation of an SleepIQ button."""

    entity_description: SleepIQButtonEntityDescription

    def __init__(
        self, bed: SleepIQBed, entity_description: SleepIQButtonEntityDescription
    ) -> None:
        """Initialize the Button."""
        super().__init__(bed)
        self._attr_unique_id = f"{bed.id}-{entity_description.key}"
        self.entity_description = entity_description

    @override
    async def async_press(self) -> None:
        """Press the button."""
        await async_write_to_bed(
            self.entity_description.press_action(self.bed), "write_failed"
        )
