"""Diagnostics for the SleepIQ integration."""

from __future__ import annotations

from typing import Any

from asyncsleepiq.bed import SleepIQBed

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import SleepIQConfigEntry
from .massage import SleepIQMassage

# The account, the bed's radio, and the household's first names. Bed and
# sleeper ids stay: they are what the entity unique ids are built from.
TO_REDACT = {CONF_USERNAME, CONF_PASSWORD, "mac_addr", "sleeper_name"}


def _massage(massage: SleepIQMassage) -> dict[str, Any]:
    return {
        "side": massage.side.value,
        "mode": massage.mode.name.lower(),
        "foot_speed": massage.foot_speed.name.lower(),
        "head_speed": massage.head_speed.name.lower(),
        "timer": massage.timer,
        "raw": dict(massage.raw),
    }


def _bed(bed: SleepIQBed, massage_sides: list[SleepIQMassage]) -> dict[str, Any]:
    foundation = bed.foundation
    return {
        "id": bed.id,
        "name": bed.name,
        "model": bed.model,
        "mac_addr": bed.mac_addr,
        "paused": bed.paused,
        "sleepers": [
            {
                "sleeper_id": sleeper.sleeper_id,
                "sleeper_name": sleeper.name,
                "side": sleeper.side.value,
                "in_bed": sleeper.in_bed,
                "sleep_number": sleeper.sleep_number,
                "pressure": sleeper.pressure,
            }
            for sleeper in bed.sleepers
        ],
        "foundation": {
            "type": foundation.type,
            "features": dict(foundation.features),
            "lights": [light.outlet_id for light in foundation.lights],
            "actuators": len(foundation.actuators),
            "presets": len(foundation.presets),
            "foot_warmers": len(foundation.foot_warmers),
            "core_climates": len(foundation.core_climates),
        },
        "massage": [_massage(massage) for massage in massage_sides],
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SleepIQConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data
    return async_redact_data(
        {
            "entry": dict(entry.data),
            "last_update_success": {
                "status": data.data_coordinator.last_update_success,
                "pause": data.pause_coordinator.last_update_success,
                "sleep_data": data.sleep_data_coordinator.last_update_success,
            },
            "beds": [
                _bed(bed, data.massage_sides.get(bed.id, []))
                for bed in data.client.beds.values()
            ],
        },
        TO_REDACT,
    )
