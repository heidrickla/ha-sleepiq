# SleepIQ (with massage)

Home Assistant's built-in `sleepiq` integration exposes firmness, head and foot
position, foundation presets, under-bed lights, pause mode and the sleep
sensors of a SleepNumber bed, but no massage. This custom component adds it:
per side, the full-body pattern, the head and foot motor speeds and the massage
timer, read back from the bed rather than assumed.

The domain is `sleepiq_massage`. It is a copy of the core integration with
massage support layered on, under its own domain, so it installs beside core's
`sleepiq` rather than replacing it. Everything core does, this does too; the
massage entities are the addition.

## Why core does not have it

The gap is not in Home Assistant, and it is not that beds lack the hardware.

`asyncsleepiq`, the library core depends on, can write massage but never reads
it. `SleepIQFoundation.set_foundation_massage()` ships and works, but the
library has no massage object, nothing calls `GET bed/{id}/foundation/massage`,
and the response fields (`footMassageMotorSpeed`, `headMassageMotorSpeed`,
`waveMode`, `massageTimer`) appear nowhere in it.

Without readback there is no state for an entity to display, so core exposes
none. This repo fills in the read half and reuses the library's existing write
half: no library fork, no patched dependency.

## Relationship to core's SleepIQ

There is no migration from core. Both integrations sign in to the same account
and create their own devices and entities.

| Situation | What happens |
| --- | --- |
| Core `sleepiq` is already set up | Nothing. Its config entry, entities and history stay under domain `sleepiq`. |
| Both are set up | Two sets of entities for the same bed. The second set's entity ids get a `_2` suffix, because the names collide. |
| You want one set | Delete core's config entry: Settings > Devices & services > SleepIQ > three dots > Delete. Its entities and their history go with it. |
| Upgrading from 0.1.0 of this repo | The 0.1.0 directory is left on disk and keeps shadowing core's `sleepiq`. Delete it, as below. |
| A bed is discovered by DHCP | Two cards, one per integration. Core's matcher is in Home Assistant itself; dropping this repo's matcher would leave core's card alone. |

Unique ids are registered against this integration's own platform, so they
never collide with core's even where the id string is the same.

### Upgrading from 0.1.0

0.1.0 used domain `sleepiq`, so it lived in `config/custom_components/sleepiq`.
HACS installs 0.2.0 into `config/custom_components/sleepiq_massage` and leaves
the 0.1.0 directory where it is: `remove_local_directory()` is called only from
`uninstall()`, never on an update, and the install path is derived from the
manifest domain of the version being downloaded. Home Assistant loads
`custom_components/sleepiq` in preference to the built-in `sleepiq`, so the
0.1.0 copy keeps serving that config entry and HACS no longer tracks it to
update it.

Do this after the update:

1. Delete `config/custom_components/sleepiq`.
2. Restart Home Assistant. Core's built-in `sleepiq` takes over the 0.1.0
   config entry and the massage entities disappear with the 0.1.0 code.
3. Add SleepIQ (with massage) from Add integration.
4. Delete the old entry if you want one set of entities.

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
- Not verified as of 2026-09-16: Climate360 and other Fuzion generation beds.
  The library drives them and the core entities should work. A massage read
  from one of those foundations would settle it.

## Supported functions

Every entity below is created and enabled by default. Each bed is one device,
and an entity's full name begins with the device name, which is the bed's name
in the SleepIQ app, so the tables show the part that follows it.

Per sleeper, from core:

| Entity | Platform | What it is |
| --- | --- | --- |
| `{bed} {sleeper} is in bed` | `binary_sensor` | Occupancy from the bed's pressure sensor |
| `{bed} {sleeper} pressure` | `sensor` | Raw air pressure reading, SleepNumber's own units |
| `{bed} {sleeper} SleepNumber` | `sensor` | Current firmness setting |
| `{bed} {sleeper} firmness` | `number` | Firmness, 5 to 100 in steps of 5 |
| `{bed} {sleeper} sleep score` | `sensor` | Last night's SleepIQ score |
| `{bed} {sleeper} sleep duration` | `sensor` | Last night's time in bed, hours |
| `{bed} {sleeper} average heart rate` | `sensor` | Last night's average heart rate |
| `{bed} {sleeper} average respiratory rate` | `sensor` | Last night's average breathing rate |
| `{bed} {sleeper} heart rate variability` | `sensor` | Last night's HRV, milliseconds |
| `{bed} {sleeper} foot warmer` | `select` | Foot warming: off, low, medium, high (beds with foot warming) |
| `{bed} {sleeper} foot warming timer` | `number` | Foot warming run time, 30 to 360 minutes |
| `{bed} {sleeper} core climate` | `select` | Climate360 heating and cooling levels (beds with core climate) |
| `{bed} {sleeper} core climate timer` | `number` | Core climate run time, 0 to 600 minutes |

The last four are hardware fitted per side of the bed, named after whoever
sleeps on that side. Core keys the foot warmer and core climate selects on the
sleeper, and a side with nobody registered on it falls back to the first
sleeper: on a bed with one registered sleeper both sides then ask for the same
unique id and Home Assistant keeps only the first entity. Here they are keyed on
the bed and the physical side, like the two timer numbers beside them, so the
bed gets both.

Per bed, from core:

| Entity | Platform | What it is |
| --- | --- | --- |
| `{bed} {Left/Right} {head/foot} position` | `number` | Actuator position, 0 to 100 (beds with an adjustable foundation) |
| `{bed} {Left/Right} foundation preset` | `select` | Favorite, Read, Watch TV, Flat, Zero G, Snore |
| `{bed} Light {n}` | `light` | Under-bed light or night stand outlet |
| `{bed} Pause mode` | `switch` | Privacy mode: stops the bed reporting sleep data |
| `{bed} Calibrate` | `button` | Re-baseline the pressure sensors. Filed under Configuration on the device page, because it sets the bed up rather than operating it |
| `{bed} Stop pump` | `button` | Stop a firmness adjustment in progress |

A foundation that reports no side names its positions and its preset without
one: `{bed} Head position`, `{bed} Foundation preset`.

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
vendor app's own: Smooth, Revitalize, Wave.

The massage entities are named by sleeper rather than by physical side, so the
mode entity for the right-hand sleeper reads "Amy massage mode" and not "Right
massage mode". That matches how core names the other per-sleeper comfort
hardware, the foot warmer and core climate. A side with no sleeper on the
account is named by position. Under the hood each entity is keyed on the bed
and the physical side, so a bed with one sleeper still gets two independent
sets of controls.

There are no actions (services), triggers or conditions; every function is an
entity.

## Installation

HACS: add this repository as a custom repository (category: Integration),
install, restart Home Assistant.

Manual: copy `custom_components/sleepiq_massage/` into your config directory's
`custom_components/`, then restart.

Either way Home Assistant logs that it found a custom integration
`sleepiq_massage` which it has not tested. That is expected of any custom
integration.

Then add it from Settings > Devices & services > Add integration > SleepIQ
(with massage). Read Relationship to core's SleepIQ above first if core's
`sleepiq` is already set up.

Minimum Home Assistant version: 2026.8.0.

### Installation parameters

| Field | Required | What to enter |
| --- | --- | --- |
| Username | yes | The email address you sign in to the SleepIQ app with. One entry covers every bed on the account. |
| Password | yes | The password for that account. It is stored in the config entry and never shown again. |

### Discovery

A SleepNumber bed on the same network is picked up by Home Assistant's DHCP
watcher. Core's `sleepiq` claims the same MAC prefix `64DBA0*` and Home
Assistant appends a custom integration's matchers to core's list instead of
replacing them, so one bed raises two cards: SleepIQ and SleepIQ (with massage).
Take the second. Core's card stays in the discovered list until it is set up or
ignored, and setting it up gives a second set of entities for the same bed.

The bed announces nothing about which SleepIQ account owns it, and this
integration talks to the cloud rather than to the bed, so the card opens the
same sign-in form. When this integration already has an entry its card is not
raised again: one entry covers every bed on the account. An entry of core's does
not suppress this card, and this one does not suppress core's.

### Configuration options

There are no options to configure after setup; the account is the only setting.

| Situation | What to do |
| --- | --- |
| The password changed | Home Assistant asks for the new one through a re-authentication prompt. |
| The username was wrong, or the account's email changed | Settings > Devices & services > SleepIQ (with massage) > three dots > Reconfigure. Leave the password blank to keep the stored one. |
| You want a second SleepIQ account | Add integration. Reconfigure refuses to point an entry at a different account, which would be a second entry with its own beds and history. |

## Data updates

Everything comes from the SleepNumber cloud; the bed itself is never contacted
directly, so nothing on your network needs configuring.

| Data | Interval |
| --- | --- |
| The account's list of beds | every 60 seconds |
| Presence, pressure, firmness, foundation positions, presets, lights, massage state | every 60 seconds |
| Pause mode | every 5 minutes |
| Sleep score, duration, heart rate, respiratory rate, HRV | every hour |

A write (firmness, position, massage, light) is sent immediately and the
entity shows the new value straight away. The massage entities then request a
refresh, so what you see a moment later is what the bed reports, not what was
asked for. The cloud's own view of the bed can lag a few seconds behind the
remote or the app.

Beds added or removed on the account are followed. The 60 second poll reads
the account's bed list; when it differs, the account is read again in full, a
new bed gets its device and its entities, and a bed that has left loses its
device and everything under it. No reload, no restart. A bed list that comes
back empty is treated as a cloud hiccup and changes nothing.

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
          entity_id: number.master_bedroom_amy_massage_timer
        data:
          value: 20
      - action: select.select_option
        target:
          entity_id: select.master_bedroom_amy_foot_massage_speed
        data:
          option: low
```

Stop the massage when the sleeper leaves the bed:

```yaml
automation:
  - alias: Massage off when out of bed
    triggers:
      - trigger: state
        entity_id: binary_sensor.master_bedroom_amy_is_in_bed
        to: "off"
        for: "00:02:00"
    actions:
      - action: select.select_option
        target:
          entity_id:
            - select.master_bedroom_amy_foot_massage_speed
            - select.master_bedroom_amy_head_massage_speed
        data:
          option: "off"
```

Entity ids follow the bed's name and the sleeper's first name; take the exact
ids from Settings > Devices & services > SleepIQ (with massage) > the bed.

## How the massage controls behave

### Mode and speed are mutually exclusive

This is an API rule, not a UI choice. `set_foundation_massage()` forces both
motor speeds to OFF whenever a wave mode is set, and the vendor app's massage
screen says the same: "Adjust either foot and head or full body massage". So:

- Selecting a mode other than off drives both speed entities to off.
- Selecting a non-off speed drives the mode entity to off.

If they did not, the UI would show a state the bed is not in.

### A speed write with no timer set sends 60 minutes

Selecting a speed with no timer set sends `massageTimer: 60`, the maximum the
vendor app and the physical remotes offer. It covers the expiry behaviour
below: the bed drops an idle timer, so a speed started without one has nothing
scheduled to stop it.

A mode write sends `waveMode` on its own and no timer. Nothing schedules the
end of a pattern from Home Assistant; see the full-body limitation below.

An explicitly set timer is never overridden. The logic is
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

`massageTimer` is exposed as a `number`, but it behaves as an armed countdown
rather than a stored preference. Measured on hardware:

| Action | Left | Right |
| --- | --- | --- |
| baseline | 0.0 | 0.0 |
| set left = 7 | **7.0** | 0.0 |
| +45 s, no motors started | **0.0** | 0.0 |
| set right = 12 | 0.0 | **12.0** |
| right speed -> low | 0.0 | **12.0** |

The timers are per-side and independent. Setting one never moves the other, so
the value on one side tells you nothing about the other. There is no shared
bed-wide timer to read.

An idle timer clears itself. Left was set to 7 and read back 7, then fell to 0
within 45 seconds with no motors running. The right side, which had a motor
started while its timer was set, held its value. A speed write does not disturb
the timer, as the fourth and fifth rows show. The consistent reading is that
the bed arms the timer and drops it if a massage does not begin; the exact
window is unmeasured as of 2026-09-16, and a run of set-then-wait at increasing
intervals would fix it.

So: set the timer, then start the massage promptly. Setting a timer and walking
away leaves nothing armed.

### The full-body patterns cannot be set from Home Assistant

Foot and head speed control works. The Full Body patterns, Smooth, Revitalize
and Wave, can be read but not written.

The read side is correct. Confirmed on hardware: setting Smooth for 1 hour from
the vendor phone app showed up in Home Assistant within one poll as
`mode=soothe`, `timer=60.0`, counting down to 58 a couple of minutes later. So
`waveMode 1 = Smooth`, the timer is in minutes, and 60 is the maximum.

On naming: the app's Full Body row is `Off / Smooth / Revitalize / Wave`; the
library enum is `OFF=0 / SOOTHE=1 / REVITILIZE=2 / WAVE=3`, the same order, so
`SOOTHE` is Smooth. The translations use the app's wording; the option keys
keep the library's spelling.

The write starts the pattern but it does not sustain. The request is not
rejected. The bed's owner watched the mattress and reported that the side did
turn on for a while during a test that Home Assistant had recorded as a total
failure. The pattern starts, runs briefly, and stops, and because `waveMode`
reads back `0` once it has stopped, the API view alone made it look like
nothing had happened.

Three request shapes have been tried, all on an idle side:

| Sent | Result |
| --- | --- |
| `massageWaveMode` + all five fields (`set_foundation_massage()`) | starts, stops |
| `waveMode` + `massageTimer` | starts, stops |
| `waveMode` alone | starts, stops |

A pattern set from the vendor phone app persists, so the correct request
differs from all three above.

One hypothesis, from the app's own UI: the massage screen gives Full Body its
own Start Timer, separate from the Foot/Head one. A pattern may need that timer
armed through a different field or endpoint, and without it the foundation runs
a brief burst and stops.

Writes use the app's partial-payload dialect rather than the library's
all-five-fields call: `{"footMassageMotor": N, "headMassageMotor": N,
"massageTimer": N, "side": "R"}`, matching what the app was observed sending.

### Other limitations

- This is a copy of core's `sleepiq`. When Home Assistant updates its copy,
  this one does not follow until it is resynced (see below).
- One failed read of any endpoint marks every entity of that poll unavailable
  until the next successful one.
- A bed is followed by the account's list, not by anything the bed itself
  announces, so a bed that the cloud stops listing while it is still yours,
  during an outage that answers with a short list rather than an error, would
  be removed. An empty list is ignored, a short one is not.

## Troubleshooting

| Symptom | Cause | What to do |
| --- | --- | --- |
| Log at startup: a custom integration `sleepiq_massage` has not been tested by Home Assistant | Every custom integration logs this | Nothing |
| Labels show as raw keys, such as `component.sleepiq_massage.entity.select.massage_mode.state.soothe` | The `translations/` folder is not in `custom_components/sleepiq_massage/` | Copy the whole folder from this repository and restart |
| Home Assistant asks you to re-authenticate | The SleepNumber cloud rejected the stored password | Enter the current one. If it keeps coming back, sign in to the SleepIQ app to check the account is not locked |
| Everything is unavailable | The cloud is unreachable or returning errors. The log carries one line when the poll first fails and one when it recovers, nothing in between | Check the SleepIQ app. If it works, download the diagnostics and open an issue |
| No massage entities for the bed | The foundation did not report the massage board | Download the diagnostics and read `foundation.features.hasMassageAndLight`. If it is `false` and the bed has massage, open an issue with the diagnostics attached; the gating flag would need widening |
| The massage stops after a few seconds | A Full Body pattern was selected | Use the head and foot speeds instead. See Known limitations |
| The timer reads 0 shortly after it was set | No massage was started inside the bed's arming window | Set the timer, then start a speed straight after, as in the examples |
| "The bed did not accept the change" or "The bed did not accept the massage change" | The cloud refused the write; the entity keeps its last known state | Try again. If it persists, the error text carries the API's response code |
| "The bed cannot be set to that" | The value was outside what the bed accepts, such as a firmness outside 5-100 or a foot warming time outside 30-360 | Use a value in range. The message carries the library's own explanation |
| A repair notice about the SleepIQ YAML configuration | The `sleepiq_massage:` block in `configuration.yaml` was imported into a config entry and now does nothing | Delete the block and restart. The notice clears with it and the account keeps working from the config entry |
| Two of every entity, or entity ids ending in `_2` | Core's `sleepiq` is set up on the same account | Delete one of the two config entries. See Relationship to core's SleepIQ |

Diagnostics: Settings > Devices & services > SleepIQ (with massage) > three
dots > Download diagnostics. The file lists the beds, sleepers, foundation
features and the raw massage block, with the account, the bed's name, its MAC
address and the sleepers' first names redacted. The mode select also keeps the
raw massage block as attributes, so it can be watched live while the vendor app
drives the bed.

## Removal

1. Settings > Devices & services > SleepIQ (with massage) > three dots >
   Delete removes the config entry, its devices and entities.
2. Remove the component: in HACS, open SleepIQ (with massage) and choose
   Remove; for a manual install delete `custom_components/sleepiq_massage/`.
3. Restart Home Assistant.

Nothing is stored outside the config entry. Core's `sleepiq`, if it is set up,
is untouched: it has its own config entry, its own entities and its own
history.

## Keeping in sync with core

When Home Assistant updates `sleepiq`, this copy does not follow.

`docs/UPSTREAM-BASELINE.txt` records the SHA-256 of each file as copied from
`home-assistant/core` at tag 2026.8.2, and marks the files this project
modifies. To resync:

```bash
# fetch the same files at a newer tag and compare against the baseline
curl -s -o /tmp/select.py   https://raw.githubusercontent.com/home-assistant/core/<tag>/homeassistant/components/sleepiq/select.py
sha256sum /tmp/select.py
```

A changed hash means upstream moved and that file needs this project's changes
re-applied. `NOTICE` lists exactly what those are, file by file. Every file is
marked `modified`: naming, icons and error handling run through all seven
platforms, so there is no untouched file to compare byte for byte. The recorded
hashes remain the starting point of the next resync diff, and
`python tools/validate_local.py` checks that every modified file is described.

## Development

`python tools/validate_local.py` runs the offline checks: the vendored files
against the baseline, translations against icons and code, every user-facing
exception translated, the manifest's published URLs against private address
space, the brand images against their required sizes, `PARALLEL_UPDATES` on
every platform, no `_attr_name` or `_attr_icon` left anywhere, the quality
scale complete, and every rule filed `done` against the mechanism it would need
to be true.

`python tools/make_brand.py` regenerates `custom_components/sleepiq_massage/brand/`
and measures what it wrote.

`python -m pytest tests -q` runs both suites: the massage model tests, which
need only `asyncsleepiq`, and the Home Assistant layer tests, which need
`pytest-homeassistant-custom-component`.

Three things make the Home Assistant suite run on a Windows workstation as well
as on the Linux CI runner, and all three are needed:

- `tests/winposix.py` stands in for `fcntl` and `resource`. Home Assistant
  2026.8 imports both while pytest is still loading the harness plugin, before
  any conftest runs, so without it the session aborts on
  `ModuleNotFoundError: No module named 'fcntl'` and not one test is collected.
  `pyproject.toml` loads it with `-p tests.winposix`, which pytest handles
  before the entry point plugins. Run pytest as `python -m pytest`, on either
  platform, so the repository root is on `sys.path`: a bare `pytest` stops with
  `Error importing plugin "tests.winposix"` unless the root is on `PYTHONPATH`.
  CI runs it as a module for the same reason.
- `tests/ha/conftest.py` hands the event loop a real socket pair for its own
  wakeup pipe, which the harness's socket block otherwise refuses.
- The same conftest puts Home Assistant on the selector loop, because aiodns
  refuses the proactor one Windows would pick.

None of the three does anything on Linux. On Windows the first test of a
session can still fail the harness's own teardown check on a lingering shutdown
thread; the assertions themselves run.

The GitHub Tests workflow is the check that counts: ruff, both suites over one
coverage total gated at 95%, mypy in strict mode with Home Assistant installed,
and the validator, on every push.

## Licence

The project is MIT, in `LICENSE`. The files in
`custom_components/sleepiq_massage/` are derived from Home Assistant core and
remain under Apache-2.0, whose text is in `LICENSE-APACHE` and whose file-by-file
record is in `NOTICE`.

## Upstreaming

The proper fix is upstream: add a massage object to `asyncsleepiq` (read and
write, wired into `init_features()` / `update()`), then add the entities to
`home-assistant/core`. The derived files are already Apache-2.0, which is core's
own licence, so they move upstream unchanged.

## Credits

`custom_components/sleepiq_massage/` is derived from the Home Assistant `sleepiq`
integration by @mfugate1 and @kbickar. See `NOTICE`.

The underlying API behaviour was confirmed by capturing the SleepIQ Android
app's own traffic.
