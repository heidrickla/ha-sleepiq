# Changelog

Newest first, in the style of
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] - 2026-09-16

### Changed

- Breaking: the domain is now `sleepiq_massage`. 0.1.0 used `sleepiq`, which is
  a core integration's domain, and HACS excludes a custom integration that
  overrides a core one. HACS installs this version into
  `config/custom_components/sleepiq_massage` and leaves
  `config/custom_components/sleepiq` on disk, where the 0.1.0 code keeps
  shadowing core's built-in `sleepiq` and never updates again. Delete that
  directory, restart, add SleepIQ (with massage) from Add integration, then
  delete the old entry if you want one set of entities; README has the
  sequence. There is no migration: unique ids
  under the new domain do not collide with core's, so both integrations can run
  side by side on the same account, with the second set's entity ids carrying a
  `_2` suffix. The deprecated YAML key moves with the domain, to
  `sleepiq_massage:`.
- The project licence is MIT, in `LICENSE`. The files in
  `custom_components/sleepiq_massage/` derived from Home Assistant core remain
  Apache-2.0; `docs/licenses/Apache-2.0.txt` carries that text and `NOTICE` has
  the file-by-file split, including the four added files, which are MIT. The
  Apache text is not a second root `LICENSE-*` file because GitHub reports
  NOASSERTION for a root with two licence-named files and HACS fails on that.
- `hacs.json` declares `"country": ["US"]`. Sleep Number sold through 570-plus
  stores in the United States and sleepnumber.com and nowhere else as of
  2026-09-16. Sleep Country Canada acquired the business in July 2026 and has
  named a Canadian rollout as an option with no date; when Sleep Number products
  reach Sleep Country or Dormez-vous, add CA. The key hides the store listing
  from HACS users who have set a different country, which defaults to ALL, and
  never affects an existing install.

### Added

- Brand art in `custom_components/sleepiq_massage/brand/`: `icon.png` 256x256,
  `icon@2x.png` 512x512, `logo.png` 512x256, `logo@2x.png` 1024x512.
  `tools/make_brand.py` regenerates them and checks each file against the
  exact size it wrote.

### Fixed

- Selecting a massage mode no longer shows a 60 minute timer. A mode write
  sends `waveMode` on its own and no `massageTimer`, so the entity was showing
  a value the bed had not been given and the next poll replaced. A speed write
  still sends 60 minutes when no timer is set.
- The diagnostics download no longer carries the bed's name, which owners set
  to a room or a person, and no longer dumps `entry.data` wholesale, which
  would have shipped anything the deprecated YAML block put in the entry.

### Development

- `tools/validate_local.py` fails a `documentation` or `issue_tracker` URL
  whose host is private, loopback, link-local, `localhost`, a `.local`, `.lan`
  or `.internal` name, or a bare hostname with no dot. It also fails
  `brands: done` when a brand file is missing or the wrong size.

## [0.1.0] - 2026-09-05

### Added

- Massage control per side of the bed: a wave-mode select, head and foot motor
  speed selects, and a timer, for beds whose foundation reports the massage
  board. Read back from the bed rather than assumed.
- Discovery. A SleepNumber bed seen by Home Assistant's DHCP watcher opens the
  sign-in form. When an account is already set up the discovery is ignored: one
  entry covers every bed on it.
- Reconfigure flow. The account an entry signs in with can be corrected in
  place. Leaving the password blank keeps the stored one; a username that
  belongs to a different account is refused.
- Beds added or removed on the account are followed without a reload. The 60
  second poll reads the account's bed list; a new bed gets its device and
  entities on the next poll, and a bed that has left the account loses its
  device and everything under it. A bed list that comes back empty is treated
  as a cloud hiccup and changes nothing.
- A repair notice when the deprecated YAML block is imported, naming the one
  action that clears it.
- Diagnostics download: beds, sleepers, foundation features, coordinator health
  and the raw massage block.
- Runtime translations. `translations/en.json` ships, so labels are words
  rather than raw keys.
- Field descriptions under the username and password on every form, and a
  masked password field that never echoes what was typed.

### Changed

- Every entity is named from the translation file. The device name is the bed
  and the entity adds only what it is. Entity ids, unique ids and history are
  untouched; only the display name changed.
- Icons come from `icons.json`, so a custom icon set for the domain applies.
  The presence sensor still shows an occupied or empty bed.
- Failed writes say what happened, in the user's language. Every control -
  preset, foot warmer, core climate, firmness, position, light, pause mode, the
  buttons and the massage entities - reports a refused write as an error on the
  action instead of a traceback in the log, and a value the bed cannot accept
  as a separate message.
- The calibrate button is filed under Configuration on the device page.
- A rejected password during a poll starts re-authentication instead of logging
  a traceback every 60 seconds.
- Setup and poll failures carry translated messages on the integration card:
  bad credentials, a login timeout, a failed bed read, a failed poll.
- Every platform declares `PARALLEL_UPDATES`: the read-only ones do not limit
  the coordinator, and every platform that writes to the bed sends one request
  at a time.
- The core climate timer's documented maximum is 600 minutes, which is what the
  library enforces; the README said "minutes" without a range.

### Fixed

- A bed with one sleeper got one set of massage controls instead of two. The
  massage entities were keyed on the sleeper, and a side with nobody on it
  resolved to the first sleeper, so the two sides collided. They are now keyed
  on the bed and the physical side.
- The same collision in the foot warmer and core climate selects, which are
  core's. Both were keyed on the sleeper, so a bed with one registered sleeper
  and hardware on both sides lost one entity of each pair. They are now keyed
  on the bed and the physical side, like the timer numbers beside them. This is
  a deliberate divergence from core.
- The README documented the massage mode value `revitalize`; the option key the
  library uses, and the one an automation must send, is `revitilize`.

### Documentation

- README: every entity and its default state, the installation fields,
  discovery, configuration options, the update cadence, use cases, examples,
  troubleshooting, and how to remove the integration.
- `quality_scale.yaml`: the Integration Quality Scale rule by rule, with the
  evidence for each. All 54 rules are `done` or `exempt`.
- `NOTICE` and `docs/UPSTREAM-BASELINE.txt` describe every file changed from
  the vendored copy of core's `sleepiq` at tag 2026.8.2.

### Development

- A GitHub Tests workflow runs on every push: ruff, both test suites over one
  coverage total gated at 95%, mypy in strict mode with Home Assistant
  installed, and the offline validator. Coverage is 100%.
- `tools/validate_local.py` refuses a quality scale rule filed `done` whose
  mechanism is not in the files.
- The Home Assistant test suite runs on a Windows workstation as well as on the
  Linux CI runner. It needs `tests/winposix.py`, which stands in for the `fcntl`
  and `resource` modules Home Assistant 2026.8 imports while pytest is still
  loading the harness plugin, before any conftest runs. `pyproject.toml` loads
  it with `-p tests.winposix`, so pytest must be run as `python -m pytest` on
  either platform, or with the repository root on `PYTHONPATH`. The module does
  nothing on Linux.
