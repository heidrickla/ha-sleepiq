# Changelog

All notable changes to this project are recorded here, newest first, in the
style of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

`0.1.0` is the first release: `manifest.json` has said `0.1.0` since the first
commit, and everything below is what that release carries. Entries are dated by
the day the work landed.

## [0.1.0] - 2026-09-05

### Added

- **Massage control per side of the bed**: a wave-mode select, head and foot
  motor speed selects, and a timer, for beds whose foundation reports the
  massage board. Read back from the bed rather than assumed.
- **Discovery.** A SleepNumber bed seen by Home Assistant's DHCP watcher opens
  the SleepIQ sign-in form. When an account is already set up the discovery is
  ignored: one entry covers every bed on it.
- **Reconfigure flow.** The account an entry signs in with can be corrected in
  place from **Settings > Devices & services > SleepIQ > Reconfigure**. Leaving
  the password blank keeps the stored one; a username that belongs to a
  different account is refused.
- **Beds added or removed on the account are followed** without a reload. The
  60 second poll reads the account's bed list; a new bed gets its device and
  entities on the next poll, and a bed that has left the account loses its
  device and everything under it. A bed list that comes back empty is treated
  as a cloud hiccup and changes nothing.
- **A repair notice** when the deprecated `sleepiq:` YAML block is imported,
  naming the one action that clears it.
- **Diagnostics download**: beds, sleepers, foundation features, coordinator
  health and the raw massage block, with the account, the bed's MAC address and
  the sleepers' first names redacted.
- **Runtime translations.** `translations/en.json` now ships, so labels are
  words rather than raw keys such as
  `component.sleepiq.entity.select.massage_mode.state.soothe`.
- **Field descriptions** under the username and password on every form, and a
  masked password field that never echoes what was typed.

### Changed

- **Every entity is named from the translation file.** `SleepNumber Master
  Bedroom Lewis Firmness` is now `Master Bedroom Lewis firmness`: the device
  name is the bed, and the entity adds only what it is. Entity ids, unique ids
  and history are untouched - only the display name changed. This is a
  one-time rename on update.
- **Icons come from `icons.json`**, so a custom icon set for the domain now
  applies. The presence sensor still shows an occupied or empty bed.
- **Failed writes say what happened, in the user's language.** Every control -
  preset, foot warmer, core climate, firmness, position, light, pause mode,
  the buttons and the massage entities - reports a refused write as an error
  on the action instead of a traceback in the log, and a value the bed cannot
  accept as a separate message.
- **The calibrate button is filed under Configuration** on the device page.
- **A rejected password during a poll starts re-authentication** instead of
  logging a traceback every 60 seconds.
- **Setup and poll failures carry translated messages** on the integration
  card: bad credentials, a login timeout, a failed bed read, a failed poll.
- Every platform declares `PARALLEL_UPDATES`: the read-only ones do not limit
  the coordinator, and every platform that writes to the bed sends one request
  at a time.
- The core climate timer's documented maximum is 600 minutes, which is what the
  library enforces; the README said "minutes" without a range.

### Fixed

- **A bed with one sleeper got one set of massage controls instead of two.**
  The massage entities were keyed on the sleeper, and a side with nobody on it
  resolved to the first sleeper, so the two sides collided. They are now keyed
  on the bed and the physical side, and entities registered under the old ids
  are migrated automatically on update.
- **The same collision in the foot warmer and core climate selects**, which are
  core's. Both were keyed on the sleeper, so a bed with one registered sleeper
  and hardware on both sides lost one entity of each pair. They are now keyed on
  the bed and the physical side, like the timer numbers beside them, and an
  entity installed under core's id is migrated on update and keeps its entity id
  and history. This is a deliberate divergence from core: if core's SleepIQ
  takes over again it recreates those two selects under its own ids and the
  migrated ones are left to delete. README's Removal section says so.
- The README documented the massage mode value `revitalize`; the option key the
  library uses, and the one an automation must send, is `revitilize`.

### Documentation

- README: every entity and its default state, the installation fields,
  discovery, configuration options, the update cadence, use cases, examples,
  troubleshooting, and how to remove the integration.
- `custom_components/sleepiq/quality_scale.yaml`: the Integration Quality Scale
  rule by rule, with the evidence for each. All 54 rules are `done` or
  `exempt`.
- `NOTICE` and `docs/UPSTREAM-BASELINE.txt` describe every file changed from
  the vendored copy of core's `sleepiq` at tag 2026.8.2.

### Development

- A GitHub `Tests` workflow runs on every push: ruff, both test suites over one
  coverage total gated at 95%, mypy in strict mode with Home Assistant
  installed, and the offline validator. Coverage of
  `custom_components/sleepiq` is 100%.
- `tools/validate_local.py` refuses a quality scale rule filed `done` whose
  mechanism is not in the files.
- The Home Assistant test suite runs on a Windows workstation as well as on the
  Linux CI runner. It needs `tests/winposix.py`, which stands in for the `fcntl`
  and `resource` modules Home Assistant 2026.8 imports while pytest is still
  loading the harness plugin - before any conftest runs, so a Windows session
  aborted with `ModuleNotFoundError` and collected nothing. `pyproject.toml`
  loads it with `-p tests.winposix`, so pytest must be run as
  `python -m pytest` on either platform, or with the repository root on
  `PYTHONPATH`. The module itself does nothing on Linux.
