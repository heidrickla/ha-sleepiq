"""The buttons: names, category, and what a refused press says."""

from asyncsleepiq.exceptions import SleepIQAPIException
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID, ATTR_FRIENDLY_NAME, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
import pytest

from .conftest import BED_ID, BED_NAME, BED_NAME_LOWER, setup_platform

CALIBRATE = f"button.{BED_NAME_LOWER}_calibrate"
STOP_PUMP = f"button.{BED_NAME_LOWER}_stop_pump"


async def _press(hass: HomeAssistant, entity_id: str) -> None:
    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )


async def test_the_buttons_are_named_and_categorised(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, mock_asyncsleepiq
) -> None:
    """Calibrate is a setup action; stopping the pump is an operating one."""
    await setup_platform(hass, [BUTTON_DOMAIN])

    calibrate = hass.states.get(CALIBRATE)
    assert calibrate.attributes[ATTR_FRIENDLY_NAME] == f"{BED_NAME} Calibrate"
    assert hass.states.get(STOP_PUMP).attributes[ATTR_FRIENDLY_NAME] == (
        f"{BED_NAME} Stop pump"
    )

    entry = entity_registry.async_get(CALIBRATE)
    assert entry.unique_id == f"{BED_ID}-calibrate"
    assert entry.entity_category is EntityCategory.CONFIG
    assert entity_registry.async_get(STOP_PUMP).unique_id == f"{BED_ID}-stop-pump"
    assert entity_registry.async_get(STOP_PUMP).entity_category is None


async def test_pressing_a_button_reaches_the_bed(
    hass: HomeAssistant, mock_asyncsleepiq, mock_bed
) -> None:
    """Each button calls its own library method."""
    await setup_platform(hass, [BUTTON_DOMAIN])

    await _press(hass, CALIBRATE)
    mock_bed.calibrate.assert_awaited_once()

    await _press(hass, STOP_PUMP)
    mock_bed.stop_pump.assert_awaited_once()


async def test_a_refused_press_is_a_translated_error(
    hass: HomeAssistant, mock_asyncsleepiq, mock_bed
) -> None:
    """The cloud's refusal reaches the user in their own language."""
    await setup_platform(hass, [BUTTON_DOMAIN])
    mock_bed.calibrate.side_effect = SleepIQAPIException(500, "nope")

    with pytest.raises(HomeAssistantError) as err:
        await _press(hass, CALIBRATE)

    assert err.value.translation_key == "write_failed"
    assert err.value.translation_placeholders == {"error": "nope"}
