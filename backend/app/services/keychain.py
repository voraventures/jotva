"""All user-supplied secrets live in the OS keychain via keyring (C10)."""
import logging
import os

log = logging.getLogger("jotva.keychain")

SERVICE = "Jotva"

KNOWN_SECRETS = [
    "anthropic_api_key",
    "openai_api_key",
    "google_api_key",
    "license_key",
    # Internal: short-lived proof-of-ownership for the billing portal, minted by
    # the license server and cached here (not a user-entered integration secret).
    "portal_token",
    "hubspot_token",
    "salesforce_token",
    "salesforce_instance_url",
    "jira_token",
    "jira_email",
    "jira_base_url",
    "linear_api_key",
    "slack_webhook_url",
    "notion_token",
    "notion_database_id",
    "zapier_webhook_url",
    "gmail_app_password",
]

try:
    import keyring

    KEYRING_AVAILABLE = True
except Exception:  # pragma: no cover
    keyring = None
    KEYRING_AVAILABLE = False


def get_secret(name: str) -> str | None:
    if KEYRING_AVAILABLE:
        try:
            value = keyring.get_password(SERVICE, name)
            if value:
                return value
        except Exception as exc:
            log.warning("keyring read failed for %s: %s", name, exc)
    # Environment fallback (e.g. ANTHROPIC_API_KEY) — never plaintext files.
    return os.environ.get(name.upper())


def _allowed(name: str) -> bool:
    # Per-account email app passwords: email_password:<account id>
    return name in KNOWN_SECRETS or (name.startswith("email_password:") and len(name) < 80)


def set_secret(name: str, value: str) -> None:
    if not _allowed(name):
        raise ValueError("Unknown secret name")
    if not KEYRING_AVAILABLE:
        raise RuntimeError("OS keychain unavailable; cannot store secret safely")
    keyring.set_password(SERVICE, name, value)


def delete_secret(name: str) -> None:
    if KEYRING_AVAILABLE:
        try:
            keyring.delete_password(SERVICE, name)
        except Exception:
            pass


def secret_status() -> dict[str, bool]:
    """Which secrets are configured (never returns values)."""
    return {name: bool(get_secret(name)) for name in KNOWN_SECRETS}
