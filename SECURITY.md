# Security

This integration talks only to the SleepIQ cloud API through the `asyncsleepiq`
library, using the credentials stored in your Home Assistant config entry. It
adds no network listeners and stores nothing outside Home Assistant's own
config entry storage.

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's private
vulnerability reporting on this repository ("Security" tab, "Report a
vulnerability"). You should get an acknowledgement within a week.

Issues in the vendored Home Assistant code should also be reported upstream to
[home-assistant/core](https://github.com/home-assistant/core/security/policy),
and issues in the API client to
[asyncsleepiq](https://github.com/kbickar/asyncsleepiq).
