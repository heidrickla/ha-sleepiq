"""Coordinator for SleepIQ."""

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any, override

from asyncsleepiq.asyncsleepiq import AsyncSleepIQ
from asyncsleepiq.exceptions import (
    SleepIQAPIException,
    SleepIQLoginException,
    SleepIQTimeoutException,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .massage import SleepIQMassage, build_massage_sides, update_massage

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=60)
LONGER_UPDATE_INTERVAL = timedelta(minutes=5)
SLEEP_DATA_UPDATE_INTERVAL = timedelta(hours=1)  # Sleep data doesn't change frequently

type SleepIQConfigEntry = ConfigEntry[SleepIQData]


async def _gather(tasks: list[Coroutine[Any, Any, None]]) -> None:
    """Run the fetches together and turn library failures into coordinator ones.

    The library re-logs in on a 401 and raises SleepIQLoginException when the
    stored password no longer works. Left uncaught that logs a traceback every
    poll; raised as ConfigEntryAuthFailed it starts the reauth flow instead.
    """
    try:
        await asyncio.gather(*tasks)
    except SleepIQLoginException as err:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN, translation_key="invalid_auth"
        ) from err
    except SleepIQTimeoutException as err:
        raise UpdateFailed(
            translation_domain=DOMAIN, translation_key="update_timeout"
        ) from err
    except SleepIQAPIException as err:
        raise UpdateFailed(
            translation_domain=DOMAIN,
            translation_key="update_failed",
            translation_placeholders={"error": str(err)},
        ) from err


class SleepIQDataUpdateCoordinator(DataUpdateCoordinator[None]):
    """SleepIQ data update coordinator."""

    config_entry: SleepIQConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: SleepIQConfigEntry,
        client: AsyncSleepIQ,
        massage_sides: dict[str, list[SleepIQMassage]],
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{config_entry.data[CONF_USERNAME]}@SleepIQ",
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.massage_sides = massage_sides

    async def _async_follow_the_account(self) -> None:
        """Re-read the account's beds so added and removed ones are followed.

        One GET per poll lists the account. Only when that list differs from
        the beds already loaded does the full enumeration run again, which is
        what builds sleepers, foundations and massage objects. A list that
        comes back empty is treated as a hiccup rather than as every bed being
        removed: an account with no beds cannot have set up in the first place.
        """
        data = await self.client.get("bed")
        current = {bed["bedId"] for bed in data.get("beds", [])}
        previous_beds = dict(self.client.beds)
        if not current or current == set(previous_beds):
            return

        _LOGGER.debug("Bed list changed, re-reading the account")
        await self.client.init_beds()

        # init_beds() builds a new object for every bed, including the ones
        # already set up, whose entities hold the old objects and would then
        # read a copy nothing updates any more. Keep those and take only the
        # beds that are new to the account.
        self.client.beds = {
            bed_id: previous_beds.get(bed_id, bed)
            for bed_id, bed in self.client.beds.items()
        }

        registry = dr.async_get(self.hass)
        for bed_id in set(previous_beds) - set(self.client.beds):
            device = registry.async_get_device(identifiers={(DOMAIN, bed_id)})
            if device is not None:
                _LOGGER.debug("Removing bed %s, no longer on the account", bed_id)
                registry.async_remove_device(device.id)

        previous_sides = dict(self.massage_sides)
        self.massage_sides.clear()
        self.massage_sides.update(
            {
                bed.id: (
                    previous_sides[bed.id]
                    if bed.id in previous_sides
                    else build_massage_sides(self.client, bed)
                )
                for bed in self.client.beds.values()
            }
        )

    @override
    async def _async_update_data(self) -> None:
        await _gather([self._async_follow_the_account()])

        tasks: list[Coroutine[Any, Any, None]] = [self.client.fetch_bed_statuses()]
        tasks.extend(
            bed.foundation.update_foundation_status()
            for bed in self.client.beds.values()
        )
        # Massage state is not part of update_foundation_status(); the
        # library never reads it. One GET per bed covers both sides.
        tasks.extend(
            update_massage(self.client, bed_id, sides)
            for bed_id, sides in self.massage_sides.items()
        )
        await _gather(tasks)


class SleepIQPauseUpdateCoordinator(DataUpdateCoordinator[None]):
    """SleepIQ pause update coordinator."""

    config_entry: SleepIQConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: SleepIQConfigEntry,
        client: AsyncSleepIQ,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{config_entry.data[CONF_USERNAME]}@SleepIQPause",
            update_interval=LONGER_UPDATE_INTERVAL,
        )
        self.client = client

    @override
    async def _async_update_data(self) -> None:
        await _gather([bed.fetch_pause_mode() for bed in self.client.beds.values()])


class SleepIQSleepDataCoordinator(DataUpdateCoordinator[None]):
    """SleepIQ sleep health data coordinator."""

    config_entry: SleepIQConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: SleepIQConfigEntry,
        client: AsyncSleepIQ,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{config_entry.data[CONF_USERNAME]}@SleepIQSleepData",
            update_interval=SLEEP_DATA_UPDATE_INTERVAL,
        )
        self.client = client

    @override
    async def _async_update_data(self) -> None:
        """Fetch sleep health data from API via asyncsleepiq library."""
        await _gather(
            [
                sleeper.fetch_sleep_data()
                for bed in self.client.beds.values()
                for sleeper in bed.sleepers
            ]
        )


@dataclass
class SleepIQData:
    """Data for the sleepiq integration."""

    data_coordinator: SleepIQDataUpdateCoordinator
    pause_coordinator: SleepIQPauseUpdateCoordinator
    sleep_data_coordinator: SleepIQSleepDataCoordinator
    client: AsyncSleepIQ
    # Massage objects per bed id; empty for a bed without the massage board.
    massage_sides: dict[str, list[SleepIQMassage]]
