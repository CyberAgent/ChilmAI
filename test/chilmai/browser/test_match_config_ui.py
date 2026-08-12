from __future__ import annotations

import io
from pathlib import Path

import openpyxl
import pytest
from playwright.sync_api import Page, expect

DATA_DIR = Path(__file__).resolve().parents[3] / "test" / "data" / "e2e"
MANUAL_UI_DATA_DIR = Path(__file__).resolve().parents[3] / "test" / "data" / "manual_ui"

DEFAULT_CHILDREN_MAPPING = {
    "child_id": "申請者番号",
    "household_id": "世帯番号",
    "age": "年齢",
    "score_prefix": "スコアN",
    "preference_prefix": "希望保育園ID_N",
    "enrolled_daycare_id": "在籍保育所ID",
    "sibling_pattern": "きょうだいパターン",
}

DEFAULT_DAYCARES_MAPPING = {
    "daycare_id": "保育所ID",
    "daycare_name": "保育所名",
    "capacity_prefix": "N歳募集人数",
}

JP_CHILDREN_MAPPING = {
    "child_id": "児童ID",
    "household_id": "世帯ID",
    "age": "年齢",
    "score_prefix": "スコア",
    "preference_prefix": "希望",
}

JP_DAYCARES_MAPPING = {
    "daycare_id": "保育所ID",
    "daycare_name": "保育所名",
    "capacity_prefix": "N歳定員",
}


def _upload_match_files(page: Page, children_name: str, daycares_name: str) -> None:
    page.locator("#match-button").click()


def _save_config(page: Page, *, children_mapping: dict[str, str], daycares_mapping: dict[str, str]) -> None:
    page.goto("http://127.0.0.1:8501/settings")
    for key, value in children_mapping.items():
        page.locator(f"input[name='children__{key}']").fill(value)
    for key, value in daycares_mapping.items():
        page.locator(f"input[name='daycares__{key}']").fill(value)
    page.get_by_role("button", name="設定を保存").click()
    expect(page.locator("#config-result")).to_contain_text("設定を保存しました")

    # Persisted state verification to reduce HTMX timing-related flakes.
    page.reload()
    if "child_id" in children_mapping:
        expect(page.locator("input[name='children__child_id']")).to_have_value(children_mapping["child_id"])
    if "daycare_id" in daycares_mapping:
        expect(page.locator("input[name='daycares__daycare_id']")).to_have_value(
            daycares_mapping["daycare_id"]
        )


def _upload_validate_files(page: Page, children_path: Path, daycares_path: Path) -> None:
    page.locator("#matching-form input[name='children_file']").set_input_files(str(children_path))
    page.locator("#matching-form input[name='daycares_file']").set_input_files(str(daycares_path))
    page.locator("button[data-action='validate']").click()


def _upload_match_file_paths(page: Page, children_path: Path, daycares_path: Path) -> None:
    page.locator("#match-button").click()


@pytest.mark.browser
def test_match_success(page: Page, api_server):
    page.goto("http://127.0.0.1:8501/")
    _upload_validate_files(page, DATA_DIR / "valid_children.csv", DATA_DIR / "valid_daycares.csv")
    expect(page.locator("#match-button")).to_be_enabled()
    _upload_match_files(page, "valid_children.csv", "valid_daycares.csv")

    match_result = page.locator("#match-result")
    expect(match_result).to_contain_text("割り当てました")
    expect(match_result).to_contain_text("Excelをダウンロード")


@pytest.mark.browser
def test_match_family_household_result_and_combo_rank(page: Page, api_server):
    page.goto("http://127.0.0.1:8501/")
    _upload_validate_files(
        page,
        DATA_DIR / "family_children_prefer_same_any_month.csv",
        DATA_DIR / "valid_daycares.csv",
    )
    expect(page.locator("#match-button")).to_be_enabled()
    _upload_match_files(page, "family_children_prefer_same_any_month.csv", "valid_daycares.csv")

    match_result = page.locator("#match-result")
    expect(match_result).to_contain_text("割り当てました")
    expect(match_result).to_contain_text("Excelをダウンロード")


@pytest.mark.browser
def test_match_result_can_download_excel(page: Page, api_server):
    page.goto("http://127.0.0.1:8501/")
    _upload_validate_files(page, DATA_DIR / "valid_children.csv", DATA_DIR / "valid_daycares.csv")
    expect(page.locator("#match-button")).to_be_enabled()
    _upload_match_files(page, "valid_children.csv", "valid_daycares.csv")

    with page.expect_download() as download_info:
        page.get_by_role("button", name="Excelをダウンロード").click()

    download = download_info.value
    assert download.suggested_filename == "matching_result.xlsx"
    saved_path = Path(download.path())
    # Excel ファイルとして読み込めること（Playwrightの一時ファイルは拡張子なしのため BytesIO 経由で渡す）
    wb = openpyxl.load_workbook(io.BytesIO(saved_path.read_bytes()))
    ws = wb.active
    headers = [cell.value for cell in ws[1]]
    # 元ファイルの全列 + 末尾に入所選考結果列が追加されること
    assert "入所選考結果保育所ID" in headers
    assert "入所選考結果保育所名" in headers


@pytest.mark.browser
def test_match_button_disabled_after_file_change(page: Page, api_server):
    page.goto("http://127.0.0.1:8501/")
    _upload_validate_files(page, DATA_DIR / "valid_children.csv", DATA_DIR / "valid_daycares.csv")
    expect(page.locator("#match-button")).to_be_enabled()

    page.locator("#matching-form input[name='children_file']").set_input_files(
        str(DATA_DIR / "family_children_prefer_same_any_month.csv")
    )
    expect(page.locator("#match-button")).to_be_disabled()


@pytest.mark.browser
def test_config_mapping_with_japanese_columns(page: Page, api_server):
    _save_config(
        page,
        children_mapping=JP_CHILDREN_MAPPING,
        daycares_mapping=DEFAULT_DAYCARES_MAPPING,
    )

    page.goto("http://127.0.0.1:8501/")
    _upload_validate_files(page, DATA_DIR / "jp_children_small.csv", DATA_DIR / "valid_daycares.csv")
    expect(page.locator("#validate-result-content")).to_contain_text("問題ありません")
    expect(page.locator("#match-button")).to_be_enabled()

    _save_config(
        page,
        children_mapping=DEFAULT_CHILDREN_MAPPING,
        daycares_mapping=DEFAULT_DAYCARES_MAPPING,
    )


@pytest.mark.browser
def test_manual_ui_flow_validate_match_and_config_persistence(page: Page, api_server):
    page.goto("http://127.0.0.1:8501/")

    # Files matching DEFAULT_CONFIG (申請者番号, 希望保育園ID_N, N歳募集人数, ...)
    default_children = MANUAL_UI_DATA_DIR / "children_match_demo_jp.csv"
    default_daycares = MANUAL_UI_DATA_DIR / "daycares_match_demo_jp.csv"
    # Files matching JP_CHILDREN_MAPPING (児童ID, 希望N, ...) with canonical daycare columns
    alt_children = DATA_DIR / "jp_children_small.csv"
    alt_daycares = DATA_DIR / "valid_daycares.csv"

    try:
        _upload_validate_files(page, default_children, default_daycares)
        validate_result = page.locator("#validate-result-content")
        expect(validate_result).to_contain_text("問題ありません")
        expect(validate_result).to_contain_text("申込者数")
        expect(validate_result).to_contain_text("4")
        expect(validate_result).to_contain_text("保育所数")
        expect(validate_result).to_contain_text("2")
        expect(page.locator("#match-button")).to_be_enabled()

        _upload_match_file_paths(page, default_children, default_daycares)
        match_result = page.locator("#match-result")
        expect(match_result).to_contain_text("割り当てました")
        expect(match_result).to_contain_text("Excelをダウンロード")

        _save_config(
            page,
            children_mapping=JP_CHILDREN_MAPPING,
            daycares_mapping=JP_DAYCARES_MAPPING,
        )
        expect(page).to_have_url("http://127.0.0.1:8501/settings")
        page.reload()

        expect(page.locator("input[name='children__child_id']")).to_have_value("児童ID")
        expect(page.locator("input[name='children__preference_prefix']")).to_have_value("希望")
        expect(page.locator("input[name='daycares__daycare_id']")).to_have_value("保育所ID")
        expect(page.locator("input[name='daycares__capacity_prefix']")).to_have_value("N歳定員")

        page.goto("http://127.0.0.1:8501/")
        _upload_validate_files(page, alt_children, alt_daycares)
        validate_result = page.locator("#validate-result-content")
        expect(validate_result).to_contain_text("問題ありません")
        expect(validate_result).to_contain_text("申込者数")
        expect(page.locator("#match-button")).to_be_enabled()

        _upload_match_file_paths(page, alt_children, alt_daycares)
        match_result = page.locator("#match-result")
        expect(match_result).to_contain_text("割り当てました")
        expect(match_result).to_contain_text("Excelをダウンロード")
    finally:
        _save_config(
            page,
            children_mapping=DEFAULT_CHILDREN_MAPPING,
            daycares_mapping=DEFAULT_DAYCARES_MAPPING,
        )
