# Changelog

Newest first, in the style of
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] - 2026-09-16

### Changed

- Breaking: the domain is now `sleepiq_massage`. 0.1.0 used `sleepiq`, a core
  integration's domain, and a custom component under a core domain shadows the
  built-in one entirely: Home Assistant loads `custom_components/sleepiq` in
  preference to core's `sleepiq`. HACS installs this version into
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
- `hacs.json` sets no `country`. The key filters the HACS store listing to the
  countries it names and hides the repository from every viewer whose HACS
  country is set to something else. The SleepIQ cloud is one global endpoint
  with no regional variant, and neither this integration nor `asyncsleepiq`
  reads a country, so a bed works wherever it is. Sleep Number's retail
  footprint is a purchase constraint, not an operating one, and Sleep Country
  Canada completed its acquisition of the business on 2026-07-31 with a
  Canadian and UK rollout announced in principle, so a `["US"]` value would
  have hidden the listing from those owners.
- A second discovered bed, or the same bed on a new DHCP lease, no longer
  raises a second card. `async_step_dhcp` defers to `ConfigFlow`'s
  `_async_handle_discovery_without_unique_id`, which adds an
  `already_in_progress` abort to the `already_configured` one. Core's
  `sleepiq` claims the same `64DBA0*` prefix and Home Assistant appends a
  custom integration's matchers to core's list, so a user who has not set core
  up still sees core's card beside this one; that card is core's and is not
  this integration's to suppress.
- `requires-python` is `>=3.14` and ruff targets `py314`. homeassistant
  2026.8.3 declares `Requires-Python >=3.14.2`, the Tests job installs 3.14 and
  the mypy block pins `python_version` 3.14. The formatter writes 3.14's
  parenthesis-free `except` clauses under that target.

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
- A failed YAML import now aborts with a dialog that has text.
  `async_step_import` aborts with reason `cannot_connect` or `invalid_auth`,
  both of which were declared only under `config.error`, which is read for an
  in-form error and not for an abort, so the reason resolved to no string.
  Both are now declared under `config.abort` as well, in `strings.json` and
  `translations/en.json`. Core's `sleepiq` has the same gap at 2026.8.3.
- The Tests workflow no longer passes `HA_DEV_HOST_NAMES` from a repository
  secret, and no longer fails when nothing supplies the names. No such secret
  exists; an undefined secret expands to the empty string, so the step behaved
  exactly as if the line were absent while reading as coverage, and the
  validator's refusal of an empty input turned the job red on its first push.
  A defined secret would have been worse: the first match inside a job would
  have published the name in a public run log, which is what the scan exists
  to prevent, and Actions masks a secret's exact value while the name matcher
  deliberately matches a longer word, so the string reaching the log is the one
  masking misses.
- No report of a matched host prints the host when `CI` or `GITHUB_ACTIONS` is
  set. `disclose()` keeps the string locally, where it is what the maintainer
  greps for, and replaces it in CI; the file, the line and the rule that fired
  are kept either way, because `tree_hits()` returns the rule with each hit.
  Applied at the published-tree scan, the object-database scan, both matcher
  controls and the manifest URL refusal. Nothing derived from the string is
  printed either: a truncated digest of a short host name is confirmable
  against a candidate list. The environment decides rather than a flag, because
  a workflow that forgot the flag would publish the string.

### Development

- `tools/validate_local.py` fails a `documentation` or `issue_tracker` URL
  whose host is private, CGNAT, link-local, unique-local, reserved, loopback,
  the unspecified address, `localhost`, an internal suffix or a bare hostname
  with no dot, and fails a value that is not an absolute http(s) URL. It also
  fails `brands: done` when a brand file is missing or the wrong size.
- `tools/validate_local.py` scans every text file `git ls-files` reports and
  fails on an address or internal name that belongs to a development network.
  The address space is pinned in `tools/_netblocks.py`, which is the one
  published file the scan skips and which may hold nothing but those three
  names. 51 files are read on this tree; a scan that reads none fails.
- The name half of both scans is live. `internal_names()` reads
  `HA_DEV_HOST_NAMES`, which holds the names comma or whitespace separated or
  the path of a file listing them, and falls back to `~/.config/ha-dev-hosts.txt`
  when the variable is unset. Both scans refuse each name with any trailing
  word characters. The names are never written into the tree, because that is
  the disclosure the scans exist to prevent. `scan_controls` fires one control
  per live matcher, so a clean result is never a broken matcher. No workflow
  supplies the names, so the name half is a local check; a matched string is
  printed locally and withheld when `CI` or `GITHUB_ACTIONS` is set. Measured
  2026-09-16 on a clone fetched over the wire, which carries the objects a ref
  reaches as a checkout does: `CI` and `GITHUB_ACTIONS` set with no name input,
  exit 0 and the note; a development name added to `README.md` with the variable
  set to it, exit 1 reporting the file, the line and the rule with the string
  withheld; the same off CI, exit 1 with the string printed; each of the
  address, URL and suffix matchers replaced in turn with one that matches
  nothing, exit 1 on that rule's control; the name matcher likewise, exit 1 on
  its control; the pristine tree with the real names supplied, exit 0. The
  object count rises with every commit, so it is quoted against the commit it
  was read at: a clone of `54a58db` fetched over the wire scans 326 objects,
  skips 4 as non-text and exempts 4. The authoring clone holds eight more
  objects no ref reaches, each one a real disclosure, so the validator exits 1
  there and exits 0 on the clone; only a history rewrite and a prune clear them.
- The name input's fallback path moved out of the tree, to
  `~/.config/ha-dev-hosts.txt`. The in-tree path it replaced was ignored only
  through `.git/info/exclude`, which no clone receives: measured in a clone over
  the git transport, `git check-ignore` exited 1 on that path, `git status`
  listed it, and writing the file the validator's own note asked for made the
  run exit 1 naming it. The out-of-tree path cannot be staged from any clone.
- `refuse_unpublished_paths` fails when `.claude/`, `.cursorrules`, `AGENTS.md`,
  `CLAUDE.md` or `docs/local/` is in `git ls-files --cached`. An ignore rule
  cannot carry that refusal: `.gitignore` ships, so its rules describe what they
  hide, and a rule in `.git/info/exclude` protects one machine. This check is in
  the tree, so it travels. Measured in a transport clone: `git add -f` on
  `CLAUDE.md` and on a file under `docs/local/` gives one failure each.
- The tree scan skips `docs/local/`, in the git branch and the walk branch
  alike. The walk honours no ignore rule, so an extracted tree with maintainer
  notes beside it had its notes read and their paths printed in the failure
  text.
- A phrase half joins the scans. `HA_DEV_PRIVATE_PHRASES`, or
  `~/.config/ha-dev-phrases.txt`, carries phrases that name private CI topology,
  account structure or lab tooling; each is matched case-insensitively as a
  substring over the published tree. That class holds no host, no address and no
  private suffix, so no address matcher sees it. The phrase half reads the
  published tree only: the object database holds commit messages of that class
  which no rewrite here can reach.
- An absent name or phrase input is a failure off CI and a note under `CI`. A
  note either way let a local run exit 0 with the name half covering nothing.
- The object scan withholds the matching object's SHA under `CI`. The SHA is a
  complete retrieval key on a public repository: `git cat-file -p` in any clone,
  and the REST blob endpoint with no clone at all, so printing it beside a
  withheld string published what the string was withheld for. Measured in a
  transport clone with `CI` set: the failure now names the object type and the
  rules and withholds the SHA. The count of failure lines is the count of
  matching objects, and a local run prints the SHAs.
- The object scan counts the objects it did not read beside the objects it did:
  a blob that is not UTF-8 and a blob over the size limit. A scanned count on
  its own reads as coverage.
- `SCAN_EXEMPT_OBJECTS` carries the true reason on each entry. One entry called
  its address an outside address while the address sits inside a pinned CIDR,
  and the entry for the object-scan measurement called the address published
  while none of the three exempt commits is in the published history.
- `const.VERSION` joins `manifest.json` and `pyproject.toml` as a third
  version field, and the validator refuses a mismatch between any of them.
- `.html` joins `PUBLISHED_SUFFIXES`, so an HTML file added to the tree is
  scanned rather than skipped. No such file ships today.
- The mypy block is Home Assistant core's generated `mypy.ini` `[mypy]` section
  at 2026.8.3 plus `strict`. The `tests.*` override dropped `strict = false`,
  which mypy 1.18.2 accepts in a per-module section and then uses to discard
  the whole section.
- Every Windows test shim lives in `tests/winposix.py`; `tests/ha/conftest.py`
  calls `install_ha_layer_shims()` instead of carrying its own copies.
- `tools/validate_local.py` also runs those matchers over every blob and commit
  message in `git cat-file --batch-all-objects`. The tree scan reads the index,
  so an object no ref reaches passes it, and a forge serves an unreachable
  commit by its SHA. A version of `tools/_netblocks.py` is skipped by its name
  in the tree; three commit messages that quote an address in the refused
  space are skipped by SHA in `SCAN_EXEMPT_OBJECTS`, each with its reason on
  its line. Two of them state the pinned CIDRs; the third records the
  measurement the object scan was built from and is reachable from `main`, so
  it is in every clone and commit messages are not rewritten here. The scan
  prints how many objects it exempts, so the hole is visible in the run rather
  than implied by a clean result.
- The object-database scan refuses a clone too shallow to scan. A clone carries
  the commits a ref reaches, not every object the authoring clone holds, and
  `actions/checkout` fetches depth 1 by default, which holds the tip commit
  object alone. `refuse_truncated_history()` fails on
  `git rev-parse --is-shallow-repository`, and again when the database holds
  one commit object while the clone has two or more refs. The Tests workflow
  checks out with `fetch-depth: 0`. Measured 2026-09-16 at commit `1e6b5dd`
  with names supplied: the authoring clone scans 356 objects and exits 1 on one
  commit message reachable from `main` plus eight objects no ref reaches; a
  full clone of that commit scans 317 and exits 1 on the reachable commit
  message alone; a `--depth 1` clone scans 51 and exits 1 on both truncation
  failures. Before the guard the same `--depth 1` clone printed "all offline
  checks passed" and exited 0. The object count rises with every commit, so it
  is quoted against that commit rather than against HEAD.
- `.gitignore` holds build and editor artefacts only. The rules that keep the
  local agent files and `docs/local/` out of the tree moved to
  `.git/info/exclude`, which `git ls-files --exclude-standard` reads and which
  no clone receives. Naming those paths in a published file advertised what it
  was hiding. Measured 2026-09-16: `git ls-files --others --exclude-standard`
  lists none of them after the move.
- The `tests/ha` count in the README Windows shim table is 77, matching
  `tests/winposix.py` and a collection of that directory. Measured 2026-09-16
  with each shim removed in turn: `install_posix_modules()` returning early
  aborts the session on `ModuleNotFoundError: No module named 'fcntl'` with 0
  collected; `install_socketpair_escape()` returning early gives 77 errors;
  `use_selector_event_loop()` replaced by a no-op gives 77 passed. The selector
  loop stops nothing here and sits below the table rather than in it.

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
