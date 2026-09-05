"""The outlet lights: naming by outlet, switching, and a refused write."""

from asyncsleepiq.exceptions import SleepIQTimeoutException
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
import pytest

from .conftest import BED_ID, BED_NAME, BED_NAME_LOWER, setup_platform

LIGHT = f"light.{BED_NAME_LOWER}_light_1"


async def _call(hass: HomeAssistant, service: str) -> None:
    await hass.services.async_call(
        LIGHT_DOMAIN, service, {ATTR_ENTITY_ID: LIGHT}, blocking=True
    )


async def test_the_light_is_named_after_its_outlet(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, mock_asyncsleepiq
) -> None:
    """A bed can have four outlets, so the number is part of the name."""
    await setup_platform(hass, [LIGHT_DOMAIN])

    state = hass.states.get(LIGHT)
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_FRIENDLY_NAME] == f"{BED_NAME} Light 1"
    assert entity_registry.async_get(LIGHT).unique_id == f"{BED_ID}-light-1"


async def test_switching_the_light_shows_the_new_state_at_once(
    hass: HomeAssistant, mock_asyncsleepiq, mock_bed
) -> None:
    """The library flips its own flag, so the entity can follow immediately."""
    await setup_platform(hass, [LIGHT_DOMAIN])
    light = mock_bed.foundation.lights[0]

    async def _turn_on() -> None:
        light.is_on = True

    async def _turn_off() -> None:
        light.is_on = False

    light.turn_on.side_effect = _turn_on
    light.turn_off.side_effect = _turn_off

    await _call(hass, SERVICE_TURN_ON)
    light.turn_on.assert_awaited_once()
    assert hass.states.get(LIGHT).state == STATE_ON

    await _call(hass, SERVICE_TURN_OFF)
    light.turn_off.assert_awaited_once()
    assert hass.states.get(LIGHT).state == STATE_OFF


async def test_a_refused_write_is_a_translated_error(
    hass: HomeAssistant, mock_asyncsleepiq, mock_bed
) -> None:
    """A timeout on the write is reported, not swallowed."""
    await setup_platform(hass, [LIGHT_DOMAIN])
    mock_bed.foundation.lights[0].turn_on.side_effect = SleepIQTimeoutException("slow")

    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, SERVICE_TURN_ON)

    assert err.value.translation_key == "write_failed"
    assert hass.states.get(LIGHT).state == STATE_OFF
