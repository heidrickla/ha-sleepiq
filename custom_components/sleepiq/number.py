"""Support for SleepIQ SleepNumber firmness number entities."""

from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass
from typing import Any, cast, override

from asyncsleepiq.actuator import SleepIQActuator
from asyncsleepiq.bed import SleepIQBed
from asyncsleepiq.consts import CoreTemps, End, FootWarmingTemps, Side
from asyncsleepiq.core_climate import SleepIQCoreClimate
from asyncsleepiq.foot_warmer import SleepIQFootWarmer
from asyncsleepiq.sleeper import SleepIQSleeper

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ACTUATOR,
    CORE_CLIMATE_TIMER,
    FIRMNESS,
    FOOT_WARMING_TIMER,
    MASSAGE_TIMER,
)
from .coordinator import SleepIQConfigEntry, SleepIQDataUpdateCoordinator
from .entity import (
    SleepIQBedEntity,
    async_add_beds,
    async_write_to_bed,
    sleeper_label,
)
from .massage import (
    MASSAGE_TIMER_MAX,
    MASSAGE_TIMER_MIN,
    SleepIQMassage,
    side_label,
)

# Every number writes to the bed; the cloud API is happiest with one request
# in flight per account.
PARALLEL_UPDATES = 1

# One translation key per side and end, so no name is assembled from English
# words. A foundation that reports something else falls back to the plain
# "Position" name.
ACTUATOR_TRANSLATION_KEYS = {
    (Side.NONE, End.HEAD): "head_position",
    (Side.NONE, End.FOOT): "foot_position",
    (Side.LEFT, End.HEAD): "left_head_position",
    (Side.LEFT, End.FOOT): "left_foot_position",
    (Side.RIGHT, End.HEAD): "right_head_position",
    (Side.RIGHT, End.FOOT): "right_foot_position",
}


@dataclass(frozen=True, kw_only=True)
class SleepIQNumberEntityDescription(NumberEntityDescription):
    """Class to describe a SleepIQ number entity."""

    value_fn: Callable[[Any], float]
    set_value_fn: Callable[[Any, int], Coroutine[None, None, None]]
    get_unique_id_fn: Callable[[SleepIQBed, Any], str]
    get_translation_key_fn: Callable[[SleepIQBed, Any], str] | None = None
    get_placeholders_fn: Callable[[SleepIQBed, Any], dict[str, str]] | None = None


async def _async_set_firmness(sleeper: SleepIQSleeper, firmness: int) -> None:
    await sleeper.set_sleepnumber(firmness)


async def _async_set_actuator_position(
    actuator: SleepIQActuator, position: int
) -> None:
    await actuator.set_position(position)


def _get_actuator_translation_key(bed: SleepIQBed, actuator: SleepIQActuator) -> str:
    return ACTUATOR_TRANSLATION_KEYS.get((actuator.side, actuator.actuator), ACTUATOR)


def _get_actuator_unique_id(bed: SleepIQBed, actuator: SleepIQActuator) -> str:
    if actuator.side:
        return f"{bed.id}_{actuator.side.value}_{actuator.actuator}"

    return f"{bed.id}_{actuator.actuator}"


def _get_sleeper_placeholders(
    bed: SleepIQBed, sleeper: SleepIQSleeper
) -> dict[str, str]:
    return {"sleeper": sleeper_label(bed, sleeper)}


def _get_side_placeholders(bed: SleepIQBed, device: Any) -> dict[str, str]:
    return {"sleeper": side_label(bed, device.side)}


def _get_sleeper_unique_id(bed: SleepIQBed, sleeper: SleepIQSleeper) -> str:
    return f"{sleeper.sleeper_id}_{FIRMNESS}"


async def _async_set_foot_warmer_time(
    foot_warmer: SleepIQFootWarmer, time: int
) -> None:
    temperature = FootWarmingTemps(foot_warmer.temperature)
    if temperature != FootWarmingTemps.OFF:
        await foot_warmer.turn_on(temperature, time)

    foot_warmer.timer = time


def _get_foot_warming_unique_id(bed: SleepIQBed, foot_warmer: SleepIQFootWarmer) -> str:
    return f"{bed.id}_{foot_warmer.side.value}_{FOOT_WARMING_TIMER}"


async def _async_set_core_climate_time(
    core_climate: SleepIQCoreClimate, time: int
) -> None:
    temperature = CoreTemps(core_climate.temperature)
    if temperature != CoreTemps.OFF:
        await core_climate.turn_on(temperature, time)

    core_climate.timer = time


def _get_core_climate_unique_id(
    bed: SleepIQBed, core_climate: SleepIQCoreClimate
) -> str:
    return f"{bed.id}_{core_climate.side.value}_{CORE_CLIMATE_TIMER}"


NUMBER_DESCRIPTIONS: dict[str, SleepIQNumberEntityDescription] = {
    FIRMNESS: SleepIQNumberEntityDescription(
        key=FIRMNESS,
        translation_key=FIRMNESS,
        native_min_value=5,
        native_max_value=100,
        native_step=5,
        value_fn=lambda sleeper: cast(float, sleeper.sleep_number),
        set_value_fn=_async_set_firmness,
        get_unique_id_fn=_get_sleeper_unique_id,
        get_placeholders_fn=_get_sleeper_placeholders,
    ),
    ACTUATOR: SleepIQNumberEntityDescription(
        key=ACTUATOR,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        value_fn=lambda actuator: cast(float, actuator.position),
        set_value_fn=_async_set_actuator_position,
        get_unique_id_fn=_get_actuator_unique_id,
        get_translation_key_fn=_get_actuator_translation_key,
    ),
    FOOT_WARMING_TIMER: SleepIQNumberEntityDescription(
        key=FOOT_WARMING_TIMER,
        translation_key=FOOT_WARMING_TIMER,
        native_min_value=30,
        native_max_value=360,
        native_step=30,
        value_fn=lambda foot_warmer: foot_warmer.timer,
        set_value_fn=_async_set_foot_warmer_time,
        get_unique_id_fn=_get_foot_warming_unique_id,
        get_placeholders_fn=_get_side_placeholders,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=NumberDeviceClass.DURATION,
    ),
    CORE_CLIMATE_TIMER: SleepIQNumberEntityDescription(
        key=CORE_CLIMATE_TIMER,
        translation_key=CORE_CLIMATE_TIMER,
        native_min_value=0,
        native_max_value=SleepIQCoreClimate.max_core_climate_time,
        native_step=30,
        value_fn=lambda core_climate: core_climate.timer,
        set_value_fn=_async_set_core_climate_time,
        get_unique_id_fn=_get_core_climate_unique_id,
        get_placeholders_fn=_get_side_placeholders,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=NumberDeviceClass.DURATION,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SleepIQConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the SleepIQ bed sensors."""
    data = entry.runtime_data

    def build(bed: SleepIQBed) -> Sequence[Entity]:
        entities: list[Entity] = [
            SleepIQNumberEntity(
                data.data_coordinator, bed, sleeper, NUMBER_DESCRIPTIONS[FIRMNESS]
            )
            for sleeper in bed.sleepers
        ]
        entities.extend(
            SleepIQNumberEntity(
                data.data_coordinator, bed, actuator, NUMBER_DESCRIPTIONS[ACTUATOR]
            )
            for actuator in bed.foundation.actuators
        )
        entities.extend(
            SleepIQNumberEntity(
                data.data_coordinator,
                bed,
                foot_warmer,
                NUMBER_DESCRIPTIONS[FOOT_WARMING_TIMER],
            )
            for foot_warmer in bed.foundation.foot_warmers
        )
        entities.extend(
            SleepIQNumberEntity(
                data.data_coordinator,
                bed,
                core_climate,
                NUMBER_DESCRIPTIONS[CORE_CLIMATE_TIMER],
            )
            for core_climate in bed.foundation.core_climates
        )
        entities.extend(
            SleepIQMassageTimerNumber(data.data_coordinator, bed, massage)
            for massage in data.massage_sides.get(bed.id, [])
        )
        return entities

    async_add_beds(entry, data.data_coordinator, async_add_entities, build)


class SleepIQNumberEntity(SleepIQBedEntity[SleepIQDataUpdateCoordinator], NumberEntity):
    """Representation of a SleepIQ number entity."""

    entity_description: SleepIQNumberEntityDescription

    def __init__(
        self,
        coordinator: SleepIQDataUpdateCoordinator,
        bed: SleepIQBed,
        device: Any,
        description: SleepIQNumberEntityDescription,
    ) -> None:
        """Initialize the number."""
        self.entity_description = description
        self.device = device

        self._attr_unique_id = description.get_unique_id_fn(bed, device)
        if description.get_translation_key_fn is not None:
            self._attr_translation_key = description.get_translation_key_fn(bed, device)
        if description.get_placeholders_fn is not None:
            self._attr_translation_placeholders = description.get_placeholders_fn(
                bed, device
            )

        super().__init__(coordinator, bed)

    @callback
    @override
    def _async_update_attrs(self) -> None:
        """Update number attributes."""
        self._attr_native_value = float(self.entity_description.value_fn(self.device))

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Set the number value."""
        await async_write_to_bed(
            self.entity_description.set_value_fn(self.device, int(value)),
            "write_failed",
        )
        self._attr_native_value = value
        self.async_write_ha_state()


class SleepIQMassageTimerNumber(
    SleepIQBedEntity[SleepIQDataUpdateCoordinator], NumberEntity
):
    """Massage timer, in minutes, for one side of the bed.

    An armed countdown rather than a stored preference: the bed drops it if a
    massage does not start, and counts it down while one runs. Named by the
    sleeper on that side and keyed on the physical side, like the massage
    selects.
    """

    _attr_translation_key = MASSAGE_TIMER
    _attr_native_min_value = MASSAGE_TIMER_MIN
    _attr_native_max_value = MASSAGE_TIMER_MAX
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = NumberDeviceClass.DURATION

    def __init__(
        self,
        coordinator: SleepIQDataUpdateCoordinator,
        bed: SleepIQBed,
        massage: SleepIQMassage,
    ) -> None:
        """Initialize the massage timer."""
        self.massage = massage
        self._attr_translation_placeholders = {"sleeper": side_label(bed, massage.side)}
        self._attr_unique_id = f"{bed.id}_{massage.side.value}_{MASSAGE_TIMER}"
        super().__init__(coordinator, bed)

    @callback
    @override
    def _async_update_attrs(self) -> None:
        """Update number attributes."""
        self._attr_native_value = float(self.massage.timer)

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Set the timer, translating a refusal for the user."""
        await async_write_to_bed(
            self.massage.set_timer(int(value)), "massage_write_failed"
        )
        self._attr_native_value = float(self.massage.timer)
        self.async_write_ha_state()
