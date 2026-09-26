"""Paths, data-directory setup, and runtime configuration for Jotva."""
import json
import os
import stat
from pathlib import Path

APP_NAME = "Jotva"

DATA_DIR = Path(
    os.environ.get(
        "JOTVA_DATA_DIR",
        Path.home() / "Library" / "Application Support" / APP_NAME,
    )
)
RECORDINGS_DIR = DATA_DIR / "recordings"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
NOTES_DIR = DATA_DIR / "notes"
EXPORTS_DIR = DATA_DIR / "exports"
LOGS_DIR = DATA_DIR / "logs"
DB_PATH = DATA_DIR / "jotva.db"

# Origins allowed to talk to the backend. Dev server + packaged custom protocol.
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "app://jotva",
    "jotva-ios://app",  # Mobile companion app
]
# Host headers we accept (DNS-rebinding defense). Port is appended at startup.
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}

# Default to the cheapest current model that is accurate for structured notes
# extraction (~$0.025/meeting-hour). Users with their own key can pick another
# model in Settings; the bundled proxy allows haiku-4-5 and sonnet-5.
CLAUDE_MODEL = os.environ.get("JOTVA_CLAUDE_MODEL", "claude-haiku-4-5")
DEFAULT_AI_PROVIDER = os.environ.get("JOTVA_AI_PROVIDER", "anthropic")
DEFAULT_OPENAI_MODEL = os.environ.get("JOTVA_OPENAI_MODEL", "gpt-4o")
DEFAULT_GEMINI_MODEL = os.environ.get("JOTVA_GEMINI_MODEL", "gemini-2.0-flash")
# Default to "small": measurably better on names/numbers than "base" for a modest
# speed cost (~9s extra per 3 min of audio on Apple Silicon). A user's explicit
# whisper_model setting still overrides this.
WHISPER_MODEL = os.environ.get("JOTVA_WHISPER_MODEL", "small")
# Until getjotva.com is live, the license server answers on its original domain.
# Everything that talks to it (AI proxy, checkout, portal, Google OAuth broker)
# derives from this one value.
LICENSE_SERVER_URL = os.environ.get(
    "JOTVA_LICENSE_SERVER", "https://license.aguacatenotes.com/api"
)
# Bundled-AI proxy base URL. The Anthropic SDK appends /v1/messages; the proxy
# authenticates by install_id and holds the real API key server-side.
AI_PROXY_URL = LICENSE_SERVER_URL + "/ai"

# Public half of the license-signing keypair. Licenses fetched from the license
# server are only trusted if their RSA-SHA256 signature verifies against this
# key AND they name this install AND they have not expired — so neither a spoofed
# JOTVA_LICENSE_SERVER nor a MITM'd response can grant Pro.
LICENSE_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAo/bfN5nkOUQn1TKSGLYL
XRaoWvF0tqni5b3EV+yEl4mJRxQApCg8OcOKjT5d+v40q4j5Ih4yG5nkQ4auEkIL
nQ4oOfFdD/uMMjMTpLFgjfT8rlD+hCNwfTsidy2Cf5TxwTWBxVTzY0p+NtA9zk7j
IhhgxxuRXbhQ0wN1PdjYBywlhVptZ5/E02VTryUcE18U1L+PgYfRQ6vhyNq4Ydf1
q6r3xutfVxWEXg/wnFQy2FfUAIemPSdJSSliJoZsDrYWEHiAuYWhXqwkEYPerSQf
Oz4dBfqqeSwFsew5nKqxAuFviT7mkqPsD8Lug1pQIvLD+ITaXJ3FAAnrWPqYwfY2
NQIDAQAB
-----END PUBLIC KEY-----"""
STRIPE_CHECKOUT_URL = os.environ.get(
    "JOTVA_CHECKOUT_URL", "https://buy.stripe.com/cNieVf0mZ0iN7ml6AL6sw04"
)
FREE_TIER_LIMIT = 5

# DEV ONLY: gates developer-testing endpoints (e.g. /api/dev/set-tier). Requires
# an EXPLICIT opt-in — a packaged binary launched from a shell that happens to
# export NODE_ENV=development must not grow a Pro-bypass endpoint, so ambient
# environment variables are deliberately not consulted.
DEV_MODE = (
    os.environ.get("DEV_MODE", "").lower() == "true"
    or os.environ.get("JOTVA_DEV") == "1"
)

# OAuth client config is user-supplied (never bundled). See credentials.example.json.
CREDENTIALS_PATH = DATA_DIR / "credentials.json"

# Default public OAuth client_id (PKCE flow — no secret). Used when credentials.json
# does not supply one; credentials.json still overrides this for backward compatibility.
# Must match the client the license-server broker exchanges tokens for.
GOOGLE_CLIENT_ID = "316282714383-nheoav7hcoj4sd00ooge7s0k2onblv8e.apps.googleusercontent.com"


def _secure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, stat.S_IRWXU)  # 700


def ensure_dirs() -> None:
    for d in (DATA_DIR, RECORDINGS_DIR, TRANSCRIPTS_DIR, NOTES_DIR, EXPORTS_DIR, LOGS_DIR):
        _secure_dir(d)


def secure_file(path: Path) -> None:
    """chmod 600 a file we just created."""
    if path.exists():
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def touch_secure(path: Path) -> None:
    """Create (or truncate-safe touch) a file with 0600 atomically, so it never
    exists with default-umask permissions (C5)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
    os.close(fd)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # in case it pre-existed


def write_secure_text(path: Path, text: str) -> None:
    """Write text to a file that is 0600 from the instant it exists."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def load_oauth_credentials() -> dict:
    """Load user-supplied OAuth client config (public client IDs only, PKCE flow)."""
    if CREDENTIALS_PATH.exists():
        try:
            with open(CREDENTIALS_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def is_safe_managed_path(path: str) -> bool:
    """True only if path resolves inside our data directory (no traversal)."""
    try:
        resolved = Path(path).resolve()
        return resolved.is_relative_to(DATA_DIR.resolve())
    except (OSError, ValueError):
        return False
