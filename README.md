# SleepIQ (with massage)

Home Assistant's built-in `sleepiq` integration exposes firmness, head and foot
position, foundation presets, under-bed lights, pause mode and the sleep
sensors of a SleepNumber bed - but **not massage**. This custom component adds
it: per side, the full-body pattern, the head and foot motor speeds and the
massage timer, read back from the bed rather than assumed.

It is a copy of the core integration with massage support layered on, so
installing it replaces core's `sleepiq` rather than running alongside it.
Everything core does, this does too; the massage entities are the addition.

## Why core does not have it

The gap is not in Home Assistant, and it is not that beds lack the hardware.

`asyncsleepiq` - the library core depends on - can **write** massage but never
**reads** it. `SleepIQFoundation.set_foundation_massage()` ships and works, but
the library has no massage object, nothing calls
`GET bed/{id}/foundation/massage`, and the response fields
(`footMassageMotorSpeed`, `headMassageMotorSpeed`, `waveMode`, `massageTimer`)
appear nowhere in it.

Without readback there is no state for an entity to display, so core exposes
none. This repo fills in the read half and reuses the library's existing write
half - no library fork, no patched dependency.

## Supported devices

- Any SleepNumber bed registered to a SleepIQ account, through the SleepNumber
  cloud. Every bed on the account is set up under one entry; each bed is one
  device in Home Assistant.
- Massage entities appear only for a bed whose FlexFit foundation reports the
  massage board: `hasMassageAndLight`, which the library derives from bit 1 of
  `fsBoardFeatures`. A bed without the board gets the core entities and no
  dead massage controls.
- Verified on hardware: a SelectComfort i8 on a FlexFit foundation
  (`fsBoardFeatures = 7`) running Home Assistant 2026.8.2. Eight massage
  entities were created, four per side, and the integration loaded with no
  errors.
- Not verified: Climate360 and other "Fuzion" generation beds. The library
  drives them and the core entities should work; the massage endpoint has not
  been tried on one.

## Supported functions

Per sleeper, from core:

| Entity | Platform | What it is |
| --- | --- | --- |
| `SleepNumber {bed} {sleeper} Is In Bed` | `binary_sensor` | Occupancy from the bed's pressure sensor |
| `SleepNumber {bed} {sleeper} Pressure` | `sensor` | Raw air pressure reading, SleepNumber's own units |
| `SleepNumber {bed} {sleeper} SleepNumber` | `sensor` | Current firmness setting |
| `SleepNumber {bed} {sleeper} Firmness` | `number` | Firmness, 5 to 100 in steps of 5 |
| `SleepNumber {bed} {sleeper} Sleep Score` | `sensor` | Last night's SleepIQ score |
| `SleepNumber {bed} {sleeper} Sleep Duration` | `sensor` | Last night's time in bed, hours |
| `SleepNumber {bed} {sleeper} Heart Rate Average` | `sensor` | Last night's average heart rate |
| `SleepNumber {bed} {sleeper} Respiratory Rate Average` | `sensor` | Last night's average breathing rate |
| `SleepNumber {bed} {sleeper} Heart Rate Variability` | `sensor` | Last night's HRV, milliseconds |
| `SleepNumber {bed} {sleeper} Foot Warmer` | `select` | Foot warming: off, low, medium, high (beds with foot warming) |
| `SleepNumber {bed} {sleeper} Foot Warming Timer` | `number` | Foot warming run time, 30 to 360 minutes |
| `SleepNumber {bed} {sleeper} Core Climate` | `select` | Climate360 heating and cooling levels (beds with core climate) |
| `SleepNumber {bed} {sleeper} Core Climate Timer` | `number` | Core climate run time, minutes |

Per bed, from core:

| Entity | Platform | What it is |
| --- | --- | --- |
| `SleepNumber {bed} {side} {Head/Foot} Position` | `number` | Actuator position, 0 to 100 (beds with an adjustable foundation) |
| `SleepNumber {bed} Foundation Preset {side}` | `select` | Favorite, Read, Watch TV, Flat, Zero G, Snore |
| `SleepNumber {bed} Light {n}` | `light` | Under-bed light or night stand outlet |
| `SleepNumber {bed} Pause Mode` | `switch` | Privacy mode: stops the bed reporting sleep data |
| `SleepNumber {bed} Calibrate` | `button` | Re-baseline the pressure sensors |
| `SleepNumber {bed} Stop Pump` | `button` | Stop a firmness adjustment in progress |

Per side, added by this repository, for beds whose foundation reports the
massage board:

| Entity | Platform | Values |
| --- | --- | --- |
| `{bed} {sleeper} massage mode` | `select` | `off`, `soothe` (shown as Smooth), `revitilize` (shown as Revitalize), `wave` |
| `{bed} {sleeper} foot massage speed` | `select` | `off`, `low`, `medium`, `high` |
| `{bed} {sleeper} head massage speed` | `select` | `off`, `low`, `medium`, `high` |
| `{bed} {sleeper} massage timer` | `number` | 0 to 60 minutes |

The option keys are the library's enum names, spelling included: an automation
must send `revitilize`, not `revitalize`. The labels shown in the UI are the
vendor app's own (Smooth, Revitalize, Wave).

The massage entities are named by **sleeper**, not by physical side - "Lewis
massage mode", not "Right massage mode" - matching how core names the other
per-sleeper comfort hardware (foot warmer, core climate). Nobody reaching for
the massage control wants to first work out which side they sleep on. A side
with no sleeper on the account is named by position ("Right massage mode").
Under the hood each entity is keyed on the bed and the physical side, so a bed
with one sleeper still gets two independent sets of controls.

There are no actions (services), triggers or conditions; every function is an
entity.

## Installation

**HACS** - add this repository as a custom repository (category: Integration),
install, restart Home Assistant.

**Manual** - copy `custom_components/sleepiq/` into your config directory's
`custom_components/`, then restart.

Either way Home Assistant will log that a custom integration is overriding a
built-in one. That is expected.

If you already have core's SleepIQ set up, the existing config entry is
reused as-is - same domain, same unique ids, so no re-authentication and no
entity renames for the core entities. Otherwise add it from **Settings >
Devices & services > Add integration > SleepIQ**.

### Installation parameters

| Field | Required | What to enter |
| --- | --- | --- |
| Username | yes | The email address you sign in to the SleepIQ app with. One entry covers every bed on the account. |
| Password | yes | The password for that account. It is stored in the config entry and never shown again. |

There are no options to configure after setup. If the password changes, Home
Assistant asks for the new one through a re-authentication prompt; the
username cannot be changed in place, because it identifies the entry - remove
the entry and add the other account.

## Data updates

Everything comes from the SleepNumber cloud; the bed itself is never contacted
directly, so nothing on your network needs configuring.

| Data | Interval |
| --- | --- |
| Presence, pressure, firmness, foundation positions, presets, lights, massage state | every 60 seconds |
| Pause mode | every 5 minutes |
| Sleep score, duration, heart rate, respiratory rate, HRV | every hour |

A write (firmness, position, massage, light) is sent immediately and the
entity shows the new value straight away. The massage entities then request a
refresh, so what you see a moment later is what the bed reports, not what was
asked for. The cloud's own view of the bed can lag a few seconds behind the
remote or the app.

## Use cases

- Start a foot massage at bedtime and let the timer stop it, without reaching
  for the remote.
- Stop a massage automatically when its sleeper gets out of bed.
- Show the remaining massage time on a bedside dashboard next to the firmness
  and position controls.
- Put the whole bed to bed: flat preset, lights off, massage off, in one
  script.

## Examples

Start a 20 minute low foot massage on one side at 22:00. The timer is set
first and the motor started straight after, because the bed drops an idle
timer (see the known limitations).

```yaml
automation:
  - alias: Bedtime foot massage
    triggers:
      - trigger: time
        at: "22:00:00"
    actions:
      - action: number.set_value
        target:
          entity_id: number.master_bedroom_lewis_massage_timer
        data:
          value: 20
      - action: select.select_option
        target:
          entity_id: select.master_bedroom_lewis_foot_massage_speed
        data:
          option: low
```

Stop the massage when the sleeper leaves the bed:

```yaml
automation:
  - alias: Massage off when out of bed
    triggers:
      - trigger: state
        entity_id: binary_sensor.sleepnumber_master_bedroom_lewis_is_in_bed
        to: "off"
        for: "00:02:00"
    actions:
      - action: select.select_option
        target:
          entity_id:
            - select.master_bedroom_lewis_foot_massage_speed
            - select.master_bedroom_lewis_head_massage_speed
        data:
          option: "off"
```

Entity ids follow the bed's name and the sleeper's first name; take the exact
ids from **Settings > Devices & services > SleepIQ > the bed**.

## How the massage controls behave

### Mode and speed are mutually exclusive

This is an API rule, not a UI choice. `set_foundation_massage()` forces both
motor speeds to OFF whenever a wave mode is set, and the vendor app's massage
screen says the same: "Adjust either foot and head or full body massage". So:

- Selecting a **mode** other than off drives both speed entities to off.
- Selecting a non-off **speed** drives the mode entity to off.

The entities mirror that deliberately. If they did not, the UI would show a
state the bed is not in.

### Starting a massage arms a 60 minute timer

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

### Verified on hardware

| Test | Result |
| --- | --- |
| Motor speed write and readback | **pass** - setting foot speed to `low` reads back `low` from the bed |
| Mode cancels speed | **pass** - selecting a mode drove foot speed to `off` |
| All four motors, both sides, HIGH | **pass** - confirmed by the bed's occupants |
| Sleeper-to-side mapping | **pass** - left and right resolve to the correct sleepers |
| Wave mode engages | **fails** - see below |
| Timer holds its value | **expires when idle** - see below |

## Known limitations

### The timer expires if massage is not started

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

### The full-body patterns cannot be set from Home Assistant

Foot/Head speed control works. The **Full Body** patterns - Smooth, Revitalize,
Wave - can be *read* but not *written*.

**The read side is correct.** Confirmed on hardware: setting Smooth for 1 hour
from the vendor phone app showed up in Home Assistant within one poll as
`mode=soothe`, `timer=60.0`, counting down to 58 a couple of minutes later. So
`waveMode 1 = Smooth`, the timer is in minutes, and 60 is the maximum.

**Naming.** The app's Full Body row is `Off / Smooth / Revitalize / Wave`; the
library enum is `OFF=0 / SOOTHE=1 / REVITILIZE=2 / WAVE=3` - same order, so
`SOOTHE` **is** Smooth. The translations use the app's wording; the option keys
keep the library's spelling.

**The write starts the pattern, but it does not sustain.** The request is not
rejected. The bed's owner watched the mattress and reported that the side "did
turn on for a bit" during a test that HA had recorded as a total failure. The
pattern starts, runs briefly, and stops - and because `waveMode` reads back `0`
once it has stopped, the API view alone made it look like nothing had happened.
That is worth stating plainly: the API state was consistent with "request
rejected" and was wrong. Only watching the hardware distinguished the two.

Three request shapes have been tried, all on an **idle** side:

| Sent | Result |
| --- | --- |
| `massageWaveMode` + all five fields (`set_foundation_massage()`) | starts, stops |
| `waveMode` + `massageTimer` | starts, stops |
| `waveMode` alone | starts, stops |

By contrast, a pattern set from the **vendor phone app** persists. So the
correct request differs from all three of the above in some way that has not
been guessed. Three attempts, three failures - the remaining move is to observe
the real request rather than infer it; `docs/NEXT-SESSION.md` has the plan.

Likely direction, from the app's own UI: the massage screen gives **Full Body
its own Start Timer**, separate from the Foot/Head one. A pattern may need that
timer armed through a different field or endpoint, and without it the foundation
runs a brief burst and stops. That is a hypothesis and is not to be treated as
more than one.

Writes use the app's **partial-payload dialect** rather than the library's
all-five-fields call - `{"footMassageMotor": N, "headMassageMotor": N,
"massageTimer": N, "side": "R"}` - matching what the app was observed sending.
Speed control was regression-tested after the change and still works, with the
timer arming correctly.

### Other limitations

- This shadows core's `sleepiq`. When Home Assistant updates its copy, this one
  does not follow until it is resynced (see below).
- Beds are read from the account when the integration loads. A bed added to or
  removed from the account shows up after **Settings > Devices & services >
  SleepIQ > Reload**, not on the next poll.
- The core entities keep core's naming (`SleepNumber {bed} ...` hard-coded in
  English); only the massage entities are translated. Bringing the core
  entities up to the same standard is planned; `quality_scale.yaml` records
  exactly which rules that affects.
- One failed read of any endpoint marks every entity of that poll unavailable
  until the next successful one.

## Troubleshooting

**"You are using a custom integration sleepiq which has not been tested by Home
Assistant"** in the log at startup - expected. It is the shadowing at work.

**Labels show as raw keys** such as `component.sleepiq.entity.select.massage_mode.state.soothe`
- the `translations/` folder did not make it into `custom_components/sleepiq/`.
Copy the whole folder from this repository and restart. Versions of this
repository before September 2026 shipped without it; update.

**Home Assistant asks you to re-authenticate SleepIQ** - the SleepNumber cloud
rejected the stored password. Enter the current one. If it keeps coming back,
sign in to the SleepIQ app to check the account is not locked.

**Everything is unavailable** - the cloud is unreachable or returning errors.
The log shows one line when the poll first fails and one when it recovers;
nothing is logged in between. Check the SleepIQ app; if it works, download the
diagnostics (below) and open an issue.

**No massage entities for my bed** - the foundation did not report the massage
board. Download the diagnostics and look at `foundation.features.hasMassageAndLight`.
If it is `false` and the bed has massage, open an issue with the diagnostics
attached; the gating flag would need widening.

**The massage stops after a few seconds** - you selected a Full Body pattern.
That is the open limitation above; use the head and foot speeds instead.

**The timer reads 0 shortly after I set it** - a massage was not started within
the bed's arming window. Set the timer, then start a speed straight after, as
in the examples.

**"The bed did not accept the massage change"** - the cloud refused the write.
The entity keeps its last known state. Try again; if it persists, the error
text carries the API's response code.

**Two sets of massage controls for one sleeper, or entity ids ending in `_2`
after updating** - versions before September 2026 keyed the massage entities
on the sleeper, which collides on a bed with one sleeper. The update migrates
the registered entities to side-keyed ids automatically; if a duplicate was
created by an earlier restart, delete the orphaned entity from **Settings >
Entities**.

**Diagnostics** - **Settings > Devices & services > SleepIQ > three dots >
Download diagnostics**. The file lists the beds, sleepers, foundation features
and the raw massage block, with the account, MAC address and first names
redacted. The mode select also keeps the raw massage block as attributes, so it
can be watched live while the vendor app drives the bed.

## Removal

1. **Settings > Devices & services > SleepIQ > three dots > Delete** removes the
   config entry, its devices and entities. Skip this if you want core's SleepIQ
   to keep the account; the entry is shared.
2. Remove the component: in HACS, open SleepIQ (with massage) and choose
   **Remove**; for a manual install delete `custom_components/sleepiq/`.
3. Restart Home Assistant.

Core's integration takes over again. Every non-massage entity keeps its unique
id and history; the massage entities become unavailable and can be deleted
from **Settings > Entities**. Nothing is stored outside the config entry.

## Keeping in sync with core

This shadows a core integration, which is the real cost of the approach. When
Home Assistant updates `sleepiq`, this copy does not follow.

`docs/UPSTREAM-BASELINE.txt` records the SHA-256 of each file as copied from
`home-assistant/core` at tag **2026.8.2**, and marks the files this project
modifies. To resync:

```bash
# fetch the same files at a newer tag and compare against the baseline
curl -s -o /tmp/select.py   https://raw.githubusercontent.com/home-assistant/core/<tag>/homeassistant/components/sleepiq/select.py
sha256sum /tmp/select.py
```

A changed hash means upstream moved and that file needs its massage additions
re-applied. `NOTICE` lists exactly which files were modified and how, so the
diff to carry forward is small. `python tools/validate_local.py` checks the
unmodified files still match and the modified ones are all described.

## Development

`python tools/validate_local.py` runs the offline checks: the vendored files
against the baseline, translations against icons and code, every user-facing
exception translated, the quality scale complete. `python -m pytest tests -q`
runs the massage model tests anywhere and the Home Assistant layer tests where
the test harness is installed (Linux; the GitHub Tests workflow runs them,
mypy in strict mode and coverage on every push).

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
