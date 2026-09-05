"""The readings: one set per sleeper, named after them, with the right classes."""

from homeassistant.components.sensor import (
    ATTR_STATE_CLASS,
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import ATTR_DEVICE_CLASS, ATTR_FRIENDLY_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import (
    BED_NAME,
    BED_NAME_LOWER,
    SLEEPER_L_ID,
    SLEEPER_L_NAME,
    SLEEPER_L_NAME_LOWER,
    SLEEPER_R_ID,
    SLEEPER_R_NAME_LOWER,
    setup_platform,
)

PRESSURE_L = f"sensor.{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_pressure"
SLEEP_NUMBER_L = f"sensor.{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_sleepnumber"
SCORE_L = f"sensor.{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_sleep_score"
DURATION_L = f"sensor.{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_sleep_duration"
HEART_RATE_L = f"sensor.{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_average_heart_rate"
BREATHING_L = f"sensor.{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_average_respiratory_rate"
HRV_L = f"sensor.{BED_NAME_LOWER}_{SLEEPER_L_NAME_LOWER}_heart_rate_variability"
PRESSURE_R = f"sensor.{BED_NAME_LOWER}_{SLEEPER_R_NAME_LOWER}_pressure"


async def test_every_sleeper_gets_the_full_set_of_readings(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, mock_asyncsleepiq
) -> None:
    """Bed status and last night's sleep health, per sleeper, named after them."""
    await setup_platform(hass, [SENSOR_DOMAIN])

    assert hass.states.get(PRESSURE_L).state == "1000"
    assert hass.states.get(PRESSURE_L).attributes[ATTR_FRIENDLY_NAME] == (
        f"{BED_NAME} {SLEEPER_L_NAME} pressure"
    )
    assert hass.states.get(SLEEP_NUMBER_L).state == "40"
    assert hass.states.get(SCORE_L).state == "85"
    assert hass.states.get(DURATION_L).state == "8.0"
    assert hass.states.get(HEART_RATE_L).state == "60"
    assert hass.states.get(BREATHING_L).state == "14"
    assert hass.states.get(HRV_L).state == "68"
    # The other side is its own set of entities, not a second name for these.
    assert hass.states.get(PRESSURE_R).state == "1400"

    assert entity_registry.async_get(PRESSURE_L).unique_id == (
        f"{SLEEPER_L_ID}_pressure"
    )
    assert entity_registry.async_get(PRESSURE_R).unique_id == (
        f"{SLEEPER_R_ID}_pressure"
    )


async def test_the_readings_carry_their_classes(
    hass: HomeAssistant, mock_asyncsleepiq
) -> None:
    """Duration where there is one; measurement everywhere."""
    await setup_platform(hass, [SENSOR_DOMAIN])

    duration = hass.states.get(DURATION_L)
    assert duration.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.DURATION
    assert duration.attributes[ATTR_STATE_CLASS] == SensorStateClass.MEASUREMENT
    assert hass.states.get(HRV_L).attributes[ATTR_DEVICE_CLASS] == (
        SensorDeviceClass.DURATION
    )
    # The bed's own pressure figure is a proprietary unitless number.
    assert ATTR_DEVICE_CLASS not in hass.states.get(PRESSURE_L).attributes


async def test_a_night_without_data_reads_unknown(
    hass: HomeAssistant, mock_asyncsleepiq, mock_bed
) -> None:
    """No sleep session recorded is unknown, not zero."""
    for sleeper in mock_bed.sleepers:
        sleeper.sleep_data = None
    await setup_platform(hass, [SENSOR_DOMAIN])

    assert hass.states.get(SCORE_L).state == "unknown"
    assert hass.states.get(DURATION_L).state == "unknown"
    assert hass.states.get(HRV_L).state == "unknown"
