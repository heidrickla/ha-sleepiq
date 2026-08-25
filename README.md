# SleepIQ (with massage)

Home Assistant's built-in `sleepiq` integration exposes firmness, head and foot
position, foundation presets, under-bed lights, pause mode and the sleep
sensors — but **not massage**. This custom component adds it.

It is a copy of the core integration with massage support layered on, so
installing it replaces core's `sleepiq` rather than running alongside it.

## Why core does not have it

The gap is not in Home Assistant, and it is not that beds lack the hardware.

`asyncsleepiq` — the library core depends on — can **write** massage but never
**reads** it. `SleepIQFoundation.set_foundation_massage()` ships and works, but
the library has no massage object, nothing calls
`GET bed/{id}/foundation/massage`, and the response fields
(`footMassageMotorSpeed`, `headMassageMotorSpeed`, `waveMode`, `massageTimer`)
appear nowhere in it.

Without readback there is no state for an entity to display, so core exposes
none. This repo fills in the read half and reuses the library's existing write
half — no library fork, no patched dependency.

## Entities added

Per side, for beds whose foundation reports the massage board:

| Entity | Platform | Values |
| --- | --- | --- |
| `{bed} {sleeper} Massage Mode` | `select` | off, soothe, revitalize, wave |
| `{bed} {sleeper} Foot Massage Speed` | `select` | off, low, medium, high |
| `{bed} {sleeper} Head Massage Speed` | `select` | off, low, medium, high |
| `{bed} {sleeper} Massage Timer` | `number` | 0-60 minutes |

Entities are named by **sleeper**, not by physical side - "Lewis Massage Mode",
not "Right Massage Mode" - matching how core names the other per-sleeper comfort
hardware (foot warmer, core climate) via its `sleeper_for_side()` helper. Nobody
reaching for the massage control wants to first work out which side they sleep
on.

Entities are created only when the foundation advertises massage —
`hasMassageAndLight`, which the library derives from bit 1 of `fsBoardFeatures`.
A bed without the board gets nothing rather than dead controls.

### Mode and speed are mutually exclusive

This is an API rule, not a UI choice. `set_foundation_massage()` forces both
motor speeds to OFF whenever a wave mode is set. So:

- Selecting a **mode** other than off drives both speed entities to off.
- Selecting a non-off **speed** drives the mode entity to off.

The entities mirror that deliberately. If they did not, the UI would show a
state the bed is not in.

## Verified on hardware

Deployed to Home Assistant 2026.8.2 against a SelectComfort i8
(`fsBoardFeatures = 7`, so `hasMassageAndLight` is set). Eight entities were
created, four per side, and the integration loaded with no errors.

| Test | Result |
| --- | --- |
| Motor speed write and readback | **pass** - setting foot speed to `low` reads back `low` from the bed |
| Mode cancels speed | **pass** - selecting a mode drove foot speed to `off` |
| All four motors, both sides, HIGH | **pass** - confirmed by the bed's occupants |
| Sleeper-to-side mapping | **pass** - left and right resolve to the correct sleepers |
| Wave mode engages | **fails** - see below |
| Timer holds its value | **expires when idle** - see below |

## Starting a massage arms a 60 minute timer

Selecting any speed or mode with no timer set arms **60 minutes** - the maximum
the vendor app and the physical remotes offer.

This is deliberate, and it exists because of the expiry behaviour below: the bed
drops an idle timer, so a massage started without one has nothing scheduled to
stop it. Defaulting means the motors always have an end.

An explicitly set timer is never overridden - the logic is
`self.timer or MASSAGE_DEFAULT_TIMER`, matching how core defaults comparable
hardware (`timer = self.foot_warmer.timer or 120`). Set 20 minutes and you get
20; set nothing and you get 60.

The 60 minute ceiling also corroborates the countdown reading: a capture of a
running massage reported `massageTimer: 57`, which is what 57 minutes remaining
of a 60 minute run looks like.

## Known issue: the timer expires if massage is not started

`massageTimer` is exposed as a `number`, but it behaves as an **armed
countdown, not a stored preference**. Measured on hardware:

| Action | Left | Right |
| --- | --- | --- |
| baseline | 0.0 | 0.0 |
| set left = 7 | **7.0** | 0.0 |
| +45 s, no motors started | **0.0** | 0.0 |
| set right = 12 | 0.0 | **12.0** |
| right speed -> low | 0.0 | **12.0** |

Two things follow.

**The timers are per-side and independent.** Setting one never moves the other,
so the value on one side tells you nothing about the other. There is no shared
bed-wide timer to read.

**An idle timer clears itself.** Left was set to 7 and read back 7, then fell to
0 within 45 seconds with no motors running. The right side, which had a motor
started while its timer was set, held its value. The consistent reading is that
the bed arms the timer and drops it if a massage does not begin - though the
exact window has not been measured.

So: **set the timer, then start the massage promptly.** Setting a timer and
walking away leaves nothing armed.

An earlier revision of this file blamed a write race - every request sends the
whole payload, so a coordinator refresh landing mid-sequence was assumed to
overwrite the local timer. **That was wrong.** A speed write does not disturb
the timer at all, as the table above shows. The correct explanation is
expiry, and it was found by testing the claim rather than reasoning about it.

## Known issue: wave mode does not stick, and "Smooth" is missing

The mode entity offers `off / soothe / revitilize / wave`, taken from the
library's `Mode` enum. The vendor app exposes at least one pattern that is not
in that list - **Smooth** - so the enum is probably incomplete.

Selecting any mode also fails to take. The write reaches the bed (the motor
speeds go to off, which is the mutual-exclusion behaviour) but `waveMode` reads
back `0` on the next refresh. No error is logged.

### What a packet capture of the vendor app shows

Captured requests to `foundation/adjustment` while driving massage from the app:

    {"footMassageMotor": 3, "massageTimer": 15, "side": "R"}
    {"headMassageMotor": 3, "side": "R"}
    {"massageTimer": 60, "side": "R"}

Two things stand out.

**The app sends partial payloads.** Head alone, timer alone, foot plus timer.
`set_foundation_massage()` always sends all five fields
(`footMassageMotor`, `headMassageMotor`, `massageTimer`, `massageWaveMode`,
`side`). The app and the library are speaking measurably different dialects to
the same endpoint.

**`massageWaveMode` never appears in any captured request**, and `waveMode` read
back `0` in all 46 observed responses. So there is no evidence for what field or
value a pattern actually uses - only that it is not what the library sends.

That makes the earlier guess - that forcing both speeds to OFF leaves a wave
pattern with no motor to run on - less likely than the simpler explanation that
the field name or endpoint is wrong for this foundation.

### How to settle it

Run the app through a proxy and select each massage pattern in turn, then look
at what `foundation/adjustment` receives. That yields both the correct field and
the integer for every pattern including Smooth, at which point the enum can be
extended and the writer corrected. Nothing here can be fixed by guessing.

**Motor speed control is unaffected and works.** If you only need vibration, the
two speed entities per side are sufficient and the mode entity can be ignored.

## Install

**HACS** — add this repository as a custom repository (category: Integration),
install, restart Home Assistant.

**Manual** — copy `custom_components/sleepiq/` into your config directory's
`custom_components/`, then restart.

Either way Home Assistant will log that a custom integration is overriding a
built-in one. That is expected.

Your existing SleepIQ config entry is reused as-is — same domain, same unique
ids, so no re-authentication and no entity renames.

## Uninstalling

Delete `custom_components/sleepiq/` and restart. Core's integration takes over
again and every non-massage entity keeps working; only the massage entities
disappear.

## Keeping in sync with core

This shadows a core integration, which is the real cost of the approach. When
Home Assistant updates `sleepiq`, this copy does not follow.

`docs/UPSTREAM-BASELINE.txt` records the SHA-256 of each file as copied from
`home-assistant/core` at tag **2026.8.2**. To resync:

```bash
# fetch the same files at a newer tag and compare against the baseline
curl -s -o /tmp/select.py   https://raw.githubusercontent.com/home-assistant/core/<tag>/homeassistant/components/sleepiq/select.py
sha256sum /tmp/select.py
```

A changed hash means upstream moved and that file needs its massage additions
re-applied. `NOTICE` lists exactly which files were modified and how, so the
diff to carry forward is small.

## Upstreaming

The proper fix is upstream: add a massage object to `asyncsleepiq` (read and
write, wired into `init_features()` / `update()`), then add the entities to
`home-assistant/core`. This repo is deliberately Apache-2.0, matching Home
Assistant, so the code here can move upstream without a licensing problem.

## Credits

`custom_components/sleepiq/` is derived from the Home Assistant `sleepiq`
integration by **@mfugate1** and **@kbickar**, Apache-2.0. See `NOTICE`.

The underlying API behaviour was confirmed by capturing the SleepIQ Android
app's own traffic; the endpoint documentation lives in a separate repository.
