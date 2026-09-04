"""Setup, its failures, polling, and the unique id migration.

Vendored from core's tests/components/sleepiq/test_init.py at tag 2026.8.2
where it applies, plus the two behaviours this repository adds on top: a login
failure during a poll starts reauth instead of logging a traceback every
minute, and massage entities created under the sleeper-keyed unique ids of the
first release are migrated to side-keyed ones.
"""

from unittest.mock import MagicMock, patch

from asyncsleepiq import (
    SleepIQAPIException,
    SleepIQLoginException,
    SleepIQTimeoutException,
)
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import CONF_USERNAME, PRESSURE, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util.dt import utcnow
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.sleepiq.const import (
    DOMAIN,
    IS_IN_BED,
    MASSAGE_MODE,
    MASSAGE_TIMER,
    SLEEP_NUMBER,
)
from custom_components.sleepiq.coordinator import UPDATE_INTERVAL

from .conftest import (
    BED_ID,
    BED_NAME_LOWER,
    SLEEPER_L_ID,
    SLEEPER_L_NAME,
    SLEEPER_L_NAME_LOWER,
    SLEEPIQ_CONFIG,
    setup_platform,
)

MODE_L = f"select.{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_massage_mode"


async def test_unload_entry(hass: HomeAssistant, mock_asyncsleepiq) -> None:
    """Test unloading the SleepIQ entry."""
    entry = await setup_platform(hass, ["select"])
    assert entry.state is ConfigEntryState.LOADED
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get(MODE_L).state == STATE_UNAVAILABLE


async def test_entry_setup_login_error(hass: HomeAssistant, mock_asyncsleepiq) -> None:
    """A rejected login is an auth failure, which starts reauth, not a retry."""
    mock_asyncsleepiq.login.side_effect = SleepIQLoginException
    entry = await setup_platform(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


async def test_entry_setup_timeout_error(
    hass: HomeAssistant, mock_asyncsleepiq
) -> None:
    """A timeout at login is retried."""
    mock_asyncsleepiq.login.side_effect = SleepIQTimeoutException
    entry = await setup_platform(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_api_error(hass: HomeAssistant, mock_asyncsleepiq) -> None:
    """An API error while reading the beds is retried."""
    mock_asyncsleepiq.init_beds.side_effect = SleepIQAPIException(500, "boom")
    entry = await setup_platform(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_api_timeout(hass: HomeAssistant, mock_asyncsleepiq) -> None:
    """A timeout while reading the beds is retried."""
    mock_asyncsleepiq.init_beds.side_effect = SleepIQTimeoutException
    entry = await setup_platform(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_update_interval(hass: HomeAssistant, mock_asyncsleepiq) -> None:
    """Bed status and the massage block are both read on every poll."""
    await setup_platform(hass, ["select"])
    assert mock_asyncsleepiq.fetch_bed_statuses.call_count == 1
    assert mock_asyncsleepiq.get.call_count == 1

    async_fire_time_changed(hass, utcnow() + UPDATE_INTERVAL)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_asyncsleepiq.fetch_bed_statuses.call_count == 2
    assert mock_asyncsleepiq.get.call_count == 2
    mock_asyncsleepiq.get.assert_called_with(f"bed/{BED_ID}/foundation/massage")


async def test_a_login_failure_while_polling_starts_reauth(
    hass: HomeAssistant, mock_asyncsleepiq
) -> None:
    """The library re-logs in on a 401; if that fails, the user is asked, once."""
    await setup_platform(hass, ["select"])
    assert hass.states.get(MODE_L).state == "off"

    mock_asyncsleepiq.fetch_bed_statuses.side_effect = SleepIQLoginException(
        "Incorrect username or password"
    )
    # The scheduled refresh runs as a background task; wait for it.
    async_fire_time_changed(hass, utcnow() + UPDATE_INTERVAL)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert hass.states.get(MODE_L).state == STATE_UNAVAILABLE
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


async def test_an_api_error_while_polling_marks_entities_unavailable_then_recovers(
    hass: HomeAssistant, mock_asyncsleepiq
) -> None:
    """A failed massage read takes the coordinator down until the next good poll."""
    await setup_platform(hass, ["select"])

    mock_asyncsleepiq.get.side_effect = SleepIQAPIException(500, "boom")
    async_fire_time_changed(hass, utcnow() + UPDATE_INTERVAL)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(MODE_L).state == STATE_UNAVAILABLE
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)

    mock_asyncsleepiq.get.side_effect = None
    async_fire_time_changed(hass, utcnow() + 2 * UPDATE_INTERVAL)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(MODE_L).state == "off"


async def test_a_bed_without_the_massage_board_gets_no_massage_entities(
    hass: HomeAssistant, mock_asyncsleepiq, mock_bed: MagicMock
) -> None:
    """No board, no controls, and no request for a block the bed does not have."""
    mock_bed.foundation.features["hasMassageAndLight"] = False
    await setup_platform(hass, ["select", "number"])

    assert not [s for s in hass.states.async_all() if "massage" in s.entity_id]
    mock_asyncsleepiq.get.assert_not_called()


async def test_unique_id_migration(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, mock_asyncsleepiq
) -> None:
    """Core's migration of the sensor unique ids still runs (core's own test)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=SLEEPIQ_CONFIG,
        unique_id=SLEEPIQ_CONFIG[CONF_USERNAME].lower(),
    )
    entry.add_to_hass(hass)
    old_ids = {
        sensor_type: f"{BED_ID}_{SLEEPER_L_NAME}_{sensor_type}"
        for sensor_type in (IS_IN_BED, PRESSURE, SLEEP_NUMBER)
    }
    for sensor_type, old_id in old_ids.items():
        entity_registry.async_get_or_create(
            "sensor",
            DOMAIN,
            old_id,
            suggested_object_id=f"old_{sensor_type}",
            config_entry=entry,
        )

    with patch("custom_components.sleepiq.PLATFORMS", []):
        assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    for sensor_type in old_ids:
        assert entity_registry.async_get(f"sensor.old_{sensor_type}").unique_id == (
            f"{SLEEPER_L_ID}_{sensor_type}"
        )


async def test_massage_unique_ids_move_from_the_sleeper_to_the_side(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, mock_asyncsleepiq
) -> None:
    """An entity registered under the first release's id keeps its entity id."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=SLEEPIQ_CONFIG,
        unique_id=SLEEPIQ_CONFIG[CONF_USERNAME].lower(),
    )
    entry.add_to_hass(hass)
    entity_registry.async_get_or_create(
        "select",
        DOMAIN,
        f"{SLEEPER_L_ID}_{MASSAGE_MODE}",
        suggested_object_id="old_mode",
        config_entry=entry,
    )
    entity_registry.async_get_or_create(
        "number",
        DOMAIN,
        f"{SLEEPER_L_ID}_{MASSAGE_TIMER}",
        suggested_object_id="old_timer",
        config_entry=entry,
    )
    # Something that is not a massage id and must be left alone.
    entity_registry.async_get_or_create(
        "light", DOMAIN, f"{BED_ID}-light-1", config_entry=entry
    )

    with patch("custom_components.sleepiq.PLATFORMS", ["select", "number"]):
        assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert entity_registry.async_get("select.old_mode").unique_id == (
        f"{BED_ID}_L_{MASSAGE_MODE}"
    )
    assert entity_registry.async_get("number.old_timer").unique_id == (
        f"{BED_ID}_L_{MASSAGE_TIMER}"
    )
    assert entity_registry.async_get_entity_id("light", DOMAIN, f"{BED_ID}-light-1")
    # The migrated entities are the live ones, not orphans beside new copies.
    assert hass.states.get("select.old_mode").state == "off"
    assert hass.states.get("number.old_timer").state == "12.0"
    assert hass.states.get(MODE_L) is None
