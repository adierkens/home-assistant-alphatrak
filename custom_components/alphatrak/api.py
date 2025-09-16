"""AlphaTRAK API client."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from base64 import b64encode
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import aiohttp
from Crypto.Cipher import AES

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    API_BASE_URL,
    API_ENDPOINT,
    API_LOGIN_ENDPOINT,
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

    def __init__(
        self, hass: HomeAssistant, token: str | None = None, pet_id: int | None = None
    ) -> None:
        """Initialize the API client."""
        self._hass = hass
        self._token = token
        self._pet_id = pet_id
        self._user_id: int | None = None
        self._session = async_get_clientsession(hass)
        self._base_url = API_BASE_URL

    @property
    def pet_id(self) -> int | None:
        """Return the pet ID when set, otherwise None."""
        return self._pet_id

    @property
    def token(self) -> str | None:
        """Return the current auth token, if any."""
        return self._token

    def set_token(self, token: str | None) -> None:
        """Set the auth token to use for subsequent requests."""
        self._token = token

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
            "ToDate": to_date.strftime("%Y-%m-%dT%H:%M:%S"),
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

                # Attempt to parse JSON body. Some API responses use non-200
                # status codes (e.g. 404) but still return a ResponseData
                # payload we can use (empty PetActivity lists). Be lenient
                # and accept ResponseData if present.
                try:
                    response_data = await response.json()
                except json.JSONDecodeError:
                    # If we couldn't parse JSON and status not OK, log and raise
                    if response.status != HTTPStatus.OK:
                        try:
                            text = await response.text()
                        except (aiohttp.ClientError, UnicodeDecodeError, ValueError):
                            text = "<unable to read response body>"
                        _LOGGER.debug(
                            "API call to %s failed (status=%s). Payload keys=%s; "
                            "response=%s",
                            url,
                            response.status,
                            list(payload.keys()),
                            text,
                        )
                        msg = f"API request failed with status {response.status}"
                        raise AlphaTrakApiError(msg) from None
                    # Otherwise, unexpected lack of JSON on OK response
                    msg = "Invalid JSON response"
                    raise AlphaTrakApiError(msg) from None

                # If non-OK status but ResponseData present, return it (some
                # endpoints return 404 with ResponseData containing empty lists)
                if response.status != HTTPStatus.OK:
                    if response_data.get(RESPONSE_DATA) is not None:
                        _LOGGER.debug(
                            "Non-OK status %s but returning ResponseData from %s",
                            response.status,
                            url,
                        )
                        return response_data.get(RESPONSE_DATA)
                    # No usable payload; log and raise
                    try:
                        text = await response.text()
                    except (aiohttp.ClientError, UnicodeDecodeError, ValueError):
                        text = "<unable to read response body>"
                    _LOGGER.debug(
                        "API call to %s failed (status=%s). Payload keys=%s; "
                        "response=%s",
                        url,
                        response.status,
                        list(payload.keys()),
                        text,
                    )
                    msg = f"API request failed with status {response.status}"
                    raise AlphaTrakApiError(msg) from None

                # OK response: accept ResponseData even if IsSuccess flag is False
                if not response_data.get(RESPONSE_SUCCESS, False):
                    if response_data.get(RESPONSE_DATA) is not None:
                        _LOGGER.debug(
                            "API returned unsuccessful flag but ResponseData present; "
                            "returning it from %s",
                            url,
                        )
                        return response_data.get(RESPONSE_DATA)
                    msg = "API returned unsuccessful response"
                    raise AlphaTrakApiError(msg) from None

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

    def _aes_encrypt_password(self, plain_password: str) -> str:
        """
        Encrypt plain password using AES-256-ECB and return base64 string.

        Mirrors the JavaScript AESEncryptor example provided by the API client.
        """
        key_str = "b14ca5898a4e4133bbce2ea2315a1916"
        key = key_str.encode("utf-8")

        # PKCS7 padding
        bs = AES.block_size
        data = plain_password.encode("utf-8")
        pad_len = bs - (len(data) % bs)
        data += bytes([pad_len]) * pad_len

        cipher = AES.new(key, AES.MODE_ECB)
        encrypted = cipher.encrypt(data)
        return b64encode(encrypted).decode("utf-8")

    async def login(self, email: str, plain_password: str) -> dict[str, Any] | None:
        """
        Authenticate with the API and store the access token and user id.

        Returns the parsed response data on success.
        """
        url = f"{self._base_url}/{API_LOGIN_ENDPOINT}"

        password_b64 = self._aes_encrypt_password(plain_password)
        s_key = b64encode(os.urandom(16)).decode("utf-8")

        payload = {
            "UserId": str(email),
            "Password": password_b64,
            "SKey": s_key,
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Authorization": "",  # No token yet
        }

        try:
            async with asyncio.timeout(API_TIMEOUT):
                async with self._session.post(
                    url, headers=headers, data=json.dumps(payload), ssl=False
                ) as response:
                    if response.status == HTTPStatus.UNAUTHORIZED:
                        msg = "Authentication failed"
                        raise AlphaTrakAuthError(msg)
                    if response.status != HTTPStatus.OK:
                        msg = f"Login request failed: {response.status}"
                        raise AlphaTrakApiError(msg)

                    response_data = await response.json()

                    if not response_data.get(RESPONSE_SUCCESS, False):
                        msg = "Login request unsuccessful"
                        raise AlphaTrakApiError(msg)

                    resp = response_data.get(RESPONSE_DATA) or {}
                    auth = resp.get("AuthToken") or {}
                    token = auth.get("access_token")
                    if token:
                        self._token = token
                        # store the numeric user id if provided
                        uid_val = resp.get("Id")
                        if uid_val is not None:
                            try:
                                self._user_id = int(uid_val)
                            except (ValueError, TypeError):
                                self._user_id = None
                        else:
                            self._user_id = None
                    return resp

        except TimeoutError as err:
            msg = "Login request timed out"
            raise AlphaTrakConnectionError(msg) from err
        except aiohttp.ClientError as err:
            msg = f"Connection error: {err}"
            raise AlphaTrakConnectionError(msg) from err
        except json.JSONDecodeError as err:
            msg = f"Invalid JSON login response: {err}"
            raise AlphaTrakApiError(msg) from err

    async def get_pets(self) -> list[dict[str, Any]]:
        """
        Fetch pets for the authenticated user using the documented endpoint.

        Calls GetPetDetailsListByUserId with query params: userId, count, languageId.
        Returns a list of pet dicts (may be empty).
        """
        if not self._token:
            msg = "Missing auth token; please login first"
            raise AlphaTrakAuthError(msg)

        if not self._user_id:
            msg = "Missing user id; login did not return user id"
            raise AlphaTrakApiError(msg)

        endpoint = "GetPetDetailsListByUserId"
        url = f"{self._base_url}/{endpoint}"

        params = {
            "userId": int(self._user_id),
            "count": 100,
            "languageId": int(DEFAULT_LANGUAGE_ID),
        }

        headers = {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Authorization": f"bearer {self._token}",
        }

        try:
            async with asyncio.timeout(API_TIMEOUT):
                async with self._session.get(
                    url, params=params, headers=headers, ssl=False
                ) as response:
                    if response.status != HTTPStatus.OK:
                        msg = f"Pet list request failed: {response.status}"
                        raise AlphaTrakApiError(msg)
                    response_data = await response.json()
        except TimeoutError as err:
            msg = "Pet list request timed out"
            raise AlphaTrakConnectionError(msg) from err
        except aiohttp.ClientError as err:
            msg = f"Connection error: {err}"
            raise AlphaTrakConnectionError(msg) from err
        except json.JSONDecodeError as err:
            msg = f"Invalid JSON pet list response: {err}"
            raise AlphaTrakApiError(msg) from err
        else:
            if not response_data.get(RESPONSE_SUCCESS, False):
                msg = "Pet list request unsuccessful"
                raise AlphaTrakApiError(msg)

            pets = response_data.get(RESPONSE_DATA) or []
            if isinstance(pets, list):
                return pets

            # Unexpected shape; return empty list
            return []
