from datetime import datetime, timedelta, timezone

import pytest

from core.oauth import OAuthToken, OAuthTokenLifecycle
from core.redaction import redact_payload


def test_redaction_handles_sensitive_keys_and_embedded_pii():
    result = redact_payload({"patient_email": "person@example.com", "note": "SSN 123-45-6789", "nested": {"token": "do-not-store"}})

    assert result["patient_email"] == "***REDACTED***"
    assert result["note"] == "SSN ***REDACTED:SSN***"
    assert result["nested"]["token"] == "***REDACTED***"


@pytest.mark.asyncio
async def test_token_lifecycle_refreshes_expiring_token():
    class Provider:
        def __init__(self):
            self.calls = 0

        async def request_token(self):
            self.calls += 1
            return OAuthToken(f"token-{self.calls}", "Bearer", datetime.now(timezone.utc) + timedelta(minutes=5))

    provider = Provider()
    lifecycle = OAuthTokenLifecycle(provider)

    first = await lifecycle.get_token()
    second = await lifecycle.get_token()

    assert first.access_token == second.access_token
    assert provider.calls == 1
