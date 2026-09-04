"""The massage model on its own: parsing, request shapes, and state discipline.

These need asyncsleepiq (for its enums) but not Home Assistant, so they run on
a workstation without the test harness.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("asyncsleepiq", reason="asyncsleepiq is not installed")

from asyncsleepiq import Mode, Side, Speed

from custom_components.sleepiq.massage import (
    MASSAGE_DEFAULT_TIMER,
    SleepIQMassage,
    build_massage_sides,
    massage_label,
    update_massage,
)

BED_ID = "123456"

PAYLOAD: dict[str, Any] = {
    "leftSide": {
        "footMassageMotorSpeed": 1,
        "headMassageMotorSpeed": 2,
        "waveMode": 0,
        "massageTimer": 12,
        "massageMotorStatus": 1,
    },
    "rightSide": {
        "footMassageMotorSpeed": 0,
        "headMassageMotorSpeed": 0,
        "waveMode": 1,
        "massageTimer": 57,
    },
}


def _api() -> Any:
    api = SimpleNamespace(put=AsyncMock(), get=AsyncMock(return_value=PAYLOAD))
    return api


def _bed(*sleepers: tuple[Side, str], massage: bool = True) -> Any:
    return SimpleNamespace(
        id=BED_ID,
        sleepers=[SimpleNamespace(side=side, name=name) for side, name in sleepers],
        foundation=SimpleNamespace(features={"hasMassageAndLight": massage}),
    )


# --------------------------------------------------------------------- apply


def test_apply_reads_this_sides_block_only():
    left = SleepIQMassage(_api(), BED_ID, Side.LEFT)
    right = SleepIQMassage(_api(), BED_ID, Side.RIGHT)
    left.apply(PAYLOAD)
    right.apply(PAYLOAD)
    assert (left.foot_speed, left.head_speed, left.mode, left.timer) == (
        Speed.LOW,
        Speed.MEDIUM,
        Mode.OFF,
        12,
    )
    assert (right.foot_speed, right.mode, right.timer) == (Speed.OFF, Mode.SOOTHE, 57)
    assert left.raw == PAYLOAD["leftSide"]


def test_apply_tolerates_junk_from_the_bed():
    massage = SleepIQMassage(_api(), BED_ID, Side.LEFT)
    massage.apply(
        {
            "leftSide": {
                "footMassageMotorSpeed": 9,
                "headMassageMotorSpeed": "high",
                "waveMode": None,
                "massageTimer": "soon",
            }
        }
    )
    assert massage.foot_speed is Speed.OFF
    assert massage.head_speed is Speed.OFF
    assert massage.mode is Mode.OFF
    assert massage.timer == 0


def test_apply_with_the_side_missing_resets_to_off():
    massage = SleepIQMassage(_api(), BED_ID, Side.RIGHT)
    massage.apply(PAYLOAD)
    massage.apply({})
    assert massage.mode is Mode.OFF
    assert massage.timer == 0
    assert massage.raw == {}


# -------------------------------------------------------------------- writes


async def test_speed_write_uses_the_apps_partial_payload_and_arms_the_timer():
    api = _api()
    massage = SleepIQMassage(api, BED_ID, Side.RIGHT)
    await massage.set_speeds(foot_speed=Speed.HIGH)
    api.put.assert_awaited_once_with(
        f"bed/{BED_ID}/foundation/adjustment",
        {
            "footMassageMotor": 3,
            "headMassageMotor": 0,
            "massageTimer": MASSAGE_DEFAULT_TIMER,
            "side": Side.RIGHT,
        },
    )
    assert massage.foot_speed is Speed.HIGH
    assert massage.timer == MASSAGE_DEFAULT_TIMER


async def test_an_explicit_timer_is_never_overridden_by_the_default():
    api = _api()
    massage = SleepIQMassage(api, BED_ID, Side.LEFT)
    massage.apply(PAYLOAD)  # timer 12
    await massage.set_speeds(head_speed=Speed.LOW)
    assert api.put.await_args.args[1]["massageTimer"] == 12


async def test_a_speed_cancels_the_mode_and_a_mode_cancels_the_speeds():
    api = _api()
    massage = SleepIQMassage(api, BED_ID, Side.RIGHT)
    massage.apply(PAYLOAD)  # mode soothe
    await massage.set_speeds(foot_speed=Speed.LOW)
    assert massage.mode is Mode.OFF

    await massage.set_mode(Mode.WAVE)
    assert massage.foot_speed is Speed.OFF
    assert massage.head_speed is Speed.OFF
    assert massage.mode is Mode.WAVE


async def test_mode_is_sent_alone():
    api = _api()
    massage = SleepIQMassage(api, BED_ID, Side.LEFT)
    await massage.set_mode(Mode.REVITILIZE)
    api.put.assert_awaited_once_with(
        f"bed/{BED_ID}/foundation/adjustment", {"waveMode": 2, "side": Side.LEFT}
    )


async def test_turning_the_mode_off_leaves_the_speeds_and_timer_alone():
    api = _api()
    massage = SleepIQMassage(api, BED_ID, Side.LEFT)
    massage.apply(PAYLOAD)
    await massage.set_mode(Mode.OFF)
    assert massage.foot_speed is Speed.LOW
    assert massage.timer == 12


@pytest.mark.parametrize(("asked", "sent"), [(-5, 0), (20, 20), (61, 60)])
async def test_timer_is_clamped_to_the_beds_range(asked, sent):
    api = _api()
    massage = SleepIQMassage(api, BED_ID, Side.LEFT)
    await massage.set_timer(asked)
    api.put.assert_awaited_once_with(
        f"bed/{BED_ID}/foundation/adjustment", {"massageTimer": sent, "side": Side.LEFT}
    )
    assert massage.timer == sent


async def test_a_refused_write_leaves_the_last_known_state_in_place():
    api = _api()
    api.put.side_effect = RuntimeError("503")
    massage = SleepIQMassage(api, BED_ID, Side.LEFT)
    massage.apply(PAYLOAD)
    for request in (
        massage.set_speeds(foot_speed=Speed.HIGH),
        massage.set_mode(Mode.WAVE),
        massage.set_timer(30),
    ):
        with pytest.raises(RuntimeError):
            await request
    assert (massage.foot_speed, massage.head_speed, massage.mode, massage.timer) == (
        Speed.LOW,
        Speed.MEDIUM,
        Mode.OFF,
        12,
    )


# ------------------------------------------------------------ construction


def test_a_bed_without_the_massage_board_gets_no_sides():
    assert build_massage_sides(_api(), _bed(massage=False)) == []


def test_a_bed_with_the_board_gets_one_object_per_side():
    sides = build_massage_sides(_api(), _bed((Side.LEFT, "Lewis")))
    assert [m.side for m in sides] == [Side.LEFT, Side.RIGHT]
    assert {m.bed_id for m in sides} == {BED_ID}


async def test_update_fetches_once_per_bed_and_feeds_both_sides():
    api = _api()
    sides = build_massage_sides(api, _bed())
    await update_massage(api, BED_ID, sides)
    api.get.assert_awaited_once_with(f"bed/{BED_ID}/foundation/massage")
    assert sides[0].timer == 12
    assert sides[1].mode is Mode.SOOTHE


async def test_update_skips_the_request_for_a_bed_without_sides():
    api = _api()
    await update_massage(api, BED_ID, [])
    api.get.assert_not_awaited()


# ------------------------------------------------------------------ naming


def test_label_is_the_sleeper_on_that_side():
    bed = _bed((Side.LEFT, "Lewis"), (Side.RIGHT, "Sam"))
    assert massage_label(bed, Side.LEFT) == "Lewis"
    assert massage_label(bed, Side.RIGHT) == "Sam"


def test_label_falls_back_to_the_physical_side_not_the_first_sleeper():
    bed = _bed((Side.LEFT, "Lewis"))
    assert massage_label(bed, Side.RIGHT) == "Right"
    assert massage_label(_bed((Side.RIGHT, "")), Side.RIGHT) == "Right"
