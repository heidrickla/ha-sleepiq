"""Entity for the SleepIQ integration."""

from abc import abstractmethod
from collections.abc import Callable, Coroutine, Sequence
from typing import Any, override

from asyncsleepiq.bed import SleepIQBed
from asyncsleepiq.consts import Side
from asyncsleepiq.exceptions import (
    SleepIQAPIException,
    SleepIQLoginException,
    SleepIQTimeoutException,
)
from asyncsleepiq.sleeper import SleepIQSleeper

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import (
    SleepIQConfigEntry,
    SleepIQDataUpdateCoordinator,
    SleepIQPauseUpdateCoordinator,
    SleepIQSleepDataCoordinator,
)
from .massage import side_label

type _DataCoordinatorType = (
    SleepIQDataUpdateCoordinator
    | SleepIQPauseUpdateCoordinator
    | SleepIQSleepDataCoordinator
)


def device_from_bed(bed: SleepIQBed) -> DeviceInfo:
    """Create a device given a bed.

    The bed id is carried as an identifier beside the MAC connection, so a bed
    that leaves the account can be found in the registry and removed.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, bed.id)},
        connections={(dr.CONNECTION_NETWORK_MAC, bed.mac_addr)},
        manufacturer="SleepNumber",
        name=bed.name,
        model=bed.model,
    )


def sleeper_for_side(bed: SleepIQBed, side: Side) -> SleepIQSleeper:
    """Find the sleeper for a side or the first sleeper."""
    for sleeper in bed.sleepers:
        if sleeper.side == side:
            return sleeper
    return bed.sleepers[0]


def sleeper_label(bed: SleepIQBed, sleeper: SleepIQSleeper) -> str:
    """The word that names one sleeper's entities."""
    return str(sleeper.name) if sleeper.name else side_label(bed, sleeper.side)


async def async_write_to_bed(
    request: Coroutine[Any, Any, None], translation_key: str
) -> None:
    """Send one write to the bed, translating a refusal for the user.

    The library checks ranges and option names itself and raises ValueError,
    which is the caller's mistake rather than the bed's, so that one becomes a
    ServiceValidationError.
    """
    try:
        await request
    except ValueError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_value",
            translation_placeholders={"error": str(err)},
        ) from err
    except (
        SleepIQAPIException,
        SleepIQLoginException,
        SleepIQTimeoutException,
    ) as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key=translation_key,
            translation_placeholders={"error": str(err)},
        ) from err


@callback
def async_add_beds(
    entry: SleepIQConfigEntry,
    coordinator: SleepIQDataUpdateCoordinator,
    async_add_entities: AddConfigEntryEntitiesCallback,
    build: Callable[[SleepIQBed], Sequence[Entity]],
) -> None:
    """Add the entities of every bed on the account, now and later.

    The coordinator re-reads the account's bed list on each poll, so a bed
    added to the account gets its entities without a reload.
    """
    known: set[str] = set()

    @callback
    def _add_new_beds() -> None:
        new = [
            bed
            for bed_id, bed in coordinator.client.beds.items()
            if bed_id not in known
        ]
        if not new:
            return
        known.update(bed.id for bed in new)
        entities: list[Entity] = []
        for bed in new:
            entities.extend(build(bed))
        async_add_entities(entities)

    _add_new_beds()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_beds))


class SleepIQEntity(Entity):
    """Implementation of a SleepIQ entity."""

    _attr_has_entity_name = True

    def __init__(self, bed: SleepIQBed) -> None:
        """Initialize the SleepIQ entity."""
        self.bed = bed
        self._attr_device_info = device_from_bed(bed)


class SleepIQBedEntity[_SleepIQCoordinatorT: _DataCoordinatorType](
    CoordinatorEntity[_SleepIQCoordinatorT]
):
    """Implementation of a SleepIQ sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: _SleepIQCoordinatorT,
        bed: SleepIQBed,
    ) -> None:
        """Initialize the SleepIQ sensor entity."""
        super().__init__(coordinator)
        self.bed = bed
        self._attr_device_info = device_from_bed(bed)
        self._async_update_attrs()

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._async_update_attrs()
        super()._handle_coordinator_update()

    @callback
    @abstractmethod
    def _async_update_attrs(self) -> None:
        """Update sensor attributes."""


class SleepIQSleeperEntity[_SleepIQCoordinatorT: _DataCoordinatorType](
    SleepIQBedEntity[_SleepIQCoordinatorT]
):
    """Implementation of a SleepIQ sensor."""

    def __init__(
        self,
        coordinator: _SleepIQCoordinatorT,
        bed: SleepIQBed,
        sleeper: SleepIQSleeper,
        name: str,
        label: str | None = None,
    ) -> None:
        """Initialize the SleepIQ sensor entity.

        The name is the entity type and keys the unique id. The label is the
        word the translated name puts in front of it: the sleeper's own by
        default, and the physical side for hardware that is keyed on the side.
        """
        self.sleeper = sleeper
        super().__init__(coordinator, bed)

        self._attr_translation_placeholders = {
            "sleeper": label if label is not None else sleeper_label(bed, sleeper)
        }
        self._attr_unique_id = f"{sleeper.sleeper_id}_{name}"
