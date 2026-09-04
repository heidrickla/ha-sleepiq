"""Support for SleepIQ foundation preset selection."""

from collections.abc import Coroutine
from typing import Any, override

from asyncsleepiq import (
    CoreTemps,
    FootWarmingTemps,
    Mode,
    Side,
    SleepIQAPIException,
    SleepIQBed,
    SleepIQCoreClimate,
    SleepIQFootWarmer,
    SleepIQLoginException,
    SleepIQPreset,
    SleepIQTimeoutException,
    Speed,
)

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CORE_CLIMATE,
    DOMAIN,
    FOOT_WARMER,
    MASSAGE_FOOT_SPEED,
    MASSAGE_HEAD_SPEED,
    MASSAGE_MODE,
)
from .coordinator import SleepIQConfigEntry, SleepIQDataUpdateCoordinator
from .entity import SleepIQBedEntity, SleepIQSleeperEntity, sleeper_for_side
from .massage import SleepIQMassage, massage_label

# Every select writes to the bed; the cloud API is happiest with one request
# in flight per account.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SleepIQConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the SleepIQ foundation preset select entities."""
    data = entry.runtime_data
    entities: list[SleepIQBedEntity[SleepIQDataUpdateCoordinator]] = []
    for bed in data.client.beds.values():
        entities.extend(
            SleepIQSelectEntity(data.data_coordinator, bed, preset)
            for preset in bed.foundation.presets
        )
        entities.extend(
            SleepIQFootWarmingTempSelectEntity(data.data_coordinator, bed, foot_warmer)
            for foot_warmer in bed.foundation.foot_warmers
        )
        entities.extend(
            SleepIQCoreTempSelectEntity(data.data_coordinator, bed, core_climate)
            for core_climate in bed.foundation.core_climates
        )
        for massage in data.massage_sides.get(bed.id, []):
            entities.append(
                SleepIQMassageModeSelect(data.data_coordinator, bed, massage)
            )
            entities.append(
                SleepIQMassageSpeedSelect(
                    data.data_coordinator, bed, massage, "foot", MASSAGE_FOOT_SPEED
                )
            )
            entities.append(
                SleepIQMassageSpeedSelect(
                    data.data_coordinator, bed, massage, "head", MASSAGE_HEAD_SPEED
                )
            )
    async_add_entities(entities)


class SleepIQSelectEntity(SleepIQBedEntity[SleepIQDataUpdateCoordinator], SelectEntity):
    """Representation of a SleepIQ select entity."""

    def __init__(
        self,
        coordinator: SleepIQDataUpdateCoordinator,
        bed: SleepIQBed,
        preset: SleepIQPreset,
    ) -> None:
        """Initialize the select entity."""
        self.preset = preset

        self._attr_name = f"SleepNumber {bed.name} Foundation Preset"
        self._attr_unique_id = f"{bed.id}_preset"
        if preset.side != Side.NONE:
            self._attr_name += f" {preset.side_full}"
            self._attr_unique_id += f"_{preset.side.value}"
        self._attr_options = preset.options

        super().__init__(coordinator, bed)
        self._async_update_attrs()

    @callback
    @override
    def _async_update_attrs(self) -> None:
        """Update entity attributes."""
        self._attr_current_option = self.preset.preset

    @override
    async def async_select_option(self, option: str) -> None:
        """Change the current preset."""
        await self.preset.set_preset(option)
        self._attr_current_option = option
        self.async_write_ha_state()


class SleepIQFootWarmingTempSelectEntity(
    SleepIQSleeperEntity[SleepIQDataUpdateCoordinator], SelectEntity
):
    """Representation of a SleepIQ foot warming temperature select entity."""

    _attr_icon = "mdi:heat-wave"
    _attr_options = [e.name.lower() for e in FootWarmingTemps]
    _attr_translation_key = "foot_warmer_temp"

    def __init__(
        self,
        coordinator: SleepIQDataUpdateCoordinator,
        bed: SleepIQBed,
        foot_warmer: SleepIQFootWarmer,
    ) -> None:
        """Initialize the select entity."""
        self.foot_warmer = foot_warmer
        sleeper = sleeper_for_side(bed, foot_warmer.side)
        super().__init__(coordinator, bed, sleeper, FOOT_WARMER)
        self._async_update_attrs()

    @callback
    @override
    def _async_update_attrs(self) -> None:
        """Update entity attributes."""
        self._attr_current_option = FootWarmingTemps(
            self.foot_warmer.temperature
        ).name.lower()

    @override
    async def async_select_option(self, option: str) -> None:
        """Change the current preset."""
        temperature = FootWarmingTemps[option.upper()]
        timer = self.foot_warmer.timer or 120

        if temperature == 0:
            await self.foot_warmer.turn_off()
        else:
            await self.foot_warmer.turn_on(temperature, timer)

        self._attr_current_option = option
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()


class SleepIQCoreTempSelectEntity(
    SleepIQSleeperEntity[SleepIQDataUpdateCoordinator], SelectEntity
):
    """Representation of a SleepIQ core climate temperature select entity."""

    # Maps to translate between asyncsleepiq and HA's naming preference
    SLEEPIQ_TO_HA_CORE_TEMP_MAP = {
        CoreTemps.OFF: "off",
        CoreTemps.HEATING_PUSH_LOW: "heating_low",
        CoreTemps.HEATING_PUSH_MED: "heating_medium",
        CoreTemps.HEATING_PUSH_HIGH: "heating_high",
        CoreTemps.COOLING_PULL_LOW: "cooling_low",
        CoreTemps.COOLING_PULL_MED: "cooling_medium",
        CoreTemps.COOLING_PULL_HIGH: "cooling_high",
    }
    HA_TO_SLEEPIQ_CORE_TEMP_MAP = {v: k for k, v in SLEEPIQ_TO_HA_CORE_TEMP_MAP.items()}

    _attr_icon = "mdi:heat-wave"
    _attr_options = list(SLEEPIQ_TO_HA_CORE_TEMP_MAP.values())
    _attr_translation_key = "core_temps"

    def __init__(
        self,
        coordinator: SleepIQDataUpdateCoordinator,
        bed: SleepIQBed,
        core_climate: SleepIQCoreClimate,
    ) -> None:
        """Initialize the select entity."""
        self.core_climate = core_climate
        sleeper = sleeper_for_side(bed, core_climate.side)
        super().__init__(coordinator, bed, sleeper, CORE_CLIMATE)
        self._async_update_attrs()

    @callback
    @override
    def _async_update_attrs(self) -> None:
        """Update entity attributes."""
        sleepiq_option = CoreTemps(self.core_climate.temperature)
        self._attr_current_option = self.SLEEPIQ_TO_HA_CORE_TEMP_MAP[sleepiq_option]

    @override
    async def async_select_option(self, option: str) -> None:
        """Change the current preset."""
        temperature = self.HA_TO_SLEEPIQ_CORE_TEMP_MAP[option]
        timer = self.core_climate.timer or 240

        if temperature == CoreTemps.OFF:
            await self.core_climate.turn_off()
        else:
            await self.core_climate.turn_on(temperature, timer)

        self._attr_current_option = option
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()


class SleepIQMassageSelect(
    SleepIQBedEntity[SleepIQDataUpdateCoordinator], SelectEntity
):
    """Common shape of the massage selects for one side of a bed.

    Named by sleeper rather than by physical side, matching how core names the
    other per-sleeper comfort hardware (foot warmer, core climate). "Lewis
    massage mode" is what someone reaches for; "Right massage mode" makes them
    work out which side they are. The unique id, though, is keyed on the
    physical side, so a bed with one sleeper still gets two distinct entities.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SleepIQDataUpdateCoordinator,
        bed: SleepIQBed,
        massage: SleepIQMassage,
        key: str,
    ) -> None:
        """Initialize a massage select."""
        self.massage = massage
        self._attr_translation_key = key
        self._attr_translation_placeholders = {
            "sleeper": massage_label(bed, massage.side)
        }
        self._attr_unique_id = f"{bed.id}_{massage.side.value}_{key}"
        super().__init__(coordinator, bed)

    @property
    @override
    def icon(self) -> None:
        """No entity icon: icons.json supplies one through the translation key.

        The bed base class sets _attr_icon to mdi:bed for every coordinator
        entity, which would otherwise override the translated icon.
        """
        return None

    async def _async_write(self, request: Coroutine[Any, Any, None]) -> None:
        """Send one write to the bed, translating a refusal for the user."""
        try:
            await request
        except (
            SleepIQAPIException,
            SleepIQLoginException,
            SleepIQTimeoutException,
        ) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="massage_write_failed",
                translation_placeholders={"error": str(err)},
            ) from err


class SleepIQMassageModeSelect(SleepIQMassageSelect):
    """Wave-mode selection for one sleeper's side of the bed."""

    _attr_options = [mode.name.lower() for mode in Mode]

    def __init__(
        self,
        coordinator: SleepIQDataUpdateCoordinator,
        bed: SleepIQBed,
        massage: SleepIQMassage,
    ) -> None:
        """Initialize the massage mode select."""
        super().__init__(coordinator, bed, massage, MASSAGE_MODE)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the raw foundation/massage block for this side.

        Lets the full field set be observed live while the vendor app drives
        the bed, which is how the pattern behaviour is being worked out. The
        same block is in the diagnostics download as a snapshot.
        """
        return dict(self.massage.raw)

    @callback
    @override
    def _async_update_attrs(self) -> None:
        """Update entity attributes."""
        self._attr_current_option = self.massage.mode.name.lower()

    @override
    async def async_select_option(self, option: str) -> None:
        """Set the wave mode.

        Selecting any mode other than off cancels the motor speeds - the API
        treats mode and speed as mutually exclusive, so the speed entities will
        follow to off on the next refresh.
        """
        await self._async_write(self.massage.set_mode(Mode[option.upper()]))
        self._attr_current_option = option
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()


class SleepIQMassageSpeedSelect(SleepIQMassageSelect):
    """Motor speed for the head or foot motor on one sleeper's side."""

    _attr_options = [speed.name.lower() for speed in Speed]

    def __init__(
        self,
        coordinator: SleepIQDataUpdateCoordinator,
        bed: SleepIQBed,
        massage: SleepIQMassage,
        end: str,
        key: str,
    ) -> None:
        """Initialize the massage speed select."""
        self.end = end
        super().__init__(coordinator, bed, massage, key)

    @property
    def _speed(self) -> Speed:
        """Return the speed of the motor this entity controls."""
        return (
            self.massage.foot_speed if self.end == "foot" else self.massage.head_speed
        )

    @callback
    @override
    def _async_update_attrs(self) -> None:
        """Update entity attributes."""
        self._attr_current_option = self._speed.name.lower()

    @override
    async def async_select_option(self, option: str) -> None:
        """Set this motor's speed.

        Any non-off speed cancels the wave mode, mirroring the API contract.
        """
        speed = Speed[option.upper()]
        if self.end == "foot":
            request = self.massage.set_speeds(foot_speed=speed)
        else:
            request = self.massage.set_speeds(head_speed=speed)
        await self._async_write(request)
        self._attr_current_option = option
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()
