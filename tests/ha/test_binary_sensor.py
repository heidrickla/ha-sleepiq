"""Presence: one sensor per sleeper, named after them, keyed on their id."""

from asyncsleepiq.consts import Side
from homeassistant.components.binary_sensor import (
    DOMAIN as BINARY_SENSOR_DOMAIN,
    BinarySensorDeviceClass,
)
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_FRIENDLY_NAME,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import (
    BED_NAME,
    BED_NAME_LOWER,
    SLEEPER_L_ID,
    SLEEPER_L_NAME,
    SLEEPER_L_NAME_LOWER,
    SLEEPER_R_NAME_LOWER,
    setup_platform,
)

IN_BED_L = f"binary_sensor.{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_is_in_bed"
IN_BED_R = f"binary_sensor.{BED_NAME_LOWER}_{SLEEPER_R_NAME_LOWER}_is_in_bed"


async def test_presence_is_reported_per_sleeper(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, mock_asyncsleepiq
) -> None:
    """One sleeper is in bed, the other is not, and each is its own entity."""
    await setup_platform(hass, [BINARY_SENSOR_DOMAIN])

    left = hass.states.get(IN_BED_L)
    assert left.state == STATE_ON
    assert left.attributes[ATTR_FRIENDLY_NAME] == (
        f"{BED_NAME} {SLEEPER_L_NAME} is in bed"
    )
    assert left.attributes[ATTR_DEVICE_CLASS] == BinarySensorDeviceClass.OCCUPANCY
    assert hass.states.get(IN_BED_R).state == STATE_OFF

    assert entity_registry.async_get(IN_BED_L).unique_id == f"{SLEEPER_L_ID}_is_in_bed"


async def test_a_sleeper_with_no_name_is_named_by_side(
    hass: HomeAssistant, mock_asyncsleepiq, mock_bed
) -> None:
    """An account that never named the sleeper still gets a usable entity."""
    mock_bed.sleepers[0].name = ""
    mock_bed.sleepers[0].side = Side.LEFT
    await setup_platform(hass, [BINARY_SENSOR_DOMAIN])

    state = hass.states.get(f"binary_sensor.{BED_NAME_LOWER}_left_is_in_bed")
    assert state is not None
    assert state.attributes[ATTR_FRIENDLY_NAME] == f"{BED_NAME} Left is in bed"
