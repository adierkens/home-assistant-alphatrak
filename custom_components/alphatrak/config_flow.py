"""Config flow for the AlphaTRAK integration."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow as HAConfigFlow
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigFlowResult
    from homeassistant.core import HomeAssistant

from .api import (
    AlphaTrakApi,
    AlphaTrakApiError,
    AlphaTrakAuthError,
    AlphaTrakConnectionError,
)
from .const import (
    CONF_PASSWORD,
    CONF_PET_ID,
    CONF_TOKEN_KEY,
    CONF_USERNAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """
    Validate the user input allows us to connect and retrieve pets.

    Returns a dict with keys: title, token, pets (list).
    """
    api = AlphaTrakApi(hass, None, None)

    try:
        resp = await api.login(data[CONF_USERNAME], data[CONF_PASSWORD])
        if not resp:
            raise InvalidAuthError

        pets = await api.get_pets()
    except AlphaTrakAuthError as err:
        raise InvalidAuthError from err
    except AlphaTrakConnectionError as err:
        raise CannotConnectError from err
    except AlphaTrakApiError as err:
        raise CannotConnectError from err

    # Return info that you want to use in the flow
    return {
        "title": f"AlphaTRAK {data[CONF_USERNAME]}",
        "token": api.token,
        "pets": pets,
    }


class CannotConnectError(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuthError(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class ConfigFlow(HAConfigFlow, domain=DOMAIN):
    """Handle a config flow for AlphaTRAK."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize temporary flow state (token and fetched pets)."""
        self._token: str | None = None
        self._pets: list[dict[str, Any]] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step for username/password input and pet selection."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self.async_set_unique_id(str(user_input.get(CONF_USERNAME)))
                self._abort_if_unique_id_configured()

                info = await validate_input(self.hass, user_input)

                # store token and pets temporarily
                self._token = info.get("token")
                self._pets = info.get("pets", [])

                # If no pets found, return an error
                if not self._pets:
                    errors["base"] = "no_pets_found"
                else:
                    # If exactly one pet, create the entry automatically
                    if len(self._pets) == 1:
                        pet = self._pets[0]
                        pid_raw = pet.get("PetId") or pet.get("Id") or pet.get("id")
                        try:
                            pid = int(str(pid_raw))
                        except (TypeError, ValueError):
                            errors["base"] = "invalid_pet_id"
                        else:
                            data = {
                                CONF_TOKEN_KEY: self._token,
                                CONF_PET_ID: pid,
                                CONF_USERNAME: user_input[CONF_USERNAME],
                            }
                            return self.async_create_entry(
                                title=f"AlphaTRAK Pet {pid}", data=data
                            )

                    # Multiple pets: create entries for each pet (delegated to helper)
                    created_entries_info = await self._create_entries_for_pets(
                        self._pets, user_input[CONF_USERNAME]
                    )
                    if created_entries_info:
                        self._created_entries = created_entries_info
                        return await self.async_step_summary()

                    errors["base"] = "no_new_pets"

            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except InvalidAuthError:
                errors["base"] = "invalid_auth"
            except (RuntimeError, ValueError, TypeError, KeyError):
                _LOGGER.exception("Unexpected exception processing user input")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_select_pet(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Present a pet selection form based on pets retrieved after login."""
        errors: dict[str, str] = {}

        if self._pets is None:
            # Missing state — ask user to re-enter credentials
            return await self.async_step_user()

        if user_input is not None:
            try:
                pet_id = int(user_input[CONF_PET_ID])
                # Attempt to resolve the pet name from temporary pet list
                data = {CONF_TOKEN_KEY: self._token, CONF_PET_ID: pet_id}
                await self.async_set_unique_id(str(pet_id))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"AlphaTRAK Pet {pet_id}", data=data
                )
            except (ValueError, TypeError):
                errors["base"] = "invalid_pet_selection"
            except (RuntimeError, KeyError):
                _LOGGER.exception("Unknown error while selecting pet")
                errors["base"] = "unknown"

        # Build selection mapping
        options = {}
        for pet in self._pets:
            pid = pet.get("PetId") or pet.get("Id") or pet.get("id")
            name = pet.get("PetName") or pet.get("Name") or f"Pet {pid}"
            if pid is not None:
                options[str(int(pid))] = name

        schema = vol.Schema({vol.Required(CONF_PET_ID): vol.In(options)})

        return self.async_show_form(
            step_id="select_pet", data_schema=schema, errors=errors
        )

    async def async_step_summary(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show a summary of entries created during this flow and finish."""
        if user_input is not None:
            # Finalize the flow by aborting with a concise reason.
            return self.async_abort(reason="created_pets")

        created_text = "\n".join(getattr(self, "_created_entries", []))
        description_placeholders = {"created_entries": created_text}

        return self.async_show_form(
            step_id="summary",
            data_schema=vol.Schema({}),
            description_placeholders=description_placeholders,
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """
        Handle a re-auth flow for an existing config entry.

        Home Assistant will call this when a ConfigEntryAuthFailed is raised
        during an update. The flow expects username & password and updates
        the entry's token on success.
        """
        errors: dict[str, str] = {}

        entry_id = self.context.get("entry_id")
        entry = self.hass.config_entries.async_get_entry(entry_id) if entry_id else None

        # Pre-fill username if available
        default_username = None
        if entry is not None:
            default_username = entry.data.get(CONF_USERNAME)

        if user_input is not None:
            api = AlphaTrakApi(self.hass, None, None)
            try:
                await api.login(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
            except AlphaTrakAuthError:
                errors["base"] = "invalid_auth"
            except AlphaTrakConnectionError:
                errors["base"] = "cannot_connect"
            except AlphaTrakApiError:
                errors["base"] = "cannot_connect"
            else:
                # Update the config entry with the new token and username
                if entry is not None:
                    new_data = {**entry.data}
                    new_data[CONF_TOKEN_KEY] = api.token
                    new_data[CONF_USERNAME] = user_input.get(CONF_USERNAME)
                    self.hass.config_entries.async_update_entry(entry, data=new_data)

                    # If this config entry is currently loaded, update its runtime
                    # coordinator so it uses the new token immediately.
                    coordinator = getattr(entry, "runtime_data", None)
                    if coordinator is not None:
                        # Use public setter to avoid touching private members
                        try:
                            coordinator.api.set_token(api.token)
                        except AttributeError:
                            _LOGGER.debug("Coordinator API has no set_token method")
                        # Refresh the coordinator; only handle known failures
                        try:
                            await coordinator.async_request_refresh()
                        except UpdateFailed:
                            _LOGGER.debug("Coordinator refresh failed after reauth")
                        except asyncio.CancelledError:
                            raise

                return self.async_abort(reason="reauth_successful")

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=default_username): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="reauth",
            data_schema=schema,
            errors=errors,
        )

    async def _create_entries_for_pets(
        self, pets: list[dict[str, Any]], username: str
    ) -> list[str]:
        """
        Create config entries for a list of pet dicts.

        Returns created info strings for the summary UI.
        """
        created_entries_info: list[str] = []
        configured_ids = set()
        for e in self.hass.config_entries.async_entries(DOMAIN):
            v = e.data.get(CONF_PET_ID)
            if v is None:
                continue
            try:
                configured_ids.add(int(v))
            except (TypeError, ValueError):
                continue

        for pet in pets:
            pid_raw = pet.get("PetId") or pet.get("Id") or pet.get("id")
            if pid_raw is None:
                continue
            try:
                pid = int(str(pid_raw))
            except (TypeError, ValueError):
                continue

            if pid in configured_ids:
                continue

            await self.async_set_unique_id(str(pid))
            self._abort_if_unique_id_configured()

            data = {
                CONF_TOKEN_KEY: self._token,
                CONF_PET_ID: pid,
                CONF_USERNAME: username,
            }
            self.async_create_entry(title=f"AlphaTRAK Pet {pid}", data=data)
            pet_name = pet.get("PetName") or "Unnamed"
            created_entries_info.append(f"Pet {pid}: {pet_name}")

        return created_entries_info
