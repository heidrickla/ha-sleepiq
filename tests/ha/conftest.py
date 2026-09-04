"""Fixtures for the Home Assistant layer tests.

These run against Home Assistant, on Linux, in CI - not on a Windows
workstation, where the harness blocks sockets and the ProactorEventLoop needs a
local socket pair for its own self-pipe. They skip when the harness is absent,
so the pure suite one level up still runs on a bare checkout.

THIS CONFTEST LIVES IN ITS OWN DIRECTORY ON PURPOSE. Its autouse fixture pulls
in Home Assistant machinery, and a conftest applies to everything at or below
its directory; in tests/ it would attach to the pure tests and error them all.

The bed fixtures follow core's tests/components/sleepiq/conftest.py at tag
2026.8.2, cut down to what the vendored platforms need to load, plus a
foundation that reports the massage board and a client whose GET answers the
massage endpoint.
"""

from __future__ import annotations

from collections.abc import Generator
from copy import deepcopy
from typing import Any
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from asyncsleepiq import (
    BED_PRESETS,
    Side,
    SleepData,
    SleepIQBed,
    SleepIQFoundation,
    SleepIQLight,
    SleepIQPreset,
    SleepIQSleeper,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sleepiq.const import DOMAIN

BED_ID = "123456"
BED_NAME = "Test Bed"
BED_NAME_LOWER = BED_NAME.lower().replace(" ", "_")
SLEEPER_L_ID = "98765"
SLEEPER_R_ID = "43219"
SLEEPER_L_NAME = "SleeperL"
SLEEPER_R_NAME = "Sleeper R"
SLEEPER_L_NAME_LOWER = SLEEPER_L_NAME.lower().replace(" ", "_")
SLEEPER_R_NAME_LOWER = SLEEPER_R_NAME.lower().replace(" ", "_")
PRESET_STATE = "Flat"

SLEEPIQ_CONFIG = {
    CONF_USERNAME: "user@email.com",
    CONF_PASSWORD: "password",
}

# What GET bed/{id}/foundation/massage answers: the left side running its foot
# motor on low with 12 minutes armed, the right side in the Smooth pattern
# counting down from 60.
MASSAGE_PAYLOAD: dict[str, Any] = {
    "leftSide": {
        "footMassageMotorSpeed": 1,
        "headMassageMotorSpeed": 0,
        "waveMode": 0,
        "massageTimer": 12,
        "massageMotorStatus": 1,
    },
    "rightSide": {
        "footMassageMotorSpeed": 0,
        "headMassageMotorSpeed": 0,
        "waveMode": 1,
        "massageTimer": 57,
        "massageMotorStatus": 0,
    },
}

ADJUSTMENT_URL = f"bed/{BED_ID}/foundation/adjustment"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Required for Home Assistant to load a custom component in tests."""
    return


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "custom_components.sleepiq.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture
def mock_bed() -> MagicMock:
    """A bed with two sleepers, one light, one preset and the massage board."""
    bed = create_autospec(SleepIQBed)
    bed.name = BED_NAME
    bed.id = BED_ID
    bed.mac_addr = "12:34:56:78:AB:CD"
    bed.model = "C10"
    bed.paused = False
    sleeper_l = create_autospec(SleepIQSleeper)
    sleeper_r = create_autospec(SleepIQSleeper)
    bed.sleepers = [sleeper_l, sleeper_r]

    sleeper_l.side = Side.LEFT
    sleeper_l.name = SLEEPER_L_NAME
    sleeper_l.in_bed = True
    sleeper_l.sleep_number = 40
    sleeper_l.pressure = 1000
    sleeper_l.sleeper_id = SLEEPER_L_ID
    sleeper_l.sleep_data = SleepData(
        duration=28800, sleep_score=85, heart_rate=60, respiratory_rate=14, hrv=68
    )

    sleeper_r.side = Side.RIGHT
    sleeper_r.name = SLEEPER_R_NAME
    sleeper_r.in_bed = False
    sleeper_r.sleep_number = 80
    sleeper_r.pressure = 1400
    sleeper_r.sleeper_id = SLEEPER_R_ID
    sleeper_r.sleep_data = SleepData(
        duration=25200, sleep_score=78, heart_rate=65, respiratory_rate=15, hrv=72
    )

    bed.foundation = create_autospec(SleepIQFoundation)
    bed.foundation.type = "splitKing"
    # fsBoardFeatures = 7 on the verified bed: single board, massage and
    # light, foot control.
    bed.foundation.features = {
        "boardIsASingle": True,
        "hasMassageAndLight": True,
        "hasFootControl": True,
        "hasFootWarming": False,
        "hasUnderbedLight": True,
        "leftUnderbedLightPMW": False,
        "rightUnderbedLightPMW": False,
    }
    light = create_autospec(SleepIQLight)
    light.outlet_id = 1
    light.is_on = False
    bed.foundation.lights = [light]

    preset = create_autospec(SleepIQPreset)
    preset.preset = PRESET_STATE
    preset.side = Side.NONE
    preset.side_full = "Right"
    preset.options = BED_PRESETS
    bed.foundation.presets = [preset]

    bed.foundation.actuators = []
    bed.foundation.foot_warmers = []
    bed.foundation.core_climates = []
    return bed


@pytest.fixture
def mock_asyncsleepiq(mock_bed: MagicMock) -> Generator[MagicMock]:
    """Replace the library client where setup constructs it.

    The client is also the API: massage reads go through client.get and
    writes through client.put, both recorded here rather than sent.
    """
    with patch("custom_components.sleepiq.AsyncSleepIQ", autospec=True) as mock:
        client = mock.return_value
        client.beds = {BED_ID: mock_bed}
        client.get.return_value = deepcopy(MASSAGE_PAYLOAD)
        yield client


async def setup_platform(
    hass: HomeAssistant, platforms: list[str] | None = None
) -> MockConfigEntry:
    """Add the account's config entry and, when platforms are given, load it."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        data=SLEEPIQ_CONFIG,
        unique_id=SLEEPIQ_CONFIG[CONF_USERNAME].lower(),
    )
    mock_entry.add_to_hass(hass)

    if platforms is not None:
        with patch("custom_components.sleepiq.PLATFORMS", platforms):
            assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

    return mock_entry
