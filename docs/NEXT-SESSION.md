# Next session: capture the Full Body pattern request

Everything else works. The one open item is that **Full Body patterns (Smooth,
Revitalize, Wave) cannot be driven from Home Assistant.** They can be *read*
correctly; they just will not sustain when written.

## What is already established - do not re-derive

- **The read model is correct.** Setting Smooth for 1 hour from the vendor phone
  app appeared in HA as `mode=soothe`, `timer=60.0`, counting down minute by
  minute. `waveMode 1 = Smooth`, timer in minutes, 60 is the max.
- **`SOOTHE` is Smooth.** The library enum is `OFF=0 / SOOTHE=1 / REVITILIZE=2 /
  WAVE=3`; the app's row is `Off / Smooth / Revitalize / Wave`, same order.
- **The write is not rejected.** It starts the massage, which runs briefly and
  stops. This was only discovered by *watching the mattress* - the API state
  after the fact is identical to a rejected request. Do not trust the API view
  alone here.
- **The custom component is not the cause.** Patterns behaved the same with core
  installed. There is no write path outside an explicit service call.
- The bed has **four massage actuators, two per side** (head and foot).

## Three request shapes already tried, all failed the same way

| Sent to `foundation/adjustment` | Result |
| --- | --- |
| `massageWaveMode` + all five fields (`set_foundation_massage()`) | starts, stops |
| `waveMode` + `massageTimer` | starts, stops |
| `waveMode` alone | starts, stops |

**Do not guess a fourth field name.** Three attempts failed. Capture the real
request instead.

## The plan

The emulator rig on `[lab-host]` (`[lab-host]`) still has everything:

- AVD `mitm` at `[lab-path]vd`, Android 13, `-writable-system`
- mitmproxy CA already in the system trust store as `c8750f0d.0`
- SleepIQ 5.4.10 installed
- `frida-server` 16.7.19 at `/data/local/tmp/frida-server`
- Launchers `1-start-emulator.cmd` and `2-start-frida-bypass.cmd` in `[lab-path]`

Full instructions in the lab-notes repo under `projects/android-mitm/`.

1. Boot the emulator, start the frida bypass, log into the app.
2. Press **Smooth**, **Revitalize**, **Wave** in turn, pausing between each.
3. Also start one using the **Full Body Start Timer** - the app gives Full Body
   its own timer, separate from Foot/Head, and that separation is the leading
   hypothesis for why a pattern written without it runs only a burst.
4. Extract with `host/tools/mitm_extract_shapes.py`, or read the raw request
   bodies for `foundation/adjustment` directly.

One pass yields the correct field name and the integer for all three patterns.

## Cheaper alternative if the emulator is unappealing

The mode entity now exposes the **raw `foundation/massage` block** as entity
attributes. Drive the patterns from the phone and watch those attributes: if a
running pattern also drives `headMassageMotorSpeed` / `footMassageMotorSpeed`,
then the fix is that a pattern needs the motors on, and
`set_foundation_massage()` forcing both speeds to OFF is exactly what kills it.

That does not give the request shape, but it may give the answer without a
capture at all.

## Fixing it, once the request is known

`custom_components/sleepiq/massage.py`, `SleepIQMassage.set_mode()`. It is a
one-line change to the payload in `self._put({...})`. Everything else -
entities, translations, state model, timer defaulting - is already in place.


---

# CI on Gitea (2026-08-25)

Both repos moved off GitHub to the **the self-hosted Gitea** (`[forge-host]:3000`)
because GitHub Actions minutes are a budget line. `origin` is Gitea; `github`
remains as a secondary remote but nothing pushes there.

## Identity — do not use the shared admin account

Each repo authenticates as its **own non-admin Gitea user** with its **own SSH
key**, because several agent sessions push to this forge and the shared
`the shared admin account` password gets rotated out from under them (twice on 2026-08-25).

    account  [repo-account]        non-admin, write on lewis/ha-sleepiq only
    key      ~/.ssh/[repo-key]
    remote   gitea-ha-sleepiq:lewis/ha-sleepiq.git

⚠ The `~/.ssh/config` block is **alias-only, never the bare IP** — a block
setting `Port`/`User` on the bare IP hijacks `ssh <user>@[forge-host]` for host
shell access and breaks it for everyone.

## What CI does now, and why it is one job

`.gitea/workflows/validate.yml`. **The runner is shared and its capacity is 1**,
so an ordinary push runs ONE fast job; hassfest and HACS are
`workflow_dispatch` only. Do not raise capacity to make it faster — that was
tried and act_runner v0.6.1 corrupted job contexts.

The lint job: pinned ruff, the vendored-baseline guard, JSON validity, manifest
sanity, and a check that core-only `[%key:...]` refs have not returned.

## Three CI traps already paid for — do not rediscover them

1. **Pin the linter.** The job passed locally and failed in CI purely because
   `pip install ruff` fetched a newer default rule set. Pinned to `0.15.21`.
2. **`ruff.toml` mirrors core's isort config.** 20 of 23 initial errors were in
   `sensor.py`/`switch.py` — vendored files this project never touched.
   Reformatting them would break every hash in `UPSTREAM-BASELINE.txt` and make
   upstream resyncs harder for no benefit. The CI baseline guard now fails if a
   vendored file drifts, which is damage nothing else would catch.
3. **No `ast.parse` step.** One existed and failed *valid* code: HA needs
   Python 3.13 and uses PEP 695 `type X = ...`, while the runner image ships
   **Python 3.10.12**. Ruff already parses at `py313`. Do not reintroduce it
   without pinning a 3.13 toolchain.

## Reading CI results without admin

The admin credential was rotated, so the Actions API is not available. Logs live
on the box:

    ssh <user>@[forge-host]
    sudo docker exec gitea sh -c 'find /data/gitea/actions_log/lewis/ha-sleepiq -name "*.log.zst"'
    sudo docker cp gitea:<path> /tmp/x.zst && zstd -dc /tmp/x.zst | ...

⛔ **A missing log file does NOT mean the task was never created.** Logs appear
only once a job *starts*. With capacity 1 and other agents queued ahead, a task
can exist and be waiting with no log on disk. That was misread once as "the
scheduler is broken" when the real state was "queued behind someone else's
pytest run". Check `docker ps` for a `GITEA-ACTIONS-*` container before
concluding anything.
