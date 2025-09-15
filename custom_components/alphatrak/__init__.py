"""The AlphaTRAK integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from .api import (
    AlphaTrakApi,
    AlphaTrakApiError,
    AlphaTrakAuthError,
    AlphaTrakConnectionError,
)
from .const import CONF_PET_ID, CONF_TOKEN_KEY
from .coordinator import AlphaTrakCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

type AlphaTrakConfigEntry = ConfigEntry[AlphaTrakCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: AlphaTrakConfigEntry) -> bool:
    """Set up AlphaTRAK from a config entry."""
    api = AlphaTrakApi(hass, entry.data[CONF_TOKEN_KEY], entry.data[CONF_PET_ID])

    try:
        # Validate the API connection
        if not await api.validate_connection():
            msg = "Unable to connect to AlphaTRAK API"
            raise ConfigEntryNotReady(msg)
    except AlphaTrakAuthError as err:
        msg = f"Authentication failed: {err}"
        raise ConfigEntryNotReady(msg) from err
    except (AlphaTrakApiError, AlphaTrakConnectionError) as err:
        msg = f"API error: {err}"
        raise ConfigEntryNotReady(msg) from err

    # Create the coordinator
    coordinator = AlphaTrakCoordinator(hass, api, entry)

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Store the coordinator in runtime data
    entry.runtime_data = coordinator

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: AlphaTrakConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
