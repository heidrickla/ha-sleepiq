"""Support for SleepIQ from SleepNumber."""

import logging
from typing import Any

from asyncsleepiq import (
    AsyncSleepIQ,
    SleepIQAPIException,
    SleepIQLoginException,
    SleepIQTimeoutException,
)
import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, PRESSURE, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    IS_IN_BED,
    MASSAGE_FOOT_SPEED,
    MASSAGE_HEAD_SPEED,
    MASSAGE_MODE,
    MASSAGE_TIMER,
    SLEEP_NUMBER,
)
from .coordinator import (
    SleepIQConfigEntry,
    SleepIQData,
    SleepIQDataUpdateCoordinator,
    SleepIQPauseUpdateCoordinator,
    SleepIQSleepDataCoordinator,
)
from .massage import build_massage_sides

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: {
            vol.Required(CONF_USERNAME): cv.string,
            vol.Required(CONF_PASSWORD): cv.string,
        }
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up sleepiq component."""
    if DOMAIN in config:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=config[DOMAIN]
            )
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: SleepIQConfigEntry) -> bool:
    """Set up the SleepIQ config entry."""
    conf = entry.data
    email = conf[CONF_USERNAME]
    password = conf[CONF_PASSWORD]

    client_session = async_create_clientsession(hass)

    gateway = AsyncSleepIQ(client_session=client_session)

    try:
        await gateway.login(email, password)
    except SleepIQLoginException as err:
        _LOGGER.error("Could not authenticate with SleepIQ server")
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN, translation_key="invalid_auth"
        ) from err
    except SleepIQTimeoutException as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="login_timeout"
        ) from err

    try:
        await gateway.init_beds()
    except SleepIQTimeoutException as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="init_timeout"
        ) from err
    except SleepIQAPIException as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="init_failed",
            translation_placeholders={"error": str(err)},
        ) from err

    # asyncsleepiq has no massage object, so build ours per bed before any
    # coordinator refresh runs. Beds without the massage board get an empty
    # list and therefore no entities.
    massage_sides = {
        bed.id: build_massage_sides(gateway, bed) for bed in gateway.beds.values()
    }

    await _async_migrate_unique_ids(hass, entry, gateway)
    await _async_migrate_massage_unique_ids(hass, entry, gateway)

    coordinator = SleepIQDataUpdateCoordinator(hass, entry, gateway, massage_sides)
    pause_coordinator = SleepIQPauseUpdateCoordinator(hass, entry, gateway)
    sleep_data_coordinator = SleepIQSleepDataCoordinator(hass, entry, gateway)

    # Call the SleepIQ API to refresh data
    await coordinator.async_config_entry_first_refresh()
    await pause_coordinator.async_config_entry_first_refresh()
    await sleep_data_coordinator.async_config_entry_first_refresh()

    entry.runtime_data = SleepIQData(
        data_coordinator=coordinator,
        pause_coordinator=pause_coordinator,
        sleep_data_coordinator=sleep_data_coordinator,
        client=gateway,
        massage_sides=massage_sides,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: SleepIQConfigEntry) -> bool:
    """Unload the config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_migrate_unique_ids(
    hass: HomeAssistant, entry: ConfigEntry, gateway: AsyncSleepIQ
) -> None:
    """Migrate old unique ids."""
    names_to_ids = {
        sleeper.name: sleeper.sleeper_id
        for bed in gateway.beds.values()
        for sleeper in bed.sleepers
    }

    bed_ids = {bed.id for bed in gateway.beds.values()}

    @callback
    def _async_migrator(entity_entry: er.RegistryEntry) -> dict[str, Any] | None:
        # Old format for sleeper entities was {bed_id}_{sleeper.name}_{sensor_type}.....
        # New format is {sleeper.sleeper_id}_{sensor_type}....
        sensor_types = [IS_IN_BED, PRESSURE, SLEEP_NUMBER]

        old_unique_id = entity_entry.unique_id
        parts = old_unique_id.split("_")

        # If it doesn't begin with a bed id or end with one of the sensor types,
        # it doesn't need to be migrated
        if parts[0] not in bed_ids or not old_unique_id.endswith(tuple(sensor_types)):
            return None

        sensor_type = next(filter(old_unique_id.endswith, sensor_types))
        sleeper_name = "_".join(parts[1:]).removesuffix(f"_{sensor_type}")
        sleeper_id = names_to_ids.get(sleeper_name)

        if not sleeper_id:
            return None

        new_unique_id = f"{sleeper_id}_{sensor_type}"

        _LOGGER.debug(
            "Migrating unique_id from [%s] to [%s]",
            old_unique_id,
            new_unique_id,
        )
        return {"new_unique_id": new_unique_id}

    await er.async_migrate_entries(hass, entry.entry_id, _async_migrator)


async def _async_migrate_massage_unique_ids(
    hass: HomeAssistant, entry: ConfigEntry, gateway: AsyncSleepIQ
) -> None:
    """Move massage entities from sleeper-keyed to side-keyed unique ids.

    The first release keyed them {sleeper_id}_{type}, which collides on a bed
    with one sleeper because both sides resolved to that sleeper. They are now
    {bed_id}_{side}_{type}, like core's foot warmer and core climate entities.
    """
    massage_types = (
        MASSAGE_MODE,
        MASSAGE_FOOT_SPEED,
        MASSAGE_HEAD_SPEED,
        MASSAGE_TIMER,
    )
    sleeper_sides = {
        sleeper.sleeper_id: (bed.id, sleeper.side.value)
        for bed in gateway.beds.values()
        for sleeper in bed.sleepers
    }

    @callback
    def _async_migrator(entity_entry: er.RegistryEntry) -> dict[str, Any] | None:
        old_unique_id = entity_entry.unique_id
        for massage_type in massage_types:
            if not old_unique_id.endswith(f"_{massage_type}"):
                continue
            sleeper_id = old_unique_id.removesuffix(f"_{massage_type}")
            if (found := sleeper_sides.get(sleeper_id)) is None:
                return None
            bed_id, side = found
            new_unique_id = f"{bed_id}_{side}_{massage_type}"
            _LOGGER.debug(
                "Migrating unique_id from [%s] to [%s]", old_unique_id, new_unique_id
            )
            return {"new_unique_id": new_unique_id}
        return None

    await er.async_migrate_entries(hass, entry.entry_id, _async_migrator)
