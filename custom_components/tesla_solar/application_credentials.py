"""Application credentials / OAuth2 implementation for Tesla Solar (Fleet).

Tesla's token endpoint requires an ``audience`` parameter (the regional Fleet
API host) on both the authorization-code exchange and every refresh. Home
Assistant's stock OAuth2 implementation does not send it, so we subclass and
inject it here. This also means token refresh is handled entirely by Home
Assistant going forward — no external scripts and no dependency on the official
Tesla Fleet integration.
"""
from __future__ import annotations

from homeassistant.components.application_credentials import (
    AuthImplementation,
    AuthorizationServer,
    ClientCredential,
)
from homeassistant.core import HomeAssistant

from .const import AUDIENCE, OAUTH2_AUTHORIZE, OAUTH2_TOKEN, SCOPE


class TeslaSolarOAuth2Implementation(AuthImplementation):
    """OAuth2 implementation that adds Tesla's required scope + audience."""

    @property
    def extra_authorize_data(self) -> dict:
        """Extra data appended to the authorize URL."""
        return {"scope": SCOPE}

    async def _token_request(self, data: dict) -> dict:
        """Add the audience to every token request (code exchange and refresh)."""
        data["audience"] = AUDIENCE
        return await super()._token_request(data)


async def async_get_auth_implementation(
    hass: HomeAssistant, auth_domain: str, credential: ClientCredential
) -> AuthImplementation:
    """Return a custom auth implementation for the given credential."""
    return TeslaSolarOAuth2Implementation(
        hass,
        auth_domain,
        credential,
        AuthorizationServer(
            authorize_url=OAUTH2_AUTHORIZE,
            token_url=OAUTH2_TOKEN,
        ),
    )


async def async_get_description_placeholders(hass: HomeAssistant) -> dict[str, str]:
    """Return description placeholders for the credentials dialog."""
    return {
        "developer_dashboard_url": "https://developer.tesla.com/",
        "more_info_url": "https://github.com/joegarcia/tesla_solar",
    }
