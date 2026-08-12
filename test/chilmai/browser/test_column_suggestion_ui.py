from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

DATA_DIR = Path(__file__).resolve().parents[3] / "test" / "data" / "e2e"


def _open_quickfill(page: Page) -> None:
    """Force the sample auto-mapping <details> block open via DOM."""
    page.evaluate(
        "() => { const el = document.querySelector('details.quickfill'); if (el) el.open = true; }"
    )


@pytest.mark.browser
def test_sample_analyze_button_disabled_until_file_chosen(page: Page, api_server):
    page.goto("http://127.0.0.1:8501/settings")
    _open_quickfill(page)
    expect(page.locator("#sample-analyze-button")).to_be_disabled()

    page.locator("#sample-children-file").set_input_files(str(DATA_DIR / "jp_children_small.csv"))
    expect(page.locator("#sample-analyze-button")).to_be_enabled()


@pytest.mark.browser
def test_analyze_renders_suggestions_and_apply_fills_form(page: Page, api_server):
    page.goto("http://127.0.0.1:8501/settings")
    _open_quickfill(page)

    page.locator("#sample-children-file").set_input_files(str(DATA_DIR / "jp_children_small.csv"))
    page.locator("#sample-analyze-button").click()

    suggestion = page.locator("#sample-suggestion-result .suggestion-result")
    expect(suggestion).to_be_visible()
    expect(suggestion).to_contain_text("解析しました")

    expect(page.locator('[data-suggestion-row="children__child_id"]')).to_be_visible()
    expect(page.locator('[data-suggestion-row="children__child_id"] code')).to_have_text("児童ID")

    page.locator("#suggestion-apply-button").click()

    expect(page.locator("input[name='children__child_id']")).to_have_value("児童ID")
    expect(page.locator("input[name='children__household_id']")).to_have_value("世帯ID")
    expect(page.locator("#sample-suggestion-result .notice--success")).to_be_visible()


@pytest.mark.browser
def test_dismiss_clears_suggestion(page: Page, api_server):
    page.goto("http://127.0.0.1:8501/settings")
    _open_quickfill(page)
    page.locator("#sample-children-file").set_input_files(str(DATA_DIR / "jp_children_small.csv"))
    page.locator("#sample-analyze-button").click()
    expect(page.locator("#sample-suggestion-result .suggestion-result")).to_be_visible()

    page.locator("#suggestion-dismiss-button").click()
    expect(page.locator("#sample-suggestion-result .suggestion-result")).to_have_count(0)


@pytest.mark.browser
def test_unchecked_row_is_not_applied(page: Page, api_server):
    page.goto("http://127.0.0.1:8501/settings")
    _open_quickfill(page)
    page.locator("input[name='children__household_id']").fill("元の世帯値")

    page.locator("#sample-children-file").set_input_files(str(DATA_DIR / "jp_children_small.csv"))
    page.locator("#sample-analyze-button").click()

    page.locator('[data-suggestion-row="children__household_id"] .suggestion-accept-checkbox').uncheck()

    page.locator("#suggestion-apply-button").click()

    expect(page.locator("input[name='children__child_id']")).to_have_value("児童ID")
    expect(page.locator("input[name='children__household_id']")).to_have_value("元の世帯値")
