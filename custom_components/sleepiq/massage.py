"""Massage (vibration) state and control for a SleepIQ foundation.

This module exists because `asyncsleepiq` can *write* massage but never *reads*
it. `SleepIQFoundation.set_foundation_massage()` ships and works, but the
library has no massage object, nothing calls `GET bed/{id}/foundation/massage`,
and the response fields (`footMassageMotorSpeed`, `headMassageMotorSpeed`,
`waveMode`, `massageTimer`) appear nowhere in it. Without readback there is
nothing for a Home Assistant entity to display, which is why upstream exposes no
massage entities at all.

So this fills in the read half and reuses the library's public request methods
for the write half. The client object is itself the API (`AsyncSleepIQ`
subclasses `SleepIQAPI`), so nothing private is reached into.

The one behavioural rule that matters: **full-body patterns and the individual
motor speeds are mutually exclusive.** `set_foundation_massage()` forces both
speeds to OFF whenever a mode is set, and the vendor app agrees - its massage
screen reads "Adjust either foot and head or full body massage", with Foot/Head
and Full Body as two separate panels. Entities mirror that in both directions or
the UI will lie about the bed's state.

Naming note: the library's `Mode.SOOTHE` is what the app labels **Smooth**. The
enum order matches the app's row exactly (Off, Smooth, Revitalize, Wave), so
SOOTHE=1 is Smooth. The translation strings use the app's wording, because that
is what is printed on the remote in the user's hand.
"""

from __future__ import annotations

import logging
from typing import Any

from asyncsleepiq import AsyncSleepIQ, Mode, Side, SleepIQBed, Speed

_LOGGER = logging.getLogger(__name__)

# Keys in the GET foundation/massage response, per side.
_SIDE_KEY = {Side.LEFT: "leftSide", Side.RIGHT: "rightSide"}

MASSAGE_ENDPOINT = "foundation/massage"

# Timer is in minutes. 60 is the maximum the vendor app and the physical remotes
# offer, which corroborates the countdown reading: a capture of a running
# massage reported massageTimer 57, i.e. 57 minutes left of a 60 minute run.
MASSAGE_TIMER_MIN = 0
MASSAGE_TIMER_MAX = 60

# Armed automatically when a massage is started with no timer set. The bed drops
# an idle timer, so starting a massage without one means nothing stops it.
# Mirrors core's own defaulting for comparable hardware, e.g.
# `timer = self.foot_warmer.timer or 120`.
MASSAGE_DEFAULT_TIMER = 60


def _coerce[_EnumT: (Speed, Mode)](
    enum_cls: type[_EnumT], raw: Any, default: _EnumT
) -> _EnumT:
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


def massage_label(bed: SleepIQBed, side: Side) -> str:
    """The word that names one side's massage entities.

    The sleeper's first name when someone sleeps on that side, otherwise the
    physical side. "Lewis massage mode" is what someone reaches for; "Right
    massage mode" makes them work out which side they are. Unlike core's
    sleeper_for_side() this never falls back to the first sleeper, so a bed
    with one sleeper still gets two distinctly named sides.
    """
    for sleeper in bed.sleepers:
        if sleeper.side == side and sleeper.name:
            return str(sleeper.name)
    return "Left" if side == Side.LEFT else "Right"


class SleepIQMassage:
    """Massage state and control for one side of a bed.

    Local state is only updated after the bed has accepted a write, so a
    rejected request leaves the last known state in place.
    """

    def __init__(self, api: AsyncSleepIQ, bed_id: str, side: Side) -> None:
        """Initialize the massage object for a side."""
        self._api = api
        self.bed_id = bed_id
        self.side = side

        self.foot_speed: Speed = Speed.OFF
        self.head_speed: Speed = Speed.OFF
        self.mode: Mode = Mode.OFF
        self.timer: int = 0
        # Raw per-side block from the last GET, surfaced as entity attributes so
        # the full field set can be observed while the vendor app drives the bed.
        self.raw: dict[str, Any] = {}

    @property
    def side_full(self) -> str:
        """Return the human-readable side name."""
        return "Left" if self.side == Side.LEFT else "Right"

    def apply(self, payload: dict[str, Any]) -> None:
        """Update this side from a foundation/massage response."""
        block = payload.get(_SIDE_KEY[self.side]) or {}
        self.raw = dict(block)
        self.foot_speed = _coerce(Speed, block.get("footMassageMotorSpeed"), Speed.OFF)
        self.head_speed = _coerce(Speed, block.get("headMassageMotorSpeed"), Speed.OFF)
        self.mode = _coerce(Mode, block.get("waveMode"), Mode.OFF)
        try:
            self.timer = int(block.get("massageTimer") or 0)
        except (TypeError, ValueError):
            self.timer = 0

    async def _put(self, data: dict[str, Any]) -> None:
        """Send one partial update, the way the vendor app does.

        `set_foundation_massage()` always sends all five fields, including
        `massageWaveMode`. The app never sends that field and only ever sends
        partial payloads - `{"headMassageMotor": 3, "side": "R"}`, and so on.
        A full-payload write is discarded wholesale by this foundation: setting
        a mode left both the mode AND the auto-armed timer at zero, while the
        identical timer logic works on a speed write.

        Note the read side returns `waveMode`, not `massageWaveMode`.
        """
        await self._api.put(
            f"bed/{self.bed_id}/foundation/adjustment", {**data, "side": self.side}
        )

    async def set_mode(self, mode: Mode) -> None:
        """Set the wave mode. Any non-OFF mode cancels the motor speeds."""
        # Send waveMode ALONE. The app's massage screen gives Full Body its own
        # Start Timer, separate from the Foot/Head one, so massageTimer here
        # probably arms the wrong timer and leaves the pattern with none - which
        # matches the observed behaviour of it running briefly then stopping.
        await self._put({"waveMode": int(mode)})
        self.mode = mode
        if mode != Mode.OFF:
            self.foot_speed = Speed.OFF
            self.head_speed = Speed.OFF
            self.timer = self.timer or MASSAGE_DEFAULT_TIMER

    async def set_speeds(
        self, foot_speed: Speed | None = None, head_speed: Speed | None = None
    ) -> None:
        """Set motor speeds. Any non-OFF speed cancels the wave mode."""
        foot = self.foot_speed if foot_speed is None else foot_speed
        head = self.head_speed if head_speed is None else head_speed
        mode = self.mode
        timer = self.timer
        if foot != Speed.OFF or head != Speed.OFF:
            mode = Mode.OFF
            timer = timer or MASSAGE_DEFAULT_TIMER
        await self._put(
            {
                "footMassageMotor": int(foot),
                "headMassageMotor": int(head),
                "massageTimer": timer,
            }
        )
        self.foot_speed = foot
        self.head_speed = head
        self.mode = mode
        self.timer = timer

    async def set_timer(self, minutes: int) -> None:
        """Set the massage timer in minutes."""
        timer = max(MASSAGE_TIMER_MIN, min(MASSAGE_TIMER_MAX, int(minutes)))
        await self._put({"massageTimer": timer})
        self.timer = timer


def build_massage_sides(api: AsyncSleepIQ, bed: SleepIQBed) -> list[SleepIQMassage]:
    """Create massage objects for a bed, or none if it has no massage board.

    Gated on the same `hasMassageAndLight` flag the library derives from
    `fsBoardFeatures` bit 1, so a bed without the hardware gets no entities.
    """
    if not bed.foundation.features.get("hasMassageAndLight"):
        return []

    return [SleepIQMassage(api, bed.id, side) for side in (Side.LEFT, Side.RIGHT)]


async def update_massage(
    api: AsyncSleepIQ, bed_id: str, sides: list[SleepIQMassage]
) -> None:
    """Refresh massage state for every side of a bed in one request.

    One GET serves both sides, so this is called per bed rather than per side.
    """
    if not sides:
        return
    payload = await api.get(f"bed/{bed_id}/{MASSAGE_ENDPOINT}")
    for massage in sides:
        massage.apply(payload)
