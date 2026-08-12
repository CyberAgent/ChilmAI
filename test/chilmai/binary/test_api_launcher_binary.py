from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest


@pytest.mark.binary
def test_api_launcher_binary_serves_top_page() -> None:
    if sys.platform != "win32":
        pytest.skip("binary test runs only on Windows")

    binary_path = Path("dist/ChilmAI/ChilmAI.exe")
    if not binary_path.exists():
        pytest.skip(f"binary not found: {binary_path}")

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    env = os.environ.copy()
    env["CHILMAI_HOST"] = "127.0.0.1"
    env["CHILMAI_PORT"] = str(port)

    process = subprocess.Popen([str(binary_path)], env=env)
    try:
        deadline = time.time() + 30
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                with urlopen(f"http://127.0.0.1:{port}/", timeout=2) as resp:
                    assert resp.status == 200
                    return
            except Exception as e:  # pragma: no cover - timing dependent
                last_error = e
                time.sleep(0.5)

        raise AssertionError(f"binary did not start in time: {last_error}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
