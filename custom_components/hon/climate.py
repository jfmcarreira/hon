import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityDescription,
)
from homeassistant.components.climate.const import (
    SWING_OFF,
    SWING_BOTH,
    SWING_VERTICAL,
    SWING_HORIZONTAL,
    PRESET_NONE,
    PRESET_BOOST,
    PRESET_SLEEP,
    PRESET_ECO,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    UnitOfTemperature,
)
from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from pyhon.appliance import HonAppliance
from pyhon.parameter.range import HonParameterRange

from .const import HON_HVAC_MODE, HON_FAN, DOMAIN, HON_HVAC_PROGRAM, AC_POSITION_VERTICAL
from .entity import HonEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class HonACClimateEntityDescription(ClimateEntityDescription):
    pass


@dataclass(frozen=True)
class HonClimateEntityDescription(ClimateEntityDescription):
    mode: HVACMode = HVACMode.AUTO


CLIMATES: dict[
    str, tuple[HonACClimateEntityDescription | HonClimateEntityDescription, ...]
] = {
    "AC": (
        HonACClimateEntityDescription(
            key="settings",
            name="Air Conditioner",
            icon="mdi:air-conditioner",
            translation_key="air_conditioner",
        ),
    ),
    "REF": (
        HonClimateEntityDescription(
            key="settings.tempSelZ1",
            mode=HVACMode.COOL,
            name="Fridge",
            icon="mdi:thermometer",
            translation_key="fridge",
        ),
        HonClimateEntityDescription(
            key="settings.tempSelZ2",
            mode=HVACMode.COOL,
            name="Freezer",
            icon="mdi:snowflake-thermometer",
            translation_key="freezer",
        ),
        HonClimateEntityDescription(
            key="settings.tempSelZ3",
            mode=HVACMode.COOL,
            name="MyZone",
            icon="mdi:thermometer",
            translation_key="my_zone",
        ),
    ),
    "OV": (
        HonClimateEntityDescription(
            key="settings.tempSel",
            mode=HVACMode.HEAT,
            name="Oven",
            icon="mdi:thermometer",
            translation_key="oven",
        ),
    ),
    "WC": (
        HonClimateEntityDescription(
            key="settings.tempSel",
            mode=HVACMode.COOL,
            name="Wine Cellar",
            icon="mdi:thermometer",
            translation_key="wine",
        ),
        HonClimateEntityDescription(
            key="settings.tempSelZ2",
            mode=HVACMode.COOL,
            name="Wine Cellar",
            icon="mdi:thermometer",
            translation_key="wine",
        ),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entities = []
    entity: HonClimateEntity | HonACClimateEntity
    for device in hass.data[DOMAIN][entry.unique_id]["hon"].appliances:
        for description in CLIMATES.get(device.appliance_type, []):
            if isinstance(description, HonACClimateEntityDescription):
                if description.key not in list(device.commands):
                    continue
                entity = HonACClimateEntity(hass, entry, device, description)
            elif isinstance(description, HonClimateEntityDescription):
                if description.key not in device.available_settings:
                    continue
                entity = HonClimateEntity(hass, entry, device, description)
            else:
                continue  # type: ignore[unreachable]
            entities.append(entity)
    async_add_entities(entities)


class HonACClimateEntity(HonEntity, ClimateEntity):
    entity_description: HonACClimateEntityDescription
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device: HonAppliance,
        description: HonACClimateEntityDescription,
    ) -> None:
        super().__init__(hass, entry, device, description)

        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._set_temperature_bound()

        self._attr_hvac_modes = [HVACMode.OFF]
        for mode in device.settings["settings.machMode"].values:
            self._attr_hvac_modes.append(HON_HVAC_MODE[int(mode)])
        self._attr_preset_modes = []
        self._attr_preset_modes.append(PRESET_NONE)
        self._attr_preset_modes.append(PRESET_SLEEP)
        self._attr_preset_modes.append(PRESET_BOOST)
        self._attr_preset_modes.append(PRESET_ECO)
        # for mode in device.settings["startProgram.program"].values:
        #     self._attr_preset_modes.append(mode)
        self._attr_swing_modes = [
            SWING_OFF,
            "swing",
            "position_1",
            "position_2",
            "position_3",
            "position_4",
            "position_5",
            SWING_VERTICAL,
            #SWING_HORIZONTAL,
            #SWING_BOTH,
        ]
        self._attr_supported_features = (
            ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.SWING_MODE
            | ClimateEntityFeature.PRESET_MODE
        )

        self._handle_coordinator_update(update=False)

    def _set_temperature_bound(self) -> None:
        temperature = self._device.settings["settings.tempSel"]
        if not isinstance(temperature, HonParameterRange):
            raise ValueError
        self._attr_max_temp = temperature.max
        self._attr_target_temperature_step = temperature.step
        self._attr_min_temp = temperature.min

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self._device.get("tempSel", 0.0)

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._device.get("tempIndoor", 0.0)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        if "settings.machMode" in self._device.settings:
            current_mach = self._device.get("machMode")
            if current_mach is not None:
                self._device.settings["settings.machMode"].value = str(int(current_mach))
        if "settings.onOffStatus" in self._device.settings:
            current_onoff = self._device.get("onOffStatus")
            if current_onoff is not None:
                self._device.settings["settings.onOffStatus"].value = str(int(current_onoff))

        self._device.settings["settings.tempSel"].value = str(int(temperature))
        self._device.settings["settings.echoStatus"].value = "1"
        await self._device.commands["settings"].send()
        self.schedule_update_ha_state()

    @property
    def hvac_mode(self) -> HVACMode:
        on_off = self._device.get("onOffStatus")
        mach = self._device.get("machMode")

        if on_off == 0:
            return HVACMode.OFF

        if mach not in HON_HVAC_MODE:
            return getattr(self, "_attr_hvac_mode", HVACMode.AUTO)

        mode = HON_HVAC_MODE[mach]

        if mode == HVACMode.AUTO and getattr(self, "_attr_hvac_mode", None) not in (
            None,
            HVACMode.OFF,
            HVACMode.AUTO,
        ):
            return self._attr_hvac_mode

        return mode

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._attr_hvac_mode = hvac_mode
        if hvac_mode == HVACMode.OFF:
            self._device.settings["stopProgram.echoStatus"].value = "1"
            self._device.settings["stopProgram.tempSel"].value = self._device.settings["settings.tempSel"].value
            self._device.settings["stopProgram.windSpeed"].value = self._device.settings["settings.windSpeed"].value
            self._device.settings["stopProgram.windDirectionVertical"].value = self._device.settings["settings.windDirectionVertical"].value
            await self._device.commands["stopProgram"].send()
            self._device.settings["settings.onOffStatus"].value = "0"
        elif hvac_mode == HVACMode.FAN_ONLY:
            if program := self._device.settings.get("startProgram.program"):
                program.value = "iot_fan"
            self._device.settings["startProgram.echoStatus"].value = "1"
            self._device.settings["startProgram.tempSel"].value = self._device.settings["settings.tempSel"].value
            self._device.settings["startProgram.windDirectionVertical"].value = self._device.settings["settings.windDirectionVertical"].value
            await self._device.commands["startProgram"].send()
        else:
            self._device.settings["settings.onOffStatus"].value = "1"
            setting = self._device.settings["settings.machMode"]
            modes = {HON_HVAC_MODE[int(number)]: number for number in setting.values}
            if hvac_mode in modes:
                setting.value = modes[hvac_mode]
            else:
                await self.async_set_preset_mode(HON_HVAC_PROGRAM[hvac_mode])
                return
            self._device.settings["settings.echoStatus"].value = "1"
            await self._device.commands["settings"].send()
        self.schedule_update_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._device.settings["startProgram.echoStatus"].value = "1"
        self._device.settings["startProgram.windSpeed"].value = self._device.settings["settings.windSpeed"].value
        self._device.settings["startProgram.windDirectionVertical"].value = self._device.settings["settings.windDirectionVertical"].value
        self._device.settings["startProgram.machMode"].value = self._device.settings["settings.machMode"].value
        await self._device.commands["startProgram"].send()
        self._device.sync_command("startProgram", "settings")

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._device.settings["stopProgram.echoStatus"].value = "1"
        self._device.settings["stopProgram.tempSel"].value = self._device.settings["settings.tempSel"].value
        self._device.settings["stopProgram.windSpeed"].value = self._device.settings["settings.windSpeed"].value
        self._device.settings["stopProgram.windDirectionVertical"].value = self._device.settings["settings.windDirectionVertical"].value
        await self._device.commands["stopProgram"].send()
        self._device.sync_command("stopProgram", "settings")
        self._device.settings["settings.onOffStatus"].value = "0"


    @property
    def preset_mode(self) -> str | None:
        """Return the current Preset for this channel."""
        if self._device.get("silentSleepStatus", 0) == 1:
            return PRESET_SLEEP
        if self._device.get("rapidMode", 0) == 1:
            return PRESET_BOOST
        if self._device.get("muteStatus", 0) == 1:
            return PRESET_ECO
        return PRESET_NONE

    async def async_set_preset_mode(self, preset_mode) -> None:
        self._device.settings["settings.muteStatus"].value = "0"
        self._device.settings["settings.silentSleepStatus"].value = "0"
        self._device.settings["settings.rapidMode"].value = "0"

        if preset_mode == PRESET_SLEEP:
            self._device.settings["settings.silentSleepStatus"].value = "1"
        elif preset_mode == PRESET_BOOST:
            self._device.settings["settings.rapidMode"].value = "1"
        elif preset_mode == PRESET_ECO:
            self._device.settings["settings.muteStatus"].value = "1"

        self._device.settings["settings.echoStatus"].value = "1"
        await self._device.commands["settings"].send()
        self.schedule_update_ha_state()

    async def async_start_program(self, preset_mode: str) -> None:
        """Set the new preset mode."""
        if program := self._device.settings.get("startProgram.program"):
            program.value = preset_mode
        self._device.sync_command("startProgram", "settings")
        self._set_temperature_bound()
        self._handle_coordinator_update(update=False)
        self.coordinator.async_set_updated_data({})
        self._attr_preset_mode = preset_mode
        self._device.settings["startProgram.echoStatus"].value = "1"
        await self._device.commands["startProgram"].send()
        self.schedule_update_ha_state()

    @property
    def fan_modes(self) -> list[str]:
        """Return the list of available fan modes."""
        fan_modes = []
        for mode in reversed(self._device.settings["settings.windSpeed"].values):
            fan_modes.append(HON_FAN[int(mode)])
        return fan_modes

    @property
    def fan_mode(self) -> str | None:
        """Return the fan setting."""
        return HON_FAN[self._device.get("windSpeed")]

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        if "settings.machMode" in self._device.settings:
            current_mach = self._device.get("machMode")
            if current_mach is not None:
                self._device.settings["settings.machMode"].value = str(int(current_mach))
        if "settings.onOffStatus" in self._device.settings:
            current_onoff = self._device.get("onOffStatus")
            if current_onoff is not None:
                self._device.settings["settings.onOffStatus"].value = str(int(current_onoff))

        fan_modes: dict[str, str] = {}
        for mode in reversed(self._device.settings["settings.windSpeed"].values):
            fan_modes[HON_FAN[int(mode)]] = mode
        self._device.settings["settings.windSpeed"].value = str(fan_modes[fan_mode])
        self._attr_fan_mode = fan_mode
        self._device.settings["settings.echoStatus"].value = "1"
        await self._device.commands["settings"].send()
        self.schedule_update_ha_state()

    @property
    def swing_mode(self) -> str | None:
        """Return the swing setting."""
        horizontal = self._device.get("windDirectionHorizontal")
        vertical = self._device.get("windDirectionVertical")
        if vertical == 2 or vertical == 4 or vertical == 5 or vertical == 6 or vertical == 7:
            return AC_POSITION_VERTICAL[vertical]
        # if horizontal == 7 and vertical == 8:
        #     return SWING_BOTH
        # if horizontal == 7:
        #     return SWING_HORIZONTAL
        if vertical == 8:
            return SWING_VERTICAL
        return SWING_OFF

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        if "settings.machMode" in self._device.settings:
            current_mach = self._device.get("machMode")
            if current_mach is not None:
                self._device.settings["settings.machMode"].value = str(int(current_mach))
        if "settings.onOffStatus" in self._device.settings:
            current_onoff = self._device.get("onOffStatus")
            if current_onoff is not None:
                self._device.settings["settings.onOffStatus"].value = str(int(current_onoff))

        #horizontal = self._device.settings["settings.windDirectionHorizontal"]
        vertical = self._device.settings["settings.windDirectionVertical"]
        if swing_mode == "position_1":
            vertical.value = "2"
        elif swing_mode == "position_2":
            vertical.value = "4"
        elif swing_mode == "position_3":
            vertical.value = "5"
        elif swing_mode == "position_4":
            vertical.value = "6"
        elif swing_mode == "position_5":
            vertical.value = "7"
        # if swing_mode in [SWING_BOTH, SWING_HORIZONTAL]:
        #     horizontal.value = "7"
        elif swing_mode in ["swing", SWING_BOTH, SWING_VERTICAL]:
            vertical.value = "8"
        # if swing_mode in [SWING_OFF, SWING_HORIZONTAL] and vertical.value == "8":
        #     vertical.value = "5"
        # if swing_mode in [SWING_OFF, SWING_VERTICAL] and horizontal.value == "7":
        #     horizontal.value = "0"
        else:
            vertical.value = "5"
        self._attr_swing_mode = swing_mode
        self._device.settings["settings.echoStatus"].value = "1"
        await self._device.commands["settings"].send()
        self.schedule_update_ha_state()

    @callback
    def _handle_coordinator_update(self, update: bool = True) -> None:
        if update:
            self.schedule_update_ha_state()


class HonClimateEntity(HonEntity, ClimateEntity):
    entity_description: HonClimateEntityDescription
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device: HonAppliance,
        description: HonClimateEntityDescription,
    ) -> None:
        super().__init__(hass, entry, device, description)

        self._attr_supported_features = (
            ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TARGET_TEMPERATURE
        )

        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._set_temperature_bound()

        self._attr_hvac_modes = [description.mode]
        if "stopProgram" in device.commands:
            self._attr_supported_features |= ClimateEntityFeature.TURN_OFF
            self._attr_hvac_modes += [HVACMode.OFF]
            modes: list[str] = []
        else:
            modes = ["no_mode"]

        for mode, data in device.commands["startProgram"].categories.items():
            if mode not in data.parameters["program"].values:
                continue
            if (zone := data.parameters.get("zone")) and isinstance(
                self.entity_description.name, str
            ):
                if self.entity_description.name.lower() in zone.values:
                    modes.append(mode)
            else:
                modes.append(mode)

        if modes:
            self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE
            self._attr_preset_modes = modes

        self._handle_coordinator_update(update=False)

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self._device.get(self.entity_description.key, 0.0)

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        temp_key = self.entity_description.key.split(".")[-1].replace("Sel", "")
        return self._device.get(temp_key, 0.0)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        self._device.settings[self.entity_description.key].value = str(int(temperature))
        await self._device.commands["settings"].send()
        self.schedule_update_ha_state()

    @property
    def hvac_mode(self) -> HVACMode:
        if self._device.get("onOffStatus") == 0:
            return HVACMode.OFF
        else:
            return self.entity_description.mode

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if len(self.hvac_modes) <= 1:
            return
        if hvac_mode == HVACMode.OFF:
            await self._device.commands["stopProgram"].send()
        else:
            await self._device.commands["startProgram"].send()
        self._attr_hvac_mode = hvac_mode
        self.schedule_update_ha_state()

    async def async_turn_on(self) -> None:
        """Set the HVAC State to on."""
        await self._device.commands["startProgram"].send()

    async def async_turn_off(self) -> None:
        """Set the HVAC State to off."""
        await self._device.commands["stopProgram"].send()

    @property
    def preset_mode(self) -> str | None:
        """Return the current Preset for this channel."""
        if self._device.get("onOffStatus") is not None:
            return self._device.get("programName", "")
        else:
            return self._device.get(
                f"mode{self.entity_description.key[-2:]}", "no_mode"
            )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the new preset mode."""
        if preset_mode == "no_mode" and HVACMode.OFF in self.hvac_modes:
            command = "stopProgram"
        elif preset_mode == "no_mode":
            command = "settings"
            self._device.commands["settings"].reset()
        else:
            command = "startProgram"
        if program := self._device.settings.get(f"{command}.program"):
            program.value = preset_mode
        zone = self._device.settings.get(f"{command}.zone")
        if zone and isinstance(self.entity_description.name, str):
            zone.value = self.entity_description.name.lower()
        self._device.sync_command(command, "settings")
        self._set_temperature_bound()
        self._attr_preset_mode = preset_mode
        self.coordinator.async_set_updated_data({})
        await self._device.commands[command].send()
        self.schedule_update_ha_state()

    def _set_temperature_bound(self) -> None:
        temperature = self._device.settings[self.entity_description.key]
        if not isinstance(temperature, HonParameterRange):
            raise ValueError
        self._attr_max_temp = temperature.max
        self._attr_target_temperature_step = temperature.step
        self._attr_min_temp = temperature.min

    @callback
    def _handle_coordinator_update(self, update: bool = True) -> None:
        if update:
            self.schedule_update_ha_state()
