"""AlphaTRAK data update coordinator."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

from .api import (
    AlphaTrakApi,
    AlphaTrakApiError,
    AlphaTrakAuthError,
    AlphaTrakConnectionError,
)
from .const import DEFAULT_SCAN_INTERVAL_MINUTES, DOMAIN

_LOGGER = logging.getLogger(__name__)


class AlphaTrakCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """AlphaTRAK data update coordinator."""

    def __init__(
        self, hass: HomeAssistant, api: AlphaTrakApi, config_entry: ConfigEntry
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES),
            config_entry=config_entry,
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via API."""
        try:
            # Get the latest glucose reading
            latest_reading = await self.api.get_latest_glucose_reading()
            if latest_reading is None:
                msg = "No glucose readings found"
                raise UpdateFailed(msg)

            # Get readings from the last 7 days for trend analysis
            readings = await self.api.get_glucose_readings(days=7)
        except AlphaTrakAuthError as err:
            msg = "Authentication failed"
            raise ConfigEntryAuthFailed(msg) from err
        except AlphaTrakConnectionError as err:
            msg = f"Connection error: {err}"
            raise UpdateFailed(msg) from err
        except AlphaTrakApiError as err:
            msg = f"API error: {err}"
            raise UpdateFailed(msg) from err
        else:
            return {
                "latest_reading": latest_reading,
                "recent_readings": readings,
                "pet_id": self.api.pet_id,
            }
