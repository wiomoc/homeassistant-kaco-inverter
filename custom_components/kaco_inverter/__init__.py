"""Integration for KACO inverters connected via RS485."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import KacoConfigEntry, KacoInverterCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: KacoConfigEntry) -> bool:
    """Set up inverter from a config entry."""

    coordinator = KacoInverterCoordinator(hass, entry)
    entry.runtime_data = coordinator
    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: KacoConfigEntry) -> bool:
    """Unload a config entry."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
