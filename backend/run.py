"""Jotva backend launcher.

Binds to a free loopback port, then prints a single JSON handshake line to
stdout so the Electron main process can read {port, token}. The token is never
written to disk (C2).
"""
import json
import socket
import sys
import atexit

# `--mcp`: serve the read-only MCP server over stdio for AI assistants. Stdout carries the
# protocol, so this must run before anything else can print.
if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == '--mcp':
    from app.mcp_server import main as mcp_main
    mcp_main()
    sys.exit(0)

# Handle a disposable analysis worker before importing the full application.
if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == '--speaker-worker':
    from app.services.speaker_worker import main as speaker_main
    sys.exit(speaker_main())

import uvicorn

from app.auth import SESSION_TOKEN
from app.main import create_app


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else find_free_port()
    app = create_app()
    from app.config import DATA_DIR, write_secure_text
    from app.routes.speakers import BRIDGE_TOKEN
    bridge_path = DATA_DIR / "speaker-bridge.json"
    # This token grants metadata ingestion/status only, never transcript access.
    write_secure_text(bridge_path, json.dumps({"port": port, "token": BRIDGE_TOKEN}))
    def remove_bridge():
        try:
            if json.loads(bridge_path.read_text()).get("token") == BRIDGE_TOKEN:
                bridge_path.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass
    atexit.register(remove_bridge)

    print(
        json.dumps({"event": "ready", "port": port, "token": SESSION_TOKEN, "speaker_token": BRIDGE_TOKEN}),
        flush=True,
    )
    # access_log=False: WS auth token travels as a query param and must never
    # appear in request logs (C2).
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
