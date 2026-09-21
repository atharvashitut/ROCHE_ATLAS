"""OAuth client-credentials token lifecycle helpers for live adapter migration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol


@dataclass(frozen=True)
class OAuthToken:
    access_token: str
    token_type: str
    expires_at: datetime
    scope: str = ""

    def authorization_header(self) -> dict[str, str]:
        return {"Authorization": f"{self.token_type} {self.access_token}"}

    def is_expiring(self, leeway_seconds: int = 60, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        return self.expires_at <= current + timedelta(seconds=leeway_seconds)


class OAuthTokenProvider(Protocol):
    async def request_token(self) -> OAuthToken: ...


class OAuthTokenLifecycle:
    """Caches a token and refreshes it before expiry without exposing its value."""

    def __init__(self, provider: OAuthTokenProvider, refresh_leeway_seconds: int = 60):
        self.provider = provider
        self.refresh_leeway_seconds = refresh_leeway_seconds
        self._token: OAuthToken | None = None

    async def get_token(self) -> OAuthToken:
        if self._token is None or self._token.is_expiring(self.refresh_leeway_seconds):
            self._token = await self.provider.request_token()
        return self._token


def client_credentials_form(client_id: str, client_secret: str, scope: str = "") -> dict[str, str]:
    form = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
    if scope:
        form["scope"] = scope
    return form
