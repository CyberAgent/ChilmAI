#!/usr/bin/env python3
"""Playwright-based screenshot capture for the ChilmAI web UI docs.

Usage (from repo root):
    uv run python scripts/capture_manual.py [--open]

Output: docs/reference/web-ui/images/*.png

Windows-only images (04_cmd_window, 03_smartscreen, 03_firewall, 10_task_manager)
must be captured manually and placed in docs/reference/web-ui/images/.
"""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import Page, sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "docs" / "reference" / "web-ui" / "images"
E2E_DIR = REPO_ROOT / "test" / "data" / "e2e"
MANUAL_UI_DIR = REPO_ROOT / "test" / "data" / "manual_ui"
SAMPLE_DIR = REPO_ROOT / "sample"

BASE_URL = "http://127.0.0.1:8501"
VIEWPORT = {"width": 1440, "height": 900}
WAIT_MS = 15_000
MATCH_WAIT_MS = 90_000


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------


def _start_server() -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "apps.api.main:app", "--host", "127.0.0.1", "--port", "8501"],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with urlopen(f"{BASE_URL}/", timeout=1):
                return proc
        except Exception:
            time.sleep(0.5)
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=5)
    raise RuntimeError("API server did not start within 30 seconds")


def _stop_server(proc: subprocess.Popen) -> None:
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=10)


# ---------------------------------------------------------------------------
# Screenshot helpers
# ---------------------------------------------------------------------------


def _shot(page: Page, name: str) -> None:
    path = OUT_DIR / name
    page.screenshot(path=str(path), full_page=False)
    print(f"  ✓ {path.relative_to(REPO_ROOT)}")


def _shot_element(page: Page, selector: str, name: str, *, padding: int = 16) -> None:
    loc = page.locator(selector)
    loc.wait_for(state="visible", timeout=WAIT_MS)
    loc.scroll_into_view_if_needed(timeout=WAIT_MS)
    # Let layout settle after scrolling before sampling the bounding box.
    page.wait_for_timeout(100)
    bb = loc.bounding_box()
    if bb is None:
        raise RuntimeError(f"bounding box not found for {selector!r}")
    clip = {
        "x": max(0.0, bb["x"] - padding),
        "y": max(0.0, bb["y"] - padding),
        "width": bb["width"] + 2 * padding,
        "height": bb["height"] + 2 * padding,
    }
    path = OUT_DIR / name
    page.screenshot(path=str(path), clip=clip)
    print(f"  ✓ {path.relative_to(REPO_ROOT)}")


def _goto(page: Page, url: str) -> None:
    page.goto(url, wait_until="networkidle", timeout=WAIT_MS * 2)


# ---------------------------------------------------------------------------
# Chapter 4 — Layout
# ---------------------------------------------------------------------------


def capture_04_top_screen(page: Page) -> None:
    print("04_top_screen …")
    _goto(page, f"{BASE_URL}/")
    page.locator("#matching-form").wait_for(state="visible", timeout=WAIT_MS)
    _shot(page, "04_top_screen.png")


# ---------------------------------------------------------------------------
# Chapter 6 — Initial Setup
# ---------------------------------------------------------------------------


def _activate_profile(page: Page, profile_name: str) -> None:
    """Activate a named profile via the settings page profile panel."""
    _goto(page, f"{BASE_URL}/settings")
    _set_details_open(page, "details.profile-disclosure", open_=True)
    button = page.locator(
        f"form[action='/profiles/activate'] input[value='{profile_name}'] + button, "
        f"form[action='/profiles/activate'] button:has-text('{profile_name}')"
    ).first
    if button.count() > 0 and button.is_enabled():
        button.click()
        page.wait_for_url(f"{BASE_URL}/settings", timeout=WAIT_MS)


def _ensure_profile_exists(page: Page, name: str) -> None:
    """Create profile if it does not exist (best-effort via the UI form)."""
    _goto(page, f"{BASE_URL}/settings")
    _set_details_open(page, "details.profile-disclosure", open_=True)
    existing = page.locator(f"details.profile-disclosure .profile-list__select-form input[value='{name}']")
    if existing.count() > 0:
        return
    # If the locator returned nothing but the disclosure is open, the profile truly
    # doesn't exist yet — proceed to create it.  If the selector itself is broken
    # (e.g. CSS class name changed), the creation form below will also fail loudly,
    # so no silent swallow here.
    print(f"  profile '{name}' not found — creating …")
    # Open the profile-create <details> and submit the creation form.
    page.evaluate(
        "sel => { const el = document.querySelector(sel); if (el) el.open = true; }",
        "details.profile-create",
    )
    page.locator("details.profile-create input[name='profile_name']").fill(name)
    page.locator("details.profile-create form[action='/profiles/create'] button[type='submit']").click()
    page.wait_for_url(f"{BASE_URL}/settings", timeout=WAIT_MS)


def capture_06_settings_link(page: Page) -> None:
    print("06_settings_link …")
    # Activate the default profile so the chip shows "デフォルト" — the state
    # a fresh install starts in.
    _activate_profile(page, "default")
    _reset_config(page)
    _goto(page, f"{BASE_URL}/")
    page.locator("a.config-link").wait_for(state="visible", timeout=WAIT_MS)
    _shot_element(page, "header.app-header", "06_settings_link.png", padding=0)


def capture_06_settings_link_profile(page: Page) -> None:
    """Header shot with a non-default profile active, to illustrate chip switching."""
    print("06_settings_link_profile …")
    _ensure_profile_exists(page, "2026年度")
    _activate_profile(page, "2026年度")
    _goto(page, f"{BASE_URL}/")
    page.locator("a.config-link").wait_for(state="visible", timeout=WAIT_MS)
    _shot_element(page, "header.app-header", "06_settings_link_profile.png", padding=0)
    # Restore default so subsequent captures start from a clean state.
    _activate_profile(page, "default")


def _set_details_open(page: Page, selector: str, *, open_: bool) -> None:
    """Force a <details> element open/closed via DOM (more robust than clicking)."""
    page.evaluate(
        "([sel, op]) => { const el = document.querySelector(sel); if (el) el.open = op; }",
        [selector, open_],
    )


def capture_06_settings(page: Page) -> None:
    _goto(page, f"{BASE_URL}/settings")
    page.locator("section.mapping-card").wait_for(state="visible", timeout=WAIT_MS)

    # Collapse all <details> so the overview shows the page in its
    # most representative initial state.
    _set_details_open(page, "details.profile-disclosure", open_=False)
    _set_details_open(page, "details.quickfill", open_=False)
    _set_details_open(page, "details.settings-advanced", open_=False)

    print("06_settings_overview …")
    _shot(page, "06_settings_overview.png")

    print("06_settings_profile_panel …")
    _set_details_open(page, "details.profile-disclosure", open_=True)
    page.locator("details.profile-disclosure .profile-list").wait_for(state="visible", timeout=WAIT_MS)
    _shot_element(
        page,
        "details.profile-disclosure",
        "06_settings_profile_panel.png",
        padding=12,
    )
    _set_details_open(page, "details.profile-disclosure", open_=False)

    # Open the sample auto-fill block for the next captures.
    _set_details_open(page, "details.quickfill", open_=True)
    page.locator("#sample-analyze-form").wait_for(state="visible", timeout=WAIT_MS)

    print("06_settings_sample_select …")
    page.locator("#sample-children-file").set_input_files(str(E2E_DIR / "jp_children_small.csv"))
    page.wait_for_function(
        "!document.querySelector('#sample-analyze-button').disabled",
        timeout=WAIT_MS,
    )
    _shot(page, "06_settings_sample_select.png")

    print("06_settings_suggestion_table …")
    page.locator("#sample-analyze-button").click()
    page.locator("#sample-suggestion-result .suggestion-result").wait_for(state="visible", timeout=WAIT_MS)
    _shot_element(
        page,
        "#sample-suggestion-result .suggestion-result",
        "06_settings_suggestion_table.png",
        padding=12,
    )

    print("06_settings_form_filled …")
    page.locator("#suggestion-apply-button").click()
    page.locator("#sample-suggestion-result .notice--success").wait_for(state="visible", timeout=WAIT_MS)
    # Crop to the mapping form so the filled rows + green status dots are clearly visible.
    _shot_element(
        page,
        "section.mapping-card",
        "06_settings_form_filled.png",
        padding=12,
    )

    print("06_settings_default_reset …")
    _set_details_open(page, "details.settings-advanced", open_=True)
    page.locator("details.settings-advanced .settings-advanced__row").wait_for(
        state="visible", timeout=WAIT_MS
    )
    _shot_element(
        page,
        "details.settings-advanced",
        "06_settings_default_reset.png",
        padding=12,
    )
    _set_details_open(page, "details.settings-advanced", open_=False)


def _reset_config(page: Page) -> None:
    """POST /config/reset via the settings page reset button (now inside a <details>)."""
    _goto(page, f"{BASE_URL}/settings")
    _set_details_open(page, "details.settings-advanced", open_=True)
    page.locator("details.settings-advanced .settings-advanced__row").wait_for(
        state="visible", timeout=WAIT_MS
    )
    page.once("dialog", lambda d: d.accept())
    page.locator("details.settings-advanced form[action='/config/reset'] button").click()
    # The redirect lands back on /settings.
    page.wait_for_url(f"{BASE_URL}/settings", timeout=WAIT_MS)


# ---------------------------------------------------------------------------
# Chapter 7 — Usage
# ---------------------------------------------------------------------------


def _load_demo_files(page: Page) -> None:
    """Load the sample demo CSV pair (申込者データ_デモ + 保育所データ_デモ) into the upload form.

    These files use the default column-name configuration (点数N / 希望保育園ID_N),
    so they work correctly after a config reset.  They also match the data described
    in chapter 5 of the manual (5 children, 3 daycares).
    """
    page.locator("#matching-form input[name='children_file']").set_input_files(
        str(SAMPLE_DIR / "申込者データ_デモ.csv")
    )
    page.locator("#matching-form input[name='daycares_file']").set_input_files(
        str(SAMPLE_DIR / "保育所データ_デモ.csv")
    )
    page.wait_for_function(
        "!document.querySelector('button[data-action=\"validate\"]').disabled",
        timeout=WAIT_MS,
    )


def capture_07_upload_panel(page: Page) -> None:
    print("07_upload_panel …")
    _goto(page, f"{BASE_URL}/")
    _load_demo_files(page)
    _shot(page, "07_upload_panel.png")


def capture_07_validate_success(page: Page) -> None:
    print("07_validate_success …")
    _goto(page, f"{BASE_URL}/")
    _load_demo_files(page)
    page.locator("button[data-action='validate']").click()
    page.wait_for_function(
        "document.querySelector('#validate-result-content')?.innerText.includes('問題ありません')",
        timeout=WAIT_MS * 3,
    )
    _shot(page, "07_validate_success.png")


def capture_07_validate_error(page: Page) -> None:
    print("07_validate_error …")
    _goto(page, f"{BASE_URL}/")
    # Use a demo-format file that references a non-existent daycare ID (999),
    # paired with the standard demo daycare file.  Both files use the default
    # column names so they load cleanly after a config reset.
    page.locator("#matching-form input[name='children_file']").set_input_files(
        str(MANUAL_UI_DIR / "children_demo_invalid_daycare.csv")
    )
    page.locator("#matching-form input[name='daycares_file']").set_input_files(
        str(SAMPLE_DIR / "保育所データ_デモ.csv")
    )
    page.locator("button[data-action='validate']").click()
    page.wait_for_function(
        "document.querySelector('#validate-result-content')?.innerText.includes('問題があります')",
        timeout=WAIT_MS * 3,
    )
    _shot(page, "07_validate_error.png")


def capture_07_match_complete(page: Page) -> None:
    print("07_match_complete …")
    _goto(page, f"{BASE_URL}/")
    _load_demo_files(page)
    page.locator("button[data-action='validate']").click()
    page.wait_for_function(
        "document.querySelector('#validate-result-content')?.innerText.includes('問題ありません')",
        timeout=WAIT_MS * 3,
    )
    page.wait_for_function(
        "!document.querySelector('#match-button').disabled",
        timeout=WAIT_MS,
    )
    page.locator("#match-button").click()
    page.wait_for_function(
        "document.querySelector('#match-result')?.innerText.includes('割り当てました')",
        timeout=MATCH_WAIT_MS,
    )
    _shot(page, "07_match_complete.png")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

WINDOWS_ONLY = [
    "04_cmd_window.png",
    "03_smartscreen.png",
    "03_firewall.png",
    "10_task_manager.png",
    "03_github_releases.png",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture ChilmAI manual screenshots")
    parser.add_argument(
        "--open", action="store_true", help="Run browser in non-headless mode (useful for debugging)"
    )
    parser.add_argument(
        "--reuse-server",
        action="store_true",
        help="Assume a server is already running at 127.0.0.1:8501 (do not start/stop one)",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        default=None,
        choices=["top", "settings_link", "settings_link_profile", "settings", "usage"],
        help="Run only the listed capture groups (default: all)",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    server = None
    if args.reuse_server:
        print("Reusing existing API server at 127.0.0.1:8501.\n")
    else:
        print("Starting API server…")
        server = _start_server()
        print("Server ready.\n")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not args.open)
            ctx = browser.new_context(viewport=VIEWPORT, locale="ja-JP")
            ctx.set_default_timeout(WAIT_MS)
            page = ctx.new_page()

            only = (
                set(args.only)
                if args.only
                else {
                    "top",
                    "settings_link",
                    "settings_link_profile",
                    "settings",
                    "usage",
                }
            )
            if "top" in only:
                capture_04_top_screen(page)
            if "settings_link" in only:
                capture_06_settings_link(page)
            if "settings_link_profile" in only:
                capture_06_settings_link_profile(page)
            if "settings" in only:
                capture_06_settings(page)
            if "usage" in only:
                # Activate the default profile and reset its config so demo files
                # (which use default column names) pass validation and the header
                # chip shows "デフォルト" regardless of which profile was active.
                _activate_profile(page, "default")
                _reset_config(page)
                capture_07_upload_panel(page)
                capture_07_validate_success(page)
                capture_07_validate_error(page)
                capture_07_match_complete(page)

            browser.close()
    finally:
        if server is not None:
            print("\nStopping server…")
            _stop_server(server)

    print("\nDone.")
    print("\nThe following images must be captured manually on Windows:")
    for name in WINDOWS_ONLY:
        print(f"  docs/reference/web-ui/images/{name}")


if __name__ == "__main__":
    main()
