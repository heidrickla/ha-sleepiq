"""The massage entities: naming, ids, state, writes, refusals, diagnostics."""

from unittest.mock import MagicMock

from asyncsleepiq.consts import Side
from asyncsleepiq.exceptions import SleepIQAPIException
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.components.select import (
    ATTR_OPTION,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    ATTR_ICON,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
import pytest

from custom_components.sleepiq.diagnostics import async_get_config_entry_diagnostics

from .conftest import (
    ADJUSTMENT_URL,
    BED_ID,
    BED_NAME,
    BED_NAME_LOWER,
    SLEEPER_L_NAME,
    SLEEPER_L_NAME_LOWER,
    SLEEPER_R_NAME,
    SLEEPER_R_NAME_LOWER,
    massage_reads,
    setup_platform,
)

MODE_L = f"select.{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_massage_mode"
MODE_R = f"select.{BED_NAME_LOWER}_{SLEEPER_R_NAME_LOWER}_massage_mode"
FOOT_L = f"select.{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_foot_massage_speed"
HEAD_L = f"select.{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_head_massage_speed"
HEAD_R = f"select.{BED_NAME_LOWER}_{SLEEPER_R_NAME_LOWER}_head_massage_speed"
TIMER_L = f"number.{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_massage_timer"
TIMER_R = f"number.{BED_NAME_LOWER}_{SLEEPER_R_NAME_LOWER}_massage_timer"

MASSAGE_PLATFORMS = [SELECT_DOMAIN, NUMBER_DOMAIN]


async def _select(hass: HomeAssistant, entity_id: str, option: str) -> None:
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: entity_id, ATTR_OPTION: option},
        blocking=True,
    )


async def _set_value(hass: HomeAssistant, entity_id: str, value: float) -> None:
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
        blocking=True,
    )


# ------------------------------------------------------------ names and ids


async def test_entities_are_named_by_sleeper_and_keyed_by_side(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, mock_asyncsleepiq
) -> None:
    await setup_platform(hass, MASSAGE_PLATFORMS)

    expected = {
        MODE_L: ("off", f"{BED_NAME} {SLEEPER_L_NAME} massage mode"),
        MODE_R: ("soothe", f"{BED_NAME} {SLEEPER_R_NAME} massage mode"),
        FOOT_L: ("low", f"{BED_NAME} {SLEEPER_L_NAME} foot massage speed"),
        HEAD_L: ("off", f"{BED_NAME} {SLEEPER_L_NAME} head massage speed"),
        TIMER_L: ("12.0", f"{BED_NAME} {SLEEPER_L_NAME} massage timer"),
        TIMER_R: ("57.0", f"{BED_NAME} {SLEEPER_R_NAME} massage timer"),
    }
    for entity_id, (state, name) in expected.items():
        got = hass.states.get(entity_id)
        assert got is not None, entity_id
        assert got.state == state, entity_id
        assert got.attributes[ATTR_FRIENDLY_NAME] == name
        # No icon in the state: icons.json supplies it through the
        # translation key, and the bed base class's mdi:bed must not win.
        assert ATTR_ICON not in got.attributes, entity_id

    assert entity_registry.async_get(MODE_L).unique_id == f"{BED_ID}_L_massage_mode"
    assert entity_registry.async_get(MODE_R).unique_id == f"{BED_ID}_R_massage_mode"
    assert entity_registry.async_get(FOOT_L).unique_id == (
        f"{BED_ID}_L_massage_foot_speed"
    )
    assert entity_registry.async_get(TIMER_R).unique_id == f"{BED_ID}_R_massage_timer"
    assert entity_registry.async_get(MODE_L).translation_key == "massage_mode"
    assert entity_registry.async_get(TIMER_L).translation_key == "massage_timer"


async def test_a_bed_with_one_sleeper_names_the_empty_side_by_position(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, mock_asyncsleepiq, mock_bed
) -> None:
    """Both sides exist, with distinct ids; the empty side is not the sleeper's."""
    mock_bed.sleepers = [mock_bed.sleepers[0]]
    await setup_platform(hass, MASSAGE_PLATFORMS)

    left = hass.states.get(MODE_L)
    right = hass.states.get(f"select.{BED_NAME_LOWER}_right_massage_mode")
    assert left.attributes[ATTR_FRIENDLY_NAME] == (
        f"{BED_NAME} {SLEEPER_L_NAME} massage mode"
    )
    assert right.attributes[ATTR_FRIENDLY_NAME] == f"{BED_NAME} Right massage mode"
    assert right.state == "soothe"
    assert entity_registry.async_get(right.entity_id).unique_id == (
        f"{BED_ID}_R_massage_mode"
    )
    assert hass.states.get(f"number.{BED_NAME_LOWER}_right_massage_timer").state == (
        "57.0"
    )


async def test_the_mode_select_exposes_the_raw_block(
    hass: HomeAssistant, mock_asyncsleepiq
) -> None:
    await setup_platform(hass, [SELECT_DOMAIN])
    attributes = hass.states.get(MODE_L).attributes
    assert attributes["massageTimer"] == 12
    assert attributes["massageMotorStatus"] == 1


# ------------------------------------------------------------------- writes


async def test_selecting_a_mode_sends_wavemode_alone(
    hass: HomeAssistant, mock_asyncsleepiq
) -> None:
    await setup_platform(hass, [SELECT_DOMAIN])
    await _select(hass, MODE_L, "wave")
    mock_asyncsleepiq.put.assert_awaited_once_with(
        ADJUSTMENT_URL, {"waveMode": 3, "side": Side.LEFT}
    )


async def test_the_state_follows_the_beds_readback_after_a_write(
    hass: HomeAssistant, mock_asyncsleepiq, massage_payload
) -> None:
    """A write triggers a refresh; what the bed then reports is the state."""
    await setup_platform(hass, [SELECT_DOMAIN])
    massage_payload["leftSide"]["waveMode"] = 2
    await _select(hass, MODE_L, "revitilize")
    await hass.async_block_till_done()
    assert hass.states.get(MODE_L).state == "revitilize"
    assert len(massage_reads(mock_asyncsleepiq)) == 2


async def test_selecting_a_speed_sends_both_motors_and_the_armed_timer(
    hass: HomeAssistant, mock_asyncsleepiq
) -> None:
    await setup_platform(hass, [SELECT_DOMAIN])

    await _select(hass, FOOT_L, "high")
    mock_asyncsleepiq.put.assert_awaited_with(
        ADJUSTMENT_URL,
        {"footMassageMotor": 3, "headMassageMotor": 0, "massageTimer": 12, "side": "L"},
    )

    # The right side was in a pattern; a speed cancels it and keeps its timer.
    await _select(hass, HEAD_R, "medium")
    mock_asyncsleepiq.put.assert_awaited_with(
        ADJUSTMENT_URL,
        {"footMassageMotor": 0, "headMassageMotor": 2, "massageTimer": 57, "side": "R"},
    )


async def test_setting_the_timer_sends_it_alone_and_shows_it_at_once(
    hass: HomeAssistant, mock_asyncsleepiq
) -> None:
    await setup_platform(hass, [NUMBER_DOMAIN])
    await _set_value(hass, TIMER_L, 20)
    mock_asyncsleepiq.put.assert_awaited_once_with(
        ADJUSTMENT_URL, {"massageTimer": 20, "side": Side.LEFT}
    )
    assert hass.states.get(TIMER_L).state == "20.0"


async def test_a_refused_write_is_a_translated_error_and_changes_nothing(
    hass: HomeAssistant, mock_asyncsleepiq
) -> None:
    await setup_platform(hass, MASSAGE_PLATFORMS)
    mock_asyncsleepiq.put.side_effect = SleepIQAPIException(500, "nope")

    with pytest.raises(HomeAssistantError) as err:
        await _select(hass, MODE_L, "wave")
    assert err.value.translation_key == "massage_write_failed"
    assert err.value.translation_placeholders == {"error": "nope"}
    assert hass.states.get(MODE_L).state == "off"

    with pytest.raises(HomeAssistantError) as err:
        await _set_value(hass, TIMER_L, 30)
    assert err.value.translation_key == "massage_write_failed"
    assert hass.states.get(TIMER_L).state == "12.0"


# -------------------------------------------------------------- diagnostics


async def test_diagnostics_redact_the_account_and_the_household(
    hass: HomeAssistant, mock_asyncsleepiq, mock_bed: MagicMock
) -> None:
    entry = await setup_platform(hass, [SELECT_DOMAIN])
    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["entry"][CONF_USERNAME] == "**REDACTED**"
    assert diag["entry"]["password"] == "**REDACTED**"
    assert diag["last_update_success"]["status"] is True
    bed = diag["beds"][0]
    assert bed["id"] == BED_ID
    assert bed["mac_addr"] == "**REDACTED**"
    assert bed["foundation"]["features"]["hasMassageAndLight"] is True
    assert bed["sleepers"][0]["sleeper_name"] == "**REDACTED**"
    assert bed["sleepers"][0]["sleeper_id"] == mock_bed.sleepers[0].sleeper_id
    assert [m["side"] for m in bed["massage"]] == ["L", "R"]
    assert bed["massage"][0]["timer"] == 12
    assert bed["massage"][1]["mode"] == "soothe"
    assert bed["massage"][1]["raw"]["waveMode"] == 1
