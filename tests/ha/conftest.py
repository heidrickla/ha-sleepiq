"""Fixtures for the Home Assistant layer tests.

These run against Home Assistant. CI runs them on Linux; on a Windows
workstation two things are shimmed below so the same suite runs there too.
They skip when the harness is absent, so the pure suite one level up still
runs on a bare checkout.

THIS CONFTEST LIVES IN ITS OWN DIRECTORY ON PURPOSE. Its autouse fixture pulls
in Home Assistant machinery, and a conftest applies to everything at or below
its directory; in tests/ it would attach to the pure tests and error them all.

The bed fixtures follow core's tests/components/sleepiq/conftest.py at tag
2026.8.2, cut down to what the vendored platforms need to load, plus a
foundation that reports the massage board and a client whose GET answers both
the account's bed list and the massage endpoint.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from copy import deepcopy
import socket
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from asyncsleepiq.actuator import SleepIQActuator
from asyncsleepiq.bed import SleepIQBed
from asyncsleepiq.consts import BED_PRESETS, CoreTemps, End, FootWarmingTemps, Side
from asyncsleepiq.core_climate import SleepIQCoreClimate
from asyncsleepiq.foot_warmer import SleepIQFootWarmer
from asyncsleepiq.foundation import SleepIQFoundation
from asyncsleepiq.light import SleepIQLight
from asyncsleepiq.preset import SleepIQPreset
from asyncsleepiq.sleeper import SleepData, SleepIQSleeper
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sleepiq.const import DOMAIN

if sys.platform == "win32":
    # ProactorEventLoop builds its self-pipe from socket.socketpair(), which
    # the harness's socket block refuses, so every test errors before it runs.
    # Hand socketpair the real socket class for the length of that one call;
    # every other socket stays blocked, here and on the Linux CI runner.
    _REAL_SOCKET = socket.socket
    _REAL_SOCKETPAIR = socket.socketpair

    def _unguarded_socketpair(*args: Any, **kwargs: Any) -> Any:
        guarded = socket.socket
        socket.socket = _REAL_SOCKET
        try:
            return _REAL_SOCKETPAIR(*args, **kwargs)
        finally:
            socket.socket = guarded

    socket.socketpair = _unguarded_socketpair

    # aiodns, which aiohttp resolves with, refuses to run on the Proactor loop
    # Home Assistant picks on Windows. The selector loop runs the same tests.
    from homeassistant import runner

    runner.HassEventLoopPolicy._loop_factory = asyncio.SelectorEventLoop

BED_ID = "123456"
BED_NAME = "Test Bed"
BED_NAME_LOWER = BED_NAME.lower().replace(" ", "_")
BED_2_ID = "654321"
BED_2_NAME = "Guest Bed"
BED_2_NAME_LOWER = BED_2_NAME.lower().replace(" ", "_")
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
MASSAGE_URL = f"bed/{BED_ID}/foundation/massage"


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


def make_sleeper(sleeper_id: str, name: str, side: Side) -> MagicMock:
    """One sleeper, with last night's numbers."""
    sleeper = create_autospec(SleepIQSleeper)
    sleeper.side = side
    sleeper.name = name
    sleeper.sleeper_id = sleeper_id
    sleeper.in_bed = side == Side.LEFT
    sleeper.sleep_number = 40 if side == Side.LEFT else 80
    sleeper.pressure = 1000 if side == Side.LEFT else 1400
    sleeper.sleep_data = SleepData(
        duration=28800, sleep_score=85, heart_rate=60, respiratory_rate=14, hrv=68
    )
    return sleeper


def make_bed(
    bed_id: str = BED_ID,
    name: str = BED_NAME,
    mac_addr: str = "12:34:56:78:AB:CD",
    massage: bool = True,
    sleeper_ids: tuple[str, str] = (SLEEPER_L_ID, SLEEPER_R_ID),
) -> MagicMock:
    """A bed with two sleepers, a light, a preset and the full foundation."""
    bed = create_autospec(SleepIQBed)
    bed.name = name
    bed.id = bed_id
    bed.mac_addr = mac_addr
    bed.model = "C10"
    bed.paused = False
    bed.sleepers = [
        make_sleeper(sleeper_ids[0], SLEEPER_L_NAME, Side.LEFT),
        make_sleeper(sleeper_ids[1], SLEEPER_R_NAME, Side.RIGHT),
    ]

    bed.foundation = create_autospec(SleepIQFoundation)
    bed.foundation.type = "splitKing"
    # fsBoardFeatures = 7 on the verified bed: single board, massage and
    # light, foot control.
    bed.foundation.features = {
        "boardIsASingle": True,
        "hasMassageAndLight": massage,
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
    preset.options = list(BED_PRESETS)
    bed.foundation.presets = [preset]

    bed.foundation.actuators = [
        make_actuator(Side.LEFT, End.HEAD, 45),
        make_actuator(Side.NONE, End.FOOT, 0),
    ]
    bed.foundation.foot_warmers = [make_foot_warmer(Side.LEFT)]
    bed.foundation.core_climates = [make_core_climate(Side.RIGHT)]
    return bed


def make_actuator(side: Side, end: End, position: int) -> MagicMock:
    """One head or foot actuator."""
    actuator = create_autospec(SleepIQActuator)
    actuator.side = side
    actuator.side_full = "Left" if side == Side.LEFT else "Right"
    actuator.actuator = end
    actuator.actuator_full = "Head" if end == End.HEAD else "Foot"
    actuator.position = position
    return actuator


def make_foot_warmer(side: Side) -> MagicMock:
    """One foot warmer, off, with an hour on its timer."""
    foot_warmer = create_autospec(SleepIQFootWarmer)
    foot_warmer.side = side
    foot_warmer.temperature = FootWarmingTemps.OFF.value
    foot_warmer.timer = 60
    foot_warmer.is_on = False
    return foot_warmer


def make_core_climate(side: Side) -> MagicMock:
    """One core climate unit, off, with four hours on its timer."""
    core_climate = create_autospec(SleepIQCoreClimate)
    core_climate.side = side
    core_climate.temperature = CoreTemps.OFF.value
    core_climate.timer = 240
    core_climate.is_on = False
    return core_climate


@pytest.fixture
def mock_bed() -> MagicMock:
    """The bed the account starts with."""
    return make_bed()


@pytest.fixture
def second_bed() -> MagicMock:
    """A second bed, with its own sleepers, for the add and remove tests."""
    return make_bed(
        bed_id=BED_2_ID,
        name=BED_2_NAME,
        mac_addr="AA:BB:CC:DD:EE:FF",
        sleeper_ids=("11111", "22222"),
    )


@pytest.fixture
def account(mock_bed: MagicMock) -> dict[str, MagicMock]:
    """The beds the account reports, by id.

    Adding to or removing from this dict is a bed added to or removed from the
    SleepIQ account: the next poll reads the list and follows it.
    """
    return {BED_ID: mock_bed}


@pytest.fixture
def massage_payload() -> dict[str, Any]:
    """What the bed answers on the massage endpoint; tests may change it."""
    return deepcopy(MASSAGE_PAYLOAD)


@pytest.fixture
def mock_asyncsleepiq(
    account: dict[str, MagicMock], massage_payload: dict[str, Any]
) -> Generator[MagicMock]:
    """Replace the library client where setup constructs it.

    The client is also the API: the account's bed list and the massage reads
    go through client.get and writes through client.put, all recorded here
    rather than sent. init_beds() re-reads the account, as the library's does.
    """
    with patch("custom_components.sleepiq.AsyncSleepIQ", autospec=True) as mock:
        client = mock.return_value
        client.beds = dict(account)

        def _get(url: str, **kwargs: Any) -> dict[str, Any]:
            if url == "bed":
                return {"beds": [{"bedId": bed_id} for bed_id in account]}
            return deepcopy(massage_payload)

        def _init_beds() -> None:
            client.beds.clear()
            client.beds.update(account)

        client.get.side_effect = _get
        client.init_beds.side_effect = _init_beds
        yield client


def massage_reads(client: MagicMock) -> list[str]:
    """The massage endpoints read so far, one entry per GET."""
    return [
        call.args[0]
        for call in client.get.call_args_list
        if call.args and call.args[0] != "bed"
    ]


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
