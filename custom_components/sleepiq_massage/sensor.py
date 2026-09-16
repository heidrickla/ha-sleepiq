"""Support for SleepIQ sensors."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import override

from asyncsleepiq.bed import SleepIQBed
from asyncsleepiq.sleeper import SleepIQSleeper

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    HEART_RATE,
    HEART_RATE_AVG,
    HRV,
    PRESSURE,
    RESPIRATORY_RATE,
    RESPIRATORY_RATE_AVG,
    SLEEP_DURATION,
    SLEEP_NUMBER,
    SLEEP_SCORE,
)
from .coordinator import (
    SleepIQConfigEntry,
    SleepIQDataUpdateCoordinator,
    SleepIQSleepDataCoordinator,
)
from .entity import SleepIQSleeperEntity, async_add_beds

# Read-only and coordinator-driven: the coordinators do the polling, so
# nothing here needs limiting.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class SleepIQSensorEntityDescription(SensorEntityDescription):
    """Describes SleepIQ sensor entity."""

    value_fn: Callable[[SleepIQSleeper], float | int | None]


BED_SENSORS: tuple[SleepIQSensorEntityDescription, ...] = (
    SleepIQSensorEntityDescription(
        key=PRESSURE,
        translation_key=PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda sleeper: sleeper.pressure,
    ),
    SleepIQSensorEntityDescription(
        key=SLEEP_NUMBER,
        translation_key=SLEEP_NUMBER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda sleeper: sleeper.sleep_number,
    ),
)

SLEEP_HEALTH_SENSORS: tuple[SleepIQSensorEntityDescription, ...] = (
    SleepIQSensorEntityDescription(
        key=SLEEP_SCORE,
        translation_key=SLEEP_SCORE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="score",
        value_fn=lambda sleeper: (
            sleeper.sleep_data.sleep_score if sleeper.sleep_data else None
        ),
    ),
    SleepIQSensorEntityDescription(
        key=SLEEP_DURATION,
        translation_key=SLEEP_DURATION,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=1,
        value_fn=lambda sleeper: (
            round(sleeper.sleep_data.duration / 3600, 1)
            if sleeper.sleep_data and sleeper.sleep_data.duration
            else None
        ),
    ),
    SleepIQSensorEntityDescription(
        key=HEART_RATE,
        translation_key=HEART_RATE_AVG,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="bpm",
        value_fn=lambda sleeper: (
            sleeper.sleep_data.heart_rate if sleeper.sleep_data else None
        ),
    ),
    SleepIQSensorEntityDescription(
        key=RESPIRATORY_RATE,
        translation_key=RESPIRATORY_RATE_AVG,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="brpm",
        value_fn=lambda sleeper: (
            sleeper.sleep_data.respiratory_rate if sleeper.sleep_data else None
        ),
    ),
    SleepIQSensorEntityDescription(
        key=HRV,
        translation_key=HRV,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        value_fn=lambda sleeper: sleeper.sleep_data.hrv if sleeper.sleep_data else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SleepIQConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the SleepIQ bed sensors."""
    data = entry.runtime_data

    def build(bed: SleepIQBed) -> Sequence[Entity]:
        entities: list[Entity] = [
            SleepIQSensorEntity(data.data_coordinator, bed, sleeper, description)
            for sleeper in bed.sleepers
            for description in BED_SENSORS
        ]
        entities.extend(
            SleepIQSensorEntity(data.sleep_data_coordinator, bed, sleeper, description)
            for sleeper in bed.sleepers
            for description in SLEEP_HEALTH_SENSORS
        )
        return entities

    async_add_beds(entry, data.data_coordinator, async_add_entities, build)


class SleepIQSensorEntity(
    SleepIQSleeperEntity[SleepIQDataUpdateCoordinator | SleepIQSleepDataCoordinator],
    SensorEntity,
):
    """Representation of a SleepIQ sensor."""

    entity_description: SleepIQSensorEntityDescription

    def __init__(
        self,
        coordinator: SleepIQDataUpdateCoordinator | SleepIQSleepDataCoordinator,
        bed: SleepIQBed,
        sleeper: SleepIQSleeper,
        description: SleepIQSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = description
        super().__init__(coordinator, bed, sleeper, description.key)

    @callback
    @override
    def _async_update_attrs(self) -> None:
        """Update sensor attributes."""
        self._attr_native_value = self.entity_description.value_fn(self.sleeper)
