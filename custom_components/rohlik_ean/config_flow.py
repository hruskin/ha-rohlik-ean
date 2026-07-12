"""Config flow for Rohlík EAN."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_CONFIDENCE_THRESHOLD,
    CONF_SCAN_AGGREGATION,
    DEFAULT_SCAN_AGGREGATION,
    CONF_GITHUB_AUTO_BACKUP,
    CONF_GITHUB_PATH,
    CONF_GITHUB_REPO,
    CONF_GITHUB_TOKEN,
    CONF_NOTIFY_UNRESOLVED,
    CONF_TRUST_EAN_HIT,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_GITHUB_AUTO_BACKUP,
    DEFAULT_GITHUB_PATH,
    DEFAULT_NOTIFY_UNRESOLVED,
    DEFAULT_TRUST_EAN_HIT,
    DOMAIN,
    ROHLIKCZ_DOMAIN,
)


class RohlikEanConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance flow; all state lives in options."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if not self.hass.config_entries.async_entries(ROHLIKCZ_DOMAIN):
            return self.async_abort(reason="rohlikcz_missing")

        if user_input is not None:
            return self.async_create_entry(title="Rohlík EAN", data={})

        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return RohlikEanOptionsFlow()


class RohlikEanOptionsFlow(OptionsFlow):
    """Tune matching confidence and notification behaviour."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_CONFIDENCE_THRESHOLD,
                    default=options.get(
                        CONF_CONFIDENCE_THRESHOLD, DEFAULT_CONFIDENCE_THRESHOLD
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=1.0)),
                vol.Optional(
                    CONF_TRUST_EAN_HIT,
                    default=options.get(CONF_TRUST_EAN_HIT, DEFAULT_TRUST_EAN_HIT),
                ): bool,
                vol.Optional(
                    CONF_NOTIFY_UNRESOLVED,
                    default=options.get(
                        CONF_NOTIFY_UNRESOLVED, DEFAULT_NOTIFY_UNRESOLVED
                    ),
                ): bool,
                vol.Optional(
                    CONF_SCAN_AGGREGATION,
                    default=options.get(
                        CONF_SCAN_AGGREGATION, DEFAULT_SCAN_AGGREGATION
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=30)),
                vol.Optional(
                    CONF_GITHUB_REPO,
                    description={
                        "suggested_value": options.get(CONF_GITHUB_REPO, "")
                    },
                ): str,
                vol.Optional(
                    CONF_GITHUB_TOKEN,
                    description={
                        "suggested_value": options.get(CONF_GITHUB_TOKEN, "")
                    },
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
                vol.Optional(
                    CONF_GITHUB_PATH,
                    default=options.get(CONF_GITHUB_PATH, DEFAULT_GITHUB_PATH),
                ): str,
                vol.Optional(
                    CONF_GITHUB_AUTO_BACKUP,
                    default=options.get(
                        CONF_GITHUB_AUTO_BACKUP, DEFAULT_GITHUB_AUTO_BACKUP
                    ),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
