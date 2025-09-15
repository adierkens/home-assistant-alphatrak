"""AlphaTRAK API client."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import aiohttp

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    API_BASE_URL,
    API_ENDPOINT,
    API_TIMEOUT,
    DEFAULT_LANGUAGE_ID,
    RESPONSE_BLOOD_GLUCOSE,
    RESPONSE_DATA,
    RESPONSE_MAX_RANGE,
    RESPONSE_MIN_RANGE,
    RESPONSE_PET_ACTIVITY,
    RESPONSE_SUCCESS,
)

_LOGGER = logging.getLogger(__name__)


class AlphaTrakApiError(Exception):
    """Exception for AlphaTRAK API errors."""


class AlphaTrakAuthError(AlphaTrakApiError):
    """Exception for authentication errors."""


class AlphaTrakConnectionError(AlphaTrakApiError):
    """Exception for connection errors."""


class AlphaTrakApi:
    """AlphaTRAK API client."""

    def __init__(self, hass: HomeAssistant, token: str, pet_id: int) -> None:
        """Initialize the API client."""
        self._hass = hass
        self._token = token
        self._pet_id = pet_id
        self._session = async_get_clientsession(hass)
        self._base_url = API_BASE_URL

    @property
    def pet_id(self) -> int:
        """Return the pet ID."""
        return self._pet_id

    async def validate_connection(self) -> bool:
        """Validate the API connection and authentication."""
        try:
            # Test with a small date range to validate credentials
            end_date = datetime.now(UTC)
            start_date = end_date - timedelta(days=1)
            data = await self.get_pet_activity(start_date, end_date)
        except AlphaTrakAuthError:
            return False
        except (AlphaTrakApiError, AlphaTrakConnectionError) as err:
            _LOGGER.debug("Connection validation failed: %s", err)
            return False
        else:
            return data is not None

    async def get_pet_activity(
        self,
        from_date: datetime,
        to_date: datetime,
        language_id: str = DEFAULT_LANGUAGE_ID,
    ) -> dict[str, Any] | None:
        """Get pet activity data from the API."""
        url = f"{self._base_url}/{API_ENDPOINT}"

        headers = {
            "Accept": "*/*",
            "User-Agent": (
                "AlphaTRAK/1.40.3 (com.zoetis.alphatrak; build:39; "
                "iOS 18.6.2) Alamofire/4.9.1"
            ),
            "Host": "alphatrakapi.zoetis.com",
            "Connection": "keep-alive",
            "Accept-Language": "en-US;q=1.0",
            "Content-Type": "application/json",
            "Authorization": f"bearer {self._token}",
        }

        payload = {
            "PetId": self._pet_id,
            "FromDate": from_date.strftime("%Y-%m-%dT%H:%M:%S"),
            "Todate": to_date.strftime("%Y-%m-%dT%H:%M:%S"),
            "LanguageId": language_id,
        }

        try:
            async with (
                asyncio.timeout(API_TIMEOUT),
                self._session.post(
                    url,
                    headers=headers,
                    data=json.dumps(payload),
                    ssl=False,  # Based on the curl -k flag
                ) as response,
            ):
                if response.status == HTTPStatus.UNAUTHORIZED:
                    msg = "Authentication failed"
                    raise AlphaTrakAuthError(msg)
                if response.status != HTTPStatus.OK:
                    msg = f"API request failed with status {response.status}"
                    raise AlphaTrakApiError(msg)

                response_data = await response.json()

                if not response_data.get(RESPONSE_SUCCESS, False):
                    msg = "API returned unsuccessful response"
                    raise AlphaTrakApiError(msg)

                return response_data.get(RESPONSE_DATA)

        except TimeoutError as err:
            msg = "Request timed out"
            raise AlphaTrakConnectionError(msg) from err
        except aiohttp.ClientError as err:
            msg = f"Connection error: {err}"
            raise AlphaTrakConnectionError(msg) from err
        except json.JSONDecodeError as err:
            msg = f"Invalid JSON response: {err}"
            raise AlphaTrakApiError(msg) from err

    async def get_latest_glucose_reading(self) -> dict[str, Any] | None:
        """Get the most recent glucose reading."""
        # Get data from the last week to ensure we catch recent readings
        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=7)

        activity_data = await self.get_pet_activity(start_date, end_date)
        if not activity_data:
            return None

        pet_activity = activity_data.get(RESPONSE_PET_ACTIVITY, {})
        blood_glucose_readings = pet_activity.get(RESPONSE_BLOOD_GLUCOSE, [])

        if not blood_glucose_readings:
            return None

        # Sort by datetime to get the most recent reading
        sorted_readings = sorted(
            blood_glucose_readings,
            key=lambda x: x.get("GlucoseEntryDateTime", ""),
            reverse=True,
        )

        latest_reading = sorted_readings[0]

        # Add range information
        latest_reading[RESPONSE_MIN_RANGE] = activity_data.get(RESPONSE_MIN_RANGE)
        latest_reading[RESPONSE_MAX_RANGE] = activity_data.get(RESPONSE_MAX_RANGE)

        return latest_reading

    async def get_glucose_readings(self, days: int = 7) -> list[dict[str, Any]]:
        """Get glucose readings from the last N days."""
        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=days)

        activity_data = await self.get_pet_activity(start_date, end_date)
        if not activity_data:
            return []

        pet_activity = activity_data.get(RESPONSE_PET_ACTIVITY, {})
        blood_glucose_readings = pet_activity.get(RESPONSE_BLOOD_GLUCOSE, [])

        # Add range information to each reading
        min_range = activity_data.get(RESPONSE_MIN_RANGE)
        max_range = activity_data.get(RESPONSE_MAX_RANGE)

        for reading in blood_glucose_readings:
            reading[RESPONSE_MIN_RANGE] = min_range
            reading[RESPONSE_MAX_RANGE] = max_range

        return blood_glucose_readings

    def _extract_entry_datetime(self, entry: dict[str, Any]) -> str:
        """Return an ISO datetime string from an activity entry."""
        for key in entry:
            if key.endswith("EntryDateTime"):
                val = entry.get(key)
                if isinstance(val, str):
                    return val
        # Some entries may use slightly different casing or names; try common
        # alternatives
        for candidate in ("EntryDateTime", "EntryDate"):
            for key in entry:
                val = entry.get(key)
                if candidate in key and isinstance(val, str):
                    return val
        return ""

    async def get_recent_activities(
        self, days: int = 7
    ) -> dict[str, list[dict[str, Any]]]:
        """Return the raw lists of activities for the last N days."""
        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=days)

        activity_data = await self.get_pet_activity(start_date, end_date)
        if not activity_data:
            return {}

        pet_activity = activity_data.get(RESPONSE_PET_ACTIVITY, {})

        # Add range information to each glucose reading if present
        min_range = activity_data.get(RESPONSE_MIN_RANGE)
        max_range = activity_data.get(RESPONSE_MAX_RANGE)
        blood_glucose_readings = pet_activity.get(RESPONSE_BLOOD_GLUCOSE, [])
        for reading in blood_glucose_readings:
            reading[RESPONSE_MIN_RANGE] = min_range
            reading[RESPONSE_MAX_RANGE] = max_range

        return pet_activity

    async def get_latest_activities(
        self,
    ) -> dict[str, dict[str, Any] | None]:
        """Return the most recent entry for each activity type (or None if absent)."""
        # Look back a reasonable window to ensure we catch recent events
        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=7)

        activity_data = await self.get_pet_activity(start_date, end_date)
        if not activity_data:
            return {}

        pet_activity = activity_data.get(RESPONSE_PET_ACTIVITY, {})

        latest: dict[str, dict[str, Any] | None] = {}

        for activity_type, entries in pet_activity.items():
            if not entries:
                latest[activity_type] = None
                continue

            sorted_entries = sorted(
                entries,
                key=lambda x: self._extract_entry_datetime(x) or "",
                reverse=True,
            )
            # Attach range info for blood glucose
            if activity_type == RESPONSE_BLOOD_GLUCOSE:
                min_range = activity_data.get(RESPONSE_MIN_RANGE)
                max_range = activity_data.get(RESPONSE_MAX_RANGE)
                for r in sorted_entries:
                    r[RESPONSE_MIN_RANGE] = min_range
                    r[RESPONSE_MAX_RANGE] = max_range

            latest[activity_type] = sorted_entries[0]

        return latest
