"""Config flow for Tesla Solar (Fleet)."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import config_entry_oauth2_flow

from .const import (
    CONF_MONTHLY_BUDGET,
    CONF_STALE_AFTER_HOURS,
    DEFAULT_MONTHLY_BUDGET,
    DEFAULT_STALE_AFTER_HOURS,
    DOMAIN,
    MAX_MONTHLY_BUDGET,
    MAX_STALE_AFTER_HOURS,
    MIN_MONTHLY_BUDGET,
    MIN_STALE_AFTER_HOURS,
    SCOPE,
)
from .coordinator import compute_schedule

_LOGGER = logging.getLogger(__name__)


class TeslaSolarOAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Handle the OAuth2 config flow for Tesla Solar."""

    DOMAIN = DOMAIN

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return _LOGGER

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Extra data appended to the authorize URL."""
        return {"scope": SCOPE}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return TeslaSolarOptionsFlow()

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm re-authentication."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_user()

    async def async_oauth_create_entry(
        self, data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Create or update the config entry after a successful OAuth login."""
        existing = await self.async_set_unique_id(DOMAIN)
        if self.source == "reauth" and existing:
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data=data
            )
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="Tesla Solar", data=data)


class TeslaSolarOptionsFlow(OptionsFlow):
    """Let the user set a monthly Fleet API call budget."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the monthly call budget."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_MONTHLY_BUDGET, DEFAULT_MONTHLY_BUDGET
        )
        stale_after = self.config_entry.options.get(
            CONF_STALE_AFTER_HOURS, DEFAULT_STALE_AFTER_HOURS
        )
        fast_interval, slow_every, est_calls = compute_schedule(current)
        placeholders = {
            "current": str(current),
            "today_minutes": str(round(fast_interval / 60, 1)),
            "year_hours": str(round(fast_interval * slow_every / 3600, 1)),
            "est_calls": str(int(round(est_calls))),
        }

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MONTHLY_BUDGET, default=current
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_MONTHLY_BUDGET, max=MAX_MONTHLY_BUDGET),
                ),
                vol.Required(
                    CONF_STALE_AFTER_HOURS, default=stale_after
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_STALE_AFTER_HOURS, max=MAX_STALE_AFTER_HOURS
                    ),
                ),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders=placeholders,
        )
