"""Config flow to configure SleepIQ component."""

from collections.abc import Mapping
import logging
from typing import Any, override

from asyncsleepiq.asyncsleepiq import AsyncSleepIQ
from asyncsleepiq.exceptions import SleepIQLoginException, SleepIQTimeoutException
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# A password field the frontend masks, with no default and no suggested value,
# so a rejected attempt never echoes what was typed back into the form.
PASSWORD_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
)


class SleepIQFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a SleepIQ config flow."""

    VERSION = 1

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Import a SleepIQ account as a config entry.

        This flow is triggered by 'async_setup' for configured accounts.
        """
        await self.async_set_unique_id(import_data[CONF_USERNAME].lower())
        self._abort_if_unique_id_configured()

        if error := await try_connection(self.hass, import_data):
            _LOGGER.error("Could not authenticate with SleepIQ server: %s", error)
            return self.async_abort(reason=error)

        return self.async_create_entry(
            title=import_data[CONF_USERNAME], data=import_data
        )

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Handle a bed seen on the network.

        The bed announces itself by MAC prefix but says nothing about which
        SleepIQ account owns it, and the integration talks to the cloud rather
        than to the bed, so discovery can only offer the sign-in form. One
        entry already covers every bed on an account, so a second bed on a
        configured account has nothing to add.
        """
        _LOGGER.debug(
            "SleepNumber bed discovered at %s (%s)",
            discovery_info.ip,
            discovery_info.macaddress,
        )
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        self.context["title_placeholders"] = {"name": "SleepNumber bed"}
        return await self.async_step_user()

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors = {}

        if user_input is not None:
            # Don't allow multiple instances with the same username
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()

            if error := await try_connection(self.hass, user_input):
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME], data=user_input
                )

        else:
            user_input = {}

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=user_input.get(CONF_USERNAME),
                    ): str,
                    vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
                }
            ),
            errors=errors,
            last_step=True,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the account details of an entry that already exists.

        The password may be left blank to keep the stored one, which is what
        someone correcting a typo in the username wants. Pointing the entry at
        a different account is refused: that is a second entry, with its own
        beds, devices and history.
        """
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None:
            data = {
                CONF_USERNAME: user_input[CONF_USERNAME],
                CONF_PASSWORD: user_input.get(CONF_PASSWORD)
                or reconfigure_entry.data[CONF_PASSWORD],
            }
            await self.async_set_unique_id(data[CONF_USERNAME].lower())
            self._abort_if_unique_id_mismatch(reason="wrong_account")

            if error := await try_connection(self.hass, data):
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    reconfigure_entry, data_updates=data
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=reconfigure_entry.data[CONF_USERNAME],
                    ): str,
                    vol.Optional(CONF_PASSWORD): PASSWORD_SELECTOR,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauth."""
        errors: dict[str, str] = {}

        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            data = {
                CONF_USERNAME: reauth_entry.data[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }

            if not (error := await try_connection(self.hass, data)):
                return self.async_update_reload_and_abort(reauth_entry, data=data)
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR}),
            errors=errors,
            description_placeholders={
                CONF_USERNAME: reauth_entry.data[CONF_USERNAME],
            },
        )


async def try_connection(hass: HomeAssistant, user_input: dict[str, Any]) -> str | None:
    """Test if the given credentials can successfully login to SleepIQ."""

    client_session = async_get_clientsession(hass)

    gateway = AsyncSleepIQ(client_session=client_session)
    try:
        await gateway.login(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
    except SleepIQLoginException:
        return "invalid_auth"
    except SleepIQTimeoutException:
        return "cannot_connect"

    return None
