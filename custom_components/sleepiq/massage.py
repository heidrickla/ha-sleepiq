"""Massage (vibration) state and control for a SleepIQ foundation.

This module exists because `asyncsleepiq` can *write* massage but never *reads*
it. `SleepIQFoundation.set_foundation_massage()` ships and works, but the
library has no massage object, nothing calls `GET bed/{id}/foundation/massage`,
and the response fields (`footMassageMotorSpeed`, `headMassageMotorSpeed`,
`waveMode`, `massageTimer`) appear nowhere in it. Without readback there is
nothing for a Home Assistant entity to display, which is why upstream exposes no
massage entities at all.

So this fills in the read half and reuses the library's existing write half.

The one behavioural rule that matters: **wave mode and motor speeds are mutually
exclusive.** `set_foundation_massage()` forces both speeds to OFF whenever mode
is not OFF, so setting a mode cancels the speeds and setting a speed must clear
the mode. Entities have to mirror that or the UI will lie about the bed's state.
"""

from __future__ import annotations

import logging
from typing import Any

from asyncsleepiq import Mode, Side, SleepIQBed, Speed

_LOGGER = logging.getLogger(__name__)

# Keys in the GET foundation/massage response, per side.
_SIDE_KEY = {Side.LEFT: "leftSide", Side.RIGHT: "rightSide"}

MASSAGE_ENDPOINT = "foundation/massage"

# The API accepts a timer in minutes. The app offers these; 0 means "no timer".
MASSAGE_TIMER_MIN = 0
MASSAGE_TIMER_MAX = 30


def _coerce[_EnumT: (Speed, Mode)](enum_cls: type[_EnumT], raw: Any, default: _EnumT) -> _EnumT:
    """Convert an API integer to an enum member, tolerating junk.

    The bed has been observed returning values outside the documented range;
    an unknown speed should degrade to OFF rather than raise and break the
    whole coordinator refresh.
    """
    try:
        return enum_cls(int(raw))
    except (TypeError, ValueError):
        _LOGGER.debug("Unexpected %s value from SleepIQ: %r", enum_cls.__name__, raw)
        return default


class SleepIQMassage:
    """Massage state and control for one side of a bed."""

    def __init__(self, foundation: Any, bed_id: str, side: Side) -> None:
        """Initialize the massage object for a side."""
        self._foundation = foundation
        self._api = foundation._api  # noqa: SLF001 - library exposes no public client
        self.bed_id = bed_id
        self.side = side

        self.foot_speed: Speed = Speed.OFF
        self.head_speed: Speed = Speed.OFF
        self.mode: Mode = Mode.OFF
        self.timer: int = 0
        self.motor_status: int = 0

    @property
    def side_full(self) -> str:
        """Return the human-readable side name."""
        return "Left" if self.side == Side.LEFT else "Right"

    @property
    def is_running(self) -> bool:
        """Return True if any massage motor is active."""
        return bool(self.motor_status) or self.mode != Mode.OFF or bool(
            self.foot_speed or self.head_speed
        )

    def apply(self, payload: dict[str, Any]) -> None:
        """Update this side from a foundation/massage response."""
        block = payload.get(_SIDE_KEY[self.side]) or {}
        self.foot_speed = _coerce(Speed, block.get("footMassageMotorSpeed"), Speed.OFF)
        self.head_speed = _coerce(Speed, block.get("headMassageMotorSpeed"), Speed.OFF)
        self.mode = _coerce(Mode, block.get("waveMode"), Mode.OFF)
        try:
            self.timer = int(block.get("massageTimer") or 0)
        except (TypeError, ValueError):
            self.timer = 0
        try:
            self.motor_status = int(block.get("massageMotorStatus") or 0)
        except (TypeError, ValueError):
            self.motor_status = 0

    async def _push(self) -> None:
        """Send the current desired state to the bed.

        Goes through the library's own writer so the payload shape stays the
        library's problem, not ours.
        """
        await self._foundation.set_foundation_massage(
            self.side,
            self.foot_speed,
            self.head_speed,
            self.timer,
            self.mode,
        )

    async def set_mode(self, mode: Mode) -> None:
        """Set the wave mode. Any non-OFF mode cancels the motor speeds."""
        self.mode = mode
        if mode != Mode.OFF:
            self.foot_speed = Speed.OFF
            self.head_speed = Speed.OFF
        await self._push()

    async def set_speeds(
        self, foot_speed: Speed | None = None, head_speed: Speed | None = None
    ) -> None:
        """Set motor speeds. Any non-OFF speed cancels the wave mode."""
        if foot_speed is not None:
            self.foot_speed = foot_speed
        if head_speed is not None:
            self.head_speed = head_speed
        if self.foot_speed != Speed.OFF or self.head_speed != Speed.OFF:
            self.mode = Mode.OFF
        await self._push()

    async def set_timer(self, minutes: int) -> None:
        """Set the massage timer in minutes."""
        self.timer = max(MASSAGE_TIMER_MIN, min(MASSAGE_TIMER_MAX, int(minutes)))
        await self._push()

    async def turn_off(self) -> None:
        """Stop massage on this side."""
        self.mode = Mode.OFF
        self.foot_speed = Speed.OFF
        self.head_speed = Speed.OFF
        await self._push()


def build_massage_sides(bed: SleepIQBed) -> list[SleepIQMassage]:
    """Create massage objects for a bed, or none if it has no massage board.

    Gated on the same `hasMassageAndLight` flag the library derives from
    `fsBoardFeatures` bit 1, so a bed without the hardware gets no entities.
    """
    foundation = bed.foundation
    if not foundation.features.get("hasMassageAndLight"):
        return []

    return [SleepIQMassage(foundation, bed.id, side) for side in (Side.LEFT, Side.RIGHT)]


async def update_massage(bed: SleepIQBed) -> None:
    """Refresh massage state for every side of a bed in one request.

    One GET serves both sides, so this is called per bed rather than per side.
    """
    sides: list[SleepIQMassage] = getattr(bed.foundation, "massage_sides", [])
    if not sides:
        return
    payload = await bed.foundation._api.get(  # noqa: SLF001
        f"bed/{bed.id}/{MASSAGE_ENDPOINT}"
    )
    for massage in sides:
        massage.apply(payload)
