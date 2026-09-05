"""Foundation presets, foot warming and core climate."""

from asyncsleepiq.consts import BED_PRESETS, CoreTemps, FootWarmingTemps, Side
from asyncsleepiq.exceptions import SleepIQAPIException
from homeassistant.components.select import (
    ATTR_OPTION,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_FRIENDLY_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
import pytest

from .conftest import (
    BED_ID,
    BED_NAME,
    BED_NAME_LOWER,
    PRESET_STATE,
    SLEEPER_L_NAME,
    SLEEPER_L_NAME_LOWER,
    SLEEPER_R_NAME_LOWER,
    make_core_climate,
    make_foot_warmer,
    setup_platform,
)

PRESET = f"select.{BED_NAME_LOWER}_foundation_preset"
FOOT_WARMER = f"select.{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_foot_warmer"
CORE_CLIMATE = f"select.{BED_NAME_LOWER}_{SLEEPER_R_NAME_LOWER}_core_climate"


async def _select(hass: HomeAssistant, entity_id: str, option: str) -> None:
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: entity_id, ATTR_OPTION: option},
        blocking=True,
    )


async def test_the_selects_are_named_and_keyed(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, mock_asyncsleepiq
) -> None:
    """The preset belongs to the bed; the comfort hardware to a side."""
    await setup_platform(hass, [SELECT_DOMAIN])

    preset = hass.states.get(PRESET)
    assert preset.state == PRESET_STATE
    assert preset.attributes[ATTR_FRIENDLY_NAME] == f"{BED_NAME} Foundation preset"
    assert preset.attributes["options"] == list(BED_PRESETS)
    assert entity_registry.async_get(PRESET).unique_id == f"{BED_ID}_preset"

    warmer = hass.states.get(FOOT_WARMER)
    assert warmer.state == "off"
    assert warmer.attributes[ATTR_FRIENDLY_NAME] == (
        f"{BED_NAME} {SLEEPER_L_NAME} foot warmer"
    )
    assert entity_registry.async_get(FOOT_WARMER).unique_id == (
        f"{BED_ID}_{Side.LEFT.value}_foot_warmer"
    )

    climate = hass.states.get(CORE_CLIMATE)
    assert climate.state == "off"
    assert climate.attributes[ATTR_FRIENDLY_NAME] == (
        f"{BED_NAME} Sleeper R core climate"
    )
    assert entity_registry.async_get(CORE_CLIMATE).unique_id == (
        f"{BED_ID}_{Side.RIGHT.value}_core_climate"
    )


async def test_a_bed_with_one_sleeper_gets_both_sides_of_the_comfort_hardware(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, mock_asyncsleepiq, mock_bed
) -> None:
    """The side with nobody on it is a side, not a copy of the other one.

    Core keys these two on the sleeper, and a side with no sleeper registered
    falls back to the first one, so both sides ask for the same unique id and
    Home Assistant keeps only the first entity. Keyed on the bed and the side,
    the bed gets all four.
    """
    mock_bed.sleepers = [mock_bed.sleepers[0]]
    mock_bed.foundation.foot_warmers = [
        make_foot_warmer(Side.LEFT),
        make_foot_warmer(Side.RIGHT),
    ]
    mock_bed.foundation.core_climates = [
        make_core_climate(Side.LEFT),
        make_core_climate(Side.RIGHT),
    ]

    await setup_platform(hass, [SELECT_DOMAIN])

    expected = {
        f"select.{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_foot_warmer": (
            f"{BED_ID}_{Side.LEFT.value}_foot_warmer"
        ),
        f"select.{BED_NAME_LOWER}_right_foot_warmer": (
            f"{BED_ID}_{Side.RIGHT.value}_foot_warmer"
        ),
        f"select.{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_core_climate": (
            f"{BED_ID}_{Side.LEFT.value}_core_climate"
        ),
        f"select.{BED_NAME_LOWER}_right_core_climate": (
            f"{BED_ID}_{Side.RIGHT.value}_core_climate"
        ),
    }
    for entity_id, unique_id in expected.items():
        assert hass.states.get(entity_id) is not None, entity_id
        assert entity_registry.async_get(entity_id).unique_id == unique_id
    assert len(set(expected.values())) == len(expected)


async def test_a_split_foundation_names_its_presets_by_side(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, mock_asyncsleepiq, mock_bed
) -> None:
    """Two preset entities need two names and two ids."""
    mock_bed.foundation.presets[0].side = Side.LEFT
    await setup_platform(hass, [SELECT_DOMAIN])

    left = hass.states.get(f"select.{BED_NAME_LOWER}_left_foundation_preset")
    assert left is not None
    assert left.attributes[ATTR_FRIENDLY_NAME] == f"{BED_NAME} Left foundation preset"
    assert entity_registry.async_get(left.entity_id).unique_id == (
        f"{BED_ID}_preset_{Side.LEFT.value}"
    )


async def test_selecting_a_preset_reaches_the_bed(
    hass: HomeAssistant, mock_asyncsleepiq, mock_bed
) -> None:
    """The choice is sent and shown without waiting for a poll."""
    await setup_platform(hass, [SELECT_DOMAIN])

    await _select(hass, PRESET, "Zero G")

    mock_bed.foundation.presets[0].set_preset.assert_awaited_once_with("Zero G")
    assert hass.states.get(PRESET).state == "Zero G"


async def test_foot_warming_turns_on_and_off(
    hass: HomeAssistant, mock_asyncsleepiq, mock_bed
) -> None:
    """A temperature starts the warmer with its stored time; off stops it."""
    await setup_platform(hass, [SELECT_DOMAIN])
    foot_warmer = mock_bed.foundation.foot_warmers[0]

    async def _turn_on(temperature: FootWarmingTemps, time: int) -> None:
        foot_warmer.temperature = temperature.value

    foot_warmer.turn_on.side_effect = _turn_on

    await _select(hass, FOOT_WARMER, "medium")
    foot_warmer.turn_on.assert_awaited_once_with(FootWarmingTemps.MEDIUM, 60)
    assert hass.states.get(FOOT_WARMER).state == "medium"

    await _select(hass, FOOT_WARMER, "off")
    foot_warmer.turn_off.assert_awaited_once()


async def test_core_climate_turns_on_and_off(
    hass: HomeAssistant, mock_asyncsleepiq, mock_bed
) -> None:
    """The Home Assistant option names map onto the library's own."""
    await setup_platform(hass, [SELECT_DOMAIN])
    core_climate = mock_bed.foundation.core_climates[0]

    async def _turn_on(temperature: CoreTemps, time: int) -> None:
        core_climate.temperature = temperature.value

    core_climate.turn_on.side_effect = _turn_on

    await _select(hass, CORE_CLIMATE, "cooling_high")
    core_climate.turn_on.assert_awaited_once_with(CoreTemps.COOLING_PULL_HIGH, 240)
    assert hass.states.get(CORE_CLIMATE).state == "cooling_high"

    await _select(hass, CORE_CLIMATE, "off")
    core_climate.turn_off.assert_awaited_once()


async def test_a_refused_write_is_a_translated_error(
    hass: HomeAssistant, mock_asyncsleepiq, mock_bed
) -> None:
    """Every write path on this platform reports the cloud's refusal."""
    await setup_platform(hass, [SELECT_DOMAIN])
    mock_bed.foundation.presets[0].set_preset.side_effect = SleepIQAPIException(
        500, "nope"
    )
    mock_bed.foundation.foot_warmers[0].turn_on.side_effect = SleepIQAPIException(
        500, "nope"
    )
    mock_bed.foundation.core_climates[0].turn_on.side_effect = SleepIQAPIException(
        500, "nope"
    )

    for entity_id, option in (
        (PRESET, "Zero G"),
        (FOOT_WARMER, "high"),
        (CORE_CLIMATE, "heating_low"),
    ):
        with pytest.raises(HomeAssistantError) as err:
            await _select(hass, entity_id, option)
        assert err.value.translation_key == "write_failed"

    assert hass.states.get(PRESET).state == PRESET_STATE
    assert hass.states.get(FOOT_WARMER).state == "off"
    assert hass.states.get(CORE_CLIMATE).state == "off"
