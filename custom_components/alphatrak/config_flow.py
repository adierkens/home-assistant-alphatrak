"""Config flow for the AlphaTRAK integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow as HAConfigFlow
from homeassistant.exceptions import HomeAssistantError

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigFlowResult
    from homeassistant.core import HomeAssistant

from .api import (
    AlphaTrakApi,
    AlphaTrakApiError,
    AlphaTrakAuthError,
    AlphaTrakConnectionError,
)
from .const import CONF_PET_ID, CONF_TOKEN_KEY, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TOKEN_KEY): str,
        vol.Required(CONF_PET_ID): int,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """
    Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    api = AlphaTrakApi(hass, data[CONF_TOKEN_KEY], data[CONF_PET_ID])

    try:
        if not await api.validate_connection():
            raise InvalidAuthError
    except AlphaTrakAuthError as err:
        raise InvalidAuthError from err
    except (AlphaTrakApiError, AlphaTrakConnectionError) as err:
        raise CannotConnectError from err

    # Return info that you want to store in the config entry.
    return {"title": f"AlphaTRAK Pet {data[CONF_PET_ID]}"}


class ConfigFlow(HAConfigFlow, domain=DOMAIN):
    """Handle a config flow for AlphaTRAK."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                # Check if this pet ID is already configured
                await self.async_set_unique_id(str(user_input[CONF_PET_ID]))
                self._abort_if_unique_id_configured()

                info = await validate_input(self.hass, user_input)
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except InvalidAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnectError(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuthError(HomeAssistantError):
    """Error to indicate there is invalid auth."""
