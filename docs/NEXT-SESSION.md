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

Capture the vendor app's own traffic (an Android emulator with a MITM proxy and
a certificate-pinning bypass is the setup that worked for the earlier captures):

1. Log into the app with the proxy in place.
2. Press **Smooth**, **Revitalize**, **Wave** in turn, pausing between each.
3. Also start one using the **Full Body Start Timer** - the app gives Full Body
   its own timer, separate from Foot/Head, and that separation is the leading
   hypothesis for why a pattern written without it runs only a burst.
4. Read the raw request bodies for `foundation/adjustment`.

One pass yields the correct field name and the integer for all three patterns.

## Cheaper alternative if the capture is unappealing

The mode entity exposes the **raw `foundation/massage` block** as entity
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
