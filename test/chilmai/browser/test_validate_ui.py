from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

DATA_DIR = Path(__file__).resolve().parents[3] / "test" / "data" / "e2e"


def _upload_validate_files(page: Page, children_name: str, daycares_name: str) -> None:
    page.locator("#matching-form input[name='children_file']").set_input_files(
        str(DATA_DIR / children_name)
    )
    page.locator("#matching-form input[name='daycares_file']").set_input_files(
        str(DATA_DIR / daycares_name)
    )
    page.locator("button[data-action='validate']").click()


@pytest.mark.browser
def test_top_page(page: Page, api_server):
    page.goto("http://127.0.0.1:8501/")
    expect(page).to_have_title("ChilmAI")
    expect(page.locator("img.app-logo-img[alt='ChilmAI']")).to_be_visible()
    expect(page.locator("a.config-link")).to_be_visible()
    expect(page.locator("#match-button")).to_be_disabled()


@pytest.mark.browser
def test_file_upload_summary_initial(page: Page, api_server):
    """未選択時: 日本語の初期文言が1箇所だけ表示される。"""
    page.goto("http://127.0.0.1:8501/")

    children_summary = page.locator("[data-file-summary='children_file']")
    daycares_summary = page.locator("[data-file-summary='daycares_file']")

    expect(children_summary).to_have_count(1)
    expect(children_summary).to_have_text("ファイルが選択されていません")

    expect(daycares_summary).to_have_count(1)
    expect(daycares_summary).to_have_text("ファイルが選択されていません")


@pytest.mark.browser
def test_file_upload_summary_after_selection(page: Page, api_server):
    """ファイル選択後: ファイル名が summary に1箇所だけ表示される。"""
    page.goto("http://127.0.0.1:8501/")

    children_input = page.locator("#matching-form input[name='children_file']")
    daycares_input = page.locator("#matching-form input[name='daycares_file']")

    children_input.set_input_files(str(DATA_DIR / "valid_children.csv"))
    daycares_input.set_input_files(str(DATA_DIR / "valid_daycares.csv"))

    expect(page.locator("[data-file-summary='children_file']")).to_have_text("選択済み：valid_children.csv")
    expect(page.locator("[data-file-summary='daycares_file']")).to_have_text("選択済み：valid_daycares.csv")


@pytest.mark.browser
def test_validate_button_disabled_until_both_files_selected(page: Page, api_server):
    """片方だけ選択: validate ボタンは無効、両方選択後に有効になる。"""
    page.goto("http://127.0.0.1:8501/")

    validate_button = page.locator("button[data-action='validate']")
    hint = page.locator("#validate-button-hint")

    expect(validate_button).to_be_disabled()
    expect(hint).to_be_visible()

    page.locator("#matching-form input[name='children_file']").set_input_files(
        str(DATA_DIR / "valid_children.csv")
    )
    expect(validate_button).to_be_disabled()
    expect(hint).to_be_visible()

    page.locator("#matching-form input[name='daycares_file']").set_input_files(
        str(DATA_DIR / "valid_daycares.csv")
    )
    expect(validate_button).to_be_enabled()
    expect(hint).to_be_hidden()


@pytest.mark.browser
def test_file_upload_drop_area_data_selected(page: Page, api_server):
    """ファイル選択後: drop-area と summary に data-selected 属性が付く。"""
    page.goto("http://127.0.0.1:8501/")

    page.locator("#matching-form input[name='children_file']").set_input_files(
        str(DATA_DIR / "valid_children.csv")
    )

    children_summary = page.locator("[data-file-summary='children_file']")
    children_drop_area = page.locator("#children-file-input").locator(
        "xpath=ancestor::*[contains(@class,'dads-file-upload__drop-area')]"
    )

    expect(children_summary).to_have_attribute("data-selected", "")
    expect(children_drop_area).to_have_attribute("data-selected", "")

    daycares_summary = page.locator("[data-file-summary='daycares_file']")
    expect(daycares_summary).not_to_have_attribute("data-selected", "")


@pytest.mark.browser
def test_validate_success(page: Page, api_server):
    page.goto("http://127.0.0.1:8501/")
    _upload_validate_files(page, "valid_children.csv", "valid_daycares.csv")

    validate_result = page.locator("#validate-result-content")
    expect(validate_result).to_contain_text("データ確認結果")
    expect(validate_result.locator("table")).to_have_count(0)
    expect(validate_result.locator(".validate-summary-cards")).to_have_count(1)
    expect(validate_result).to_contain_text("申込者数")
    expect(validate_result).to_contain_text("問題ありません")


@pytest.mark.browser
def test_validate_unknown_daycare_error(page: Page, api_server):
    page.goto("http://127.0.0.1:8501/")
    _upload_validate_files(page, "invalid_children_unknown_daycare.csv", "valid_daycares.csv")

    validate_result = page.locator("#validate-result-content")
    expect(validate_result).to_contain_text("問題があります")
    expect(validate_result).to_contain_text("保育所ファイルに存在しない保育所ID")


@pytest.mark.browser
def test_validate_inconsistent_sibling_pattern_error(page: Page, api_server):
    page.goto("http://127.0.0.1:8501/")
    _upload_validate_files(
        page,
        "invalid_children_inconsistent_sibling_pattern.csv",
        "valid_daycares.csv",
    )

    validate_result = page.locator("#validate-result-content")
    expect(validate_result).to_contain_text("問題があります")
    expect(validate_result).to_contain_text("きょうだいパターン」が同一世帯内で一致しません")
