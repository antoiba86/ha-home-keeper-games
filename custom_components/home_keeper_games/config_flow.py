"""The config flow and the options flow of Home Keeper Games.

The integration has 1 config entry. The flow first checks Home Keeper. If Home
Keeper is not installed, not set up or too old, the flow stops with the reason
and a link. The settings are the currency of the prices and values of the copies,
with the currency of Home Assistant as default, and the optional IGDB keys.
The options flow has 1 step with the same fields. It merges its input into the
stored options, so a key that the form does not show stays.

The IGDB keys are a Twitch client ID and client secret. The flow gets a token with
them before it saves them, in the entry data. The secret field never shows the
stored secret: an empty secret with the same client ID keeps it, and an empty
client ID removes both keys.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_CURRENCY,
    CONF_IGDB_CLIENT_ID,
    CONF_IGDB_CLIENT_SECRET,
    DEFAULT_CURRENCY,
    DOMAIN,
    NAME,
)
from .home_keeper import async_check, placeholders
from .igdb import IgdbClient, igdb_urls
from .models import LibraryError

_IGDB_KEYS = (CONF_IGDB_CLIENT_ID, CONF_IGDB_CLIENT_SECRET)
_FLOW_ERRORS = {"invalid_igdb_auth": "invalid_igdb_auth"}


def _schema(currency: str, client_id: str) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_CURRENCY, default=currency): str,
            vol.Optional(
                CONF_IGDB_CLIENT_ID, description={"suggested_value": client_id}
            ): str,
            vol.Optional(CONF_IGDB_CLIENT_SECRET): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
        }
    )


async def async_igdb_data(
    hass: HomeAssistant, user_input: dict[str, Any], stored: Mapping[str, Any]
) -> tuple[dict[str, str], str | None]:
    """The IGDB keys to store from the form, and an error key or None.

    ``{}`` stores no keys. Keys that are new get a token first, so a wrong key
    never gets into the entry.
    """
    client_id = str(user_input.get(CONF_IGDB_CLIENT_ID) or "").strip()
    secret = str(user_input.get(CONF_IGDB_CLIENT_SECRET) or "").strip()
    if not client_id:
        return {}, ("igdb_keys_incomplete" if secret else None)
    if not secret:
        if stored.get(CONF_IGDB_CLIENT_ID) == client_id and stored.get(
            CONF_IGDB_CLIENT_SECRET
        ):
            return {key: stored[key] for key in _IGDB_KEYS}, None
        return {}, "igdb_keys_incomplete"
    client = IgdbClient(hass, lambda: None, **igdb_urls(os.environ))
    try:
        await client.async_check_keys(client_id, secret)
    except LibraryError as err:
        return {}, _FLOW_ERRORS.get(err.key, "cannot_connect")
    return {CONF_IGDB_CLIENT_ID: client_id, CONF_IGDB_CLIENT_SECRET: secret}, None


def clean_currency(value: Any) -> str | None:
    """An upper-case code of 3 letters, or None."""
    text = str(value or "").strip().upper()
    return text if len(text) == 3 and text.isalpha() else None


def merge_flow_input(entry: ConfigEntry, user_input: dict[str, Any]) -> dict[str, Any]:
    """The stored options with the form input on top."""
    return {**entry.options, **user_input}


class LibraryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add the 1 config entry of the library."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the currency."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if (reason := await async_check(self.hass)) is not None:
            return self.async_abort(
                reason=reason, description_placeholders=placeholders(reason)
            )
        default = self.hass.config.currency or DEFAULT_CURRENCY
        errors: dict[str, str] = {}
        client_id = ""
        if user_input is not None:
            client_id = str(user_input.get(CONF_IGDB_CLIENT_ID) or "")
            currency = clean_currency(user_input.get(CONF_CURRENCY))
            if currency is None:
                errors[CONF_CURRENCY] = "invalid_currency"
            else:
                keys, error = await async_igdb_data(self.hass, user_input, {})
                if error is None:
                    return self.async_create_entry(
                        title=NAME, data=keys, options={CONF_CURRENCY: currency}
                    )
                errors["base"] = error
            default = str(user_input.get(CONF_CURRENCY) or default)
        return self.async_show_form(
            step_id="user", data_schema=_schema(default, client_id), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return LibraryOptionsFlow()


class LibraryOptionsFlow(OptionsFlow):
    """Change the currency and the IGDB keys."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options form."""
        entry = self.config_entry
        errors: dict[str, str] = {}
        current = entry.options.get(CONF_CURRENCY) or (
            self.hass.config.currency or DEFAULT_CURRENCY
        )
        client_id = str(entry.data.get(CONF_IGDB_CLIENT_ID) or "")
        if user_input is not None:
            client_id = str(user_input.get(CONF_IGDB_CLIENT_ID) or "")
            currency = clean_currency(user_input.get(CONF_CURRENCY))
            if currency is None:
                errors[CONF_CURRENCY] = "invalid_currency"
            else:
                keys, error = await async_igdb_data(self.hass, user_input, entry.data)
                if error is None:
                    data = {k: v for k, v in entry.data.items() if k not in _IGDB_KEYS}
                    if {**data, **keys} != dict(entry.data):
                        self.hass.config_entries.async_update_entry(
                            entry, data={**data, **keys}
                        )
                    return self.async_create_entry(
                        data=merge_flow_input(entry, {CONF_CURRENCY: currency})
                    )
                errors["base"] = error
            current = str(user_input.get(CONF_CURRENCY) or current)
        return self.async_show_form(
            step_id="init", data_schema=_schema(current, client_id), errors=errors
        )
