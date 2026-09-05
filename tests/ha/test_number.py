"""Firmness, actuator positions and the comfort timers."""

from asyncsleepiq.consts import CoreTemps, End, FootWarmingTemps, Side
from asyncsleepiq.exceptions import SleepIQAPIException
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_FRIENDLY_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
import pytest

from .conftest import (
    BED_ID,
    BED_NAME,
    BED_NAME_LOWER,
    SLEEPER_L_ID,
    SLEEPER_L_NAME,
    SLEEPER_L_NAME_LOWER,
    SLEEPER_R_NAME_LOWER,
    setup_platform,
)

FIRMNESS_L = f"number.{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_firmness"
HEAD_POSITION = f"number.{BED_NAME_LOWER}_left_head_position"
FOOT_POSITION = f"number.{BED_NAME_LOWER}_foot_position"
FOOT_WARMING_TIMER = (
    f"number.{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_foot_warming_timer"
)
CORE_CLIMATE_TIMER = (
    f"number.{BED_NAME_LOWER}_{SLEEPER_R_NAME_LOWER}_core_climate_timer"
)


async def _set_value(hass: HomeAssistant, entity_id: str, value: float) -> None:
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
        blocking=True,
    )


async def test_the_numbers_are_named_and_keyed(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, mock_asyncsleepiq
) -> None:
    """Firmness follows the sleeper; a position follows the side and the end."""
    await setup_platform(hass, [NUMBER_DOMAIN])

    firmness = hass.states.get(FIRMNESS_L)
    assert firmness.state == "40.0"
    assert firmness.attributes[ATTR_FRIENDLY_NAME] == (
        f"{BED_NAME} {SLEEPER_L_NAME} firmness"
    )
    assert entity_registry.async_get(FIRMNESS_L).unique_id == (
        f"{SLEEPER_L_ID}_firmness"
    )

    head = hass.states.get(HEAD_POSITION)
    assert head.state == "45.0"
    assert head.attributes[ATTR_FRIENDLY_NAME] == f"{BED_NAME} Left head position"
    assert entity_registry.async_get(HEAD_POSITION).unique_id == (
        f"{BED_ID}_{Side.LEFT.value}_{End.HEAD}"
    )

    # A foundation that reports no side names the position without one.
    foot = hass.states.get(FOOT_POSITION)
    assert foot.state == "0.0"
    assert foot.attributes[ATTR_FRIENDLY_NAME] == f"{BED_NAME} Foot position"

    assert hass.states.get(FOOT_WARMING_TIMER).state == "60.0"
    assert hass.states.get(CORE_CLIMATE_TIMER).attributes[ATTR_FRIENDLY_NAME] == (
        f"{BED_NAME} Sleeper R core climate timer"
    )


async def test_an_actuator_with_no_side_is_named_and_keyed_without_one(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, mock_asyncsleepiq, mock_bed
) -> None:
    """A foundation that reports no side at all still gets one usable entity."""
    actuator = mock_bed.foundation.actuators[0]
    actuator.side = None
    await setup_platform(hass, [NUMBER_DOMAIN])

    position = hass.states.get(f"number.{BED_NAME_LOWER}_position")
    assert position is not None
    assert position.attributes[ATTR_FRIENDLY_NAME] == f"{BED_NAME} Position"
    assert entity_registry.async_get(position.entity_id).unique_id == (
        f"{BED_ID}_{End.HEAD}"
    )


async def test_setting_firmness_and_position_reaches_the_bed(
    hass: HomeAssistant, mock_asyncsleepiq, mock_bed
) -> None:
    """The write is sent and the new value shown without waiting for a poll."""
    await setup_platform(hass, [NUMBER_DOMAIN])

    await _set_value(hass, FIRMNESS_L, 45)
    mock_bed.sleepers[0].set_sleepnumber.assert_awaited_once_with(45)
    assert hass.states.get(FIRMNESS_L).state == "45.0"

    await _set_value(hass, HEAD_POSITION, 60)
    mock_bed.foundation.actuators[0].set_position.assert_awaited_once_with(60)
    assert hass.states.get(HEAD_POSITION).state == "60.0"


async def test_an_armed_foot_warmer_is_restarted_with_the_new_time(
    hass: HomeAssistant, mock_asyncsleepiq, mock_bed
) -> None:
    """Changing the timer of a running warmer re-sends the temperature with it."""
    foot_warmer = mock_bed.foundation.foot_warmers[0]
    foot_warmer.temperature = FootWarmingTemps.MEDIUM.value
    core_climate = mock_bed.foundation.core_climates[0]
    core_climate.temperature = CoreTemps.HEATING_PUSH_LOW.value
    await setup_platform(hass, [NUMBER_DOMAIN])

    await _set_value(hass, FOOT_WARMING_TIMER, 120)
    foot_warmer.turn_on.assert_awaited_once_with(FootWarmingTemps.MEDIUM, 120)
    assert foot_warmer.timer == 120

    await _set_value(hass, CORE_CLIMATE_TIMER, 300)
    core_climate.turn_on.assert_awaited_once_with(CoreTemps.HEATING_PUSH_LOW, 300)
    assert core_climate.timer == 300


async def test_an_idle_timer_is_stored_without_starting_anything(
    hass: HomeAssistant, mock_asyncsleepiq, mock_bed
) -> None:
    """Setting the timer of a warmer that is off must not turn it on."""
    await setup_platform(hass, [NUMBER_DOMAIN])
    foot_warmer = mock_bed.foundation.foot_warmers[0]

    await _set_value(hass, FOOT_WARMING_TIMER, 90)

    foot_warmer.turn_on.assert_not_awaited()
    assert foot_warmer.timer == 90


async def test_a_refused_write_is_a_translated_error(
    hass: HomeAssistant, mock_asyncsleepiq, mock_bed
) -> None:
    """The cloud's refusal is one message; a rejected value is another."""
    await setup_platform(hass, [NUMBER_DOMAIN])
    sleeper = mock_bed.sleepers[0]

    sleeper.set_sleepnumber.side_effect = SleepIQAPIException(500, "nope")
    with pytest.raises(HomeAssistantError) as err:
        await _set_value(hass, FIRMNESS_L, 45)
    assert err.value.translation_key == "write_failed"
    assert hass.states.get(FIRMNESS_L).state == "40.0"

    sleeper.set_sleepnumber.side_effect = ValueError("Invalid SleepNumber")
    with pytest.raises(ServiceValidationError) as err:
        await _set_value(hass, FIRMNESS_L, 45)
    assert err.value.translation_key == "invalid_value"
    assert err.value.translation_placeholders == {"error": "Invalid SleepNumber"}
