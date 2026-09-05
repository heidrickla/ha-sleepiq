"""Pause mode: naming, both directions, and a refused write."""

from asyncsleepiq.exceptions import SleepIQAPIException
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
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

PAUSE = f"switch.{BED_NAME_LOWER}_pause_mode"


async def _call(hass: HomeAssistant, service: str) -> None:
    await hass.services.async_call(
        SWITCH_DOMAIN, service, {ATTR_ENTITY_ID: PAUSE}, blocking=True
    )


async def test_pause_mode_is_named_and_keyed_on_the_bed(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, mock_asyncsleepiq
) -> None:
    """Privacy mode is a bed setting, not a sleeper's."""
    await setup_platform(hass, [SWITCH_DOMAIN])

    state = hass.states.get(PAUSE)
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_FRIENDLY_NAME] == f"{BED_NAME} Pause mode"
    assert entity_registry.async_get(PAUSE).unique_id == f"{BED_ID}-pause-mode"


async def test_switching_pause_mode_reaches_the_bed(
    hass: HomeAssistant, mock_asyncsleepiq, mock_bed
) -> None:
    """Both directions are sent and shown straight away."""
    await setup_platform(hass, [SWITCH_DOMAIN])

    async def _set(mode: bool) -> None:
        mock_bed.paused = mode

    mock_bed.set_pause_mode.side_effect = _set

    await _call(hass, SERVICE_TURN_ON)
    mock_bed.set_pause_mode.assert_awaited_with(True)
    assert hass.states.get(PAUSE).state == STATE_ON

    await _call(hass, SERVICE_TURN_OFF)
    mock_bed.set_pause_mode.assert_awaited_with(False)
    assert hass.states.get(PAUSE).state == STATE_OFF


async def test_a_refused_write_is_a_translated_error(
    hass: HomeAssistant, mock_asyncsleepiq, mock_bed
) -> None:
    """The bed keeps its last known state when the cloud refuses."""
    await setup_platform(hass, [SWITCH_DOMAIN])
    mock_bed.set_pause_mode.side_effect = SleepIQAPIException(500, "nope")

    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, SERVICE_TURN_ON)

    assert err.value.translation_key == "write_failed"
    assert hass.states.get(PAUSE).state == STATE_OFF
