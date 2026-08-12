from __future__ import annotations

import os
import socket
import sys

# Must be set before importing `app` — apps/api/main.py reads this env var at
# import time to initialize templates.env.globals["is_packaged"].
if getattr(sys, "frozen", False):
    os.environ["CHILMAI_PACKAGED"] = "1"

import threading
import time
import webbrowser

import uvicorn
from apps.api.main import app


def _browser_host(host: str) -> str:
    if host in {"0.0.0.0", "::", "[::]"}:
        return "127.0.0.1"
    return host


def _open_browser(host: str, port: int) -> None:
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.1)
    webbrowser.open(f"http://{host}:{port}")


def main() -> None:
    host = os.getenv("CHILMAI_HOST", "127.0.0.1")
    port = int(os.getenv("CHILMAI_PORT", "8501"))

    if getattr(sys, "frozen", False):
        browser_host = _browser_host(host)
        threading.Thread(target=_open_browser, args=(browser_host, port), daemon=True).start()

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
