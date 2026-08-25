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
| `{bed} {side} Massage Mode` | `select` | off, soothe, revitalize, wave |
| `{bed} {side} Foot Massage Speed` | `select` | off, low, medium, high |
| `{bed} {side} Head Massage Speed` | `select` | off, low, medium, high |
| `{bed} {side} Massage Timer` | `number` | 0-30 minutes |

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
