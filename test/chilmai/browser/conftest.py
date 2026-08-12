from __future__ import annotations

import signal
import subprocess
import sys
import time
from urllib.request import urlopen

import pytest


@pytest.fixture(scope="module")
def api_server():
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "apps.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8501",
        ]
    )

    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with urlopen("http://127.0.0.1:8501/", timeout=1):
                break
        except Exception:
            time.sleep(0.5)
    else:
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=5)
        raise RuntimeError("API server did not start")

    yield process

    process.send_signal(signal.SIGTERM)
    process.wait(timeout=10)
