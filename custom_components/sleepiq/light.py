"""Support for SleepIQ outlet lights."""

from collections.abc import Sequence
from typing import Any, override

from asyncsleepiq.bed import SleepIQBed
from asyncsleepiq.light import SleepIQLight

from homeassistant.components.light import LightEntity
from homeassistant.components.light.const import ColorMode
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import LIGHT
from .coordinator import SleepIQConfigEntry, SleepIQDataUpdateCoordinator
from .entity import SleepIQBedEntity, async_add_beds, async_write_to_bed

# Each light writes to the bed; the cloud API is happiest with one request in
# flight per account.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SleepIQConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the SleepIQ bed lights."""
    data = entry.runtime_data

    def build(bed: SleepIQBed) -> Sequence[Entity]:
        return [
            SleepIQLightEntity(data.data_coordinator, bed, light)
            for light in bed.foundation.lights
        ]

    async_add_beds(entry, data.data_coordinator, async_add_entities, build)


class SleepIQLightEntity(SleepIQBedEntity[SleepIQDataUpdateCoordinator], LightEntity):
    """Representation of a light."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_translation_key = LIGHT

    def __init__(
        self,
        coordinator: SleepIQDataUpdateCoordinator,
        bed: SleepIQBed,
        light: SleepIQLight,
    ) -> None:
        """Initialize the light."""
        self.light = light
        super().__init__(coordinator, bed)
        self._attr_translation_placeholders = {"outlet": str(light.outlet_id)}
        self._attr_unique_id = f"{bed.id}-light-{light.outlet_id}"  # pylint: disable=home-assistant-entity-unique-id-redundant-platform

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on light."""
        await async_write_to_bed(self.light.turn_on(), "write_failed")
        self._handle_coordinator_update()

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off light."""
        await async_write_to_bed(self.light.turn_off(), "write_failed")
        self._handle_coordinator_update()

    @callback
    @override
    def _async_update_attrs(self) -> None:
        """Update light attributes."""
        self._attr_is_on = self.light.is_on
