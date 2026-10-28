from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest
from playwright.sync_api import Page, expect

DATA_DIR = Path(__file__).resolve().parents[3] / "test" / "data" / "e2e"
BASE_URL = "http://127.0.0.1:8502"


@pytest.fixture(scope="module")
def customized_api_server():
    env = {
        **os.environ,
        "CHILMAI_WEB_CUSTOMIZATION": "examples.sample_web_customization:SampleWebCustomization",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "apps.api.main:app", "--host", "127.0.0.1", "--port", "8502"],
        env=env,
    )

    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with urlopen(f"{BASE_URL}/", timeout=1):
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


@pytest.mark.browser
def test_param_inputs_are_sent_and_reset_match_button(page: Page, customized_api_server):
    page.goto(f"{BASE_URL}/")
    expect(page.locator("#param-fiscal_year")).to_have_value("2027")
    expect(page.locator("#param-month")).to_have_value("4")
    expect(page.locator("#param-add_remarks")).to_be_checked()

    page.locator("#matching-form input[name='children_file']").set_input_files(
        str(DATA_DIR / "valid_children.csv")
    )
    page.locator("#matching-form input[name='daycares_file']").set_input_files(
        str(DATA_DIR / "valid_daycares.csv")
    )
    page.locator("button[data-action='validate']").click()
    match_button = page.locator("#match-button")
    expect(match_button).to_be_enabled()

    # 入力項目を変えたらデータ確認からやり直す。
    page.locator("#panel-2 [data-nav-to='1']").click()
    page.locator("#param-month").select_option("5")
    expect(match_button).to_be_disabled()
    expect(page.locator("#panel-1")).to_be_visible()

    page.locator("button[data-action='validate']").click()
    expect(match_button).to_be_enabled()
    match_button.click()

    download_button = page.locator("[data-download-excel]")
    expect(download_button).to_have_attribute("data-download-filename", "選考結果_2027年度5月.xlsx")
    with page.expect_download() as download_info:
        download_button.click()
    assert download_info.value.suggested_filename == "選考結果_2027年度5月.xlsx"
