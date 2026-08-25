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
| `{bed} {sleeper} Massage Timer` | `number` | 0-30 minutes |

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
| Timer holds its value | **unreliable** - see below |

## Known issue: the timer is probably a countdown, not a setting

`massageTimer` is exposed as a `number`, but the evidence suggests it is a
**live countdown rather than a stored preference**. In a packet capture of the
vendor app, the running side reported `massageTimer: 57` alongside
`massageRunTime: 3` while the idle side reported `0`.

Observed symptom: setting the timer then immediately setting a speed can leave
the timer reading `0`. Every write sends the whole payload - that is the API's
shape, not a choice - so a coordinator refresh landing mid-sequence can replace
the local timer with the bed's own value before the speed write re-sends it.

Until the semantics are confirmed, treat the timer entity as advisory. Set it
*before* starting a massage and re-check it afterwards rather than assuming it
held. An `off` write to both speed entities always stops the motors regardless.

## Known issue: wave mode does not stick

Selecting a wave mode (`soothe` / `revitilize` / `wave`) reaches the bed - the
motor speeds go to off, which is the API's mutual-exclusion behaviour, so the
write is clearly landing - but the mode itself reads back as `off` on the next
refresh. No error is logged and the request succeeds.

The likely cause is in `set_foundation_massage()` upstream: it forces **both
motor speeds to OFF whenever a mode is set**. If the foundation will not run a
wave pattern with both motors at zero speed, it accepts the command, runs
nothing, and correctly reports `waveMode: 0`.

That is a hypothesis, not a diagnosis. It has not been confirmed, and it may
instead be that this foundation simply does not implement wave modes.

**Motor speed control - the part that actually vibrates the bed - works.** If
you only need vibration, the two speed entities per side are sufficient and the
mode entity can be ignored.

To investigate: set a mode *and* a non-zero speed in one request and see whether
`waveMode` survives. That contradicts the library's current behaviour, so it
would need a library change rather than a change here.

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
