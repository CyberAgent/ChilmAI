from __future__ import annotations

import io

import openpyxl
import pytest

from chilmai.generic.config import DEFAULT_CONFIG
from chilmai.generic.error_codes import ErrorCode
from chilmai.generic.parser import InputParser
from chilmai.generic.service import MatchingService


def _daycares_csv() -> bytes:
    return (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,A,0,1,0,0,0,0\n"
        "101,B,0,1,0,0,0,0\n"
    ).encode("utf-8")


def test_parser_maps_fullwidth_preference_prefix():
    """全角数字の列名（希望１, 希望２）を pref_1, pref_2 に変換できること。"""
    parser = InputParser()
    children = ("児童ID,世帯ID,年齢,score_1,希望１,希望２\n" "1,10,1,100,100,101\n").encode("utf-8")

    mapping = {
        "child_id": "児童ID",
        "household_id": "世帯ID",
        "age": "年齢",
        "preference_prefix": "希望N",
    }
    parsed = parser.parse_children(file_bytes=children, file_format="csv", mapping=mapping)

    assert "pref_1" in parsed.columns
    assert "pref_2" in parsed.columns
    assert parsed.loc[0, "pref_1"] == "100"
    assert parsed.loc[0, "pref_2"] == "101"


def test_parser_maps_fullwidth_score_prefix():
    """全角数字の列名（スコア１, スコア２）を score_1, score_2 に変換できること。"""
    parser = InputParser()
    children = (
        "child_id,household_id,age,スコア１,スコア２,pref_1,pref_2,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,90,100,101,,\n"
    ).encode("utf-8")

    mapping = {"score_prefix": "スコアN"}
    parsed = parser.parse_children(file_bytes=children, file_format="csv", mapping=mapping)

    assert "score_1" in parsed.columns
    assert "score_2" in parsed.columns
    assert parsed.loc[0, "score_1"] == "100"
    assert parsed.loc[0, "score_2"] == "90"


def test_parser_maps_fullwidth_capacity_prefix():
    """全角数字の列名（０歳定員, １歳定員）を capacity_age0, capacity_age1 に変換できること。"""
    parser = InputParser()
    daycares = (
        "daycare_id,daycare_name,０歳定員,１歳定員,２歳定員,３歳定員,４歳定員,５歳定員\n"
        "100,A,0,2,3,4,5,6\n"
    ).encode("utf-8")

    mapping = {"capacity_prefix": "N歳定員"}
    parsed = parser.parse_daycares(file_bytes=daycares, file_format="csv", mapping=mapping)

    assert "capacity_age0" in parsed.columns
    assert "capacity_age1" in parsed.columns
    assert parsed.loc[0, "capacity_age0"] == "0"
    assert parsed.loc[0, "capacity_age1"] == "2"


def test_read_columns_normalizes_fullwidth_digits():
    """read_columns が全角数字を半角に正規化して返すこと。"""
    parser = InputParser()
    csv_bytes = "児童ID,希望１,希望２\n1,100,101\n".encode("utf-8")
    cols = parser.read_columns(io.BytesIO(csv_bytes), "csv")

    assert "希望1" in cols
    assert "希望2" in cols
    assert "希望１" not in cols
    assert "希望２" not in cols


def test_parser_maps_fullwidth_user_name_in_mapping():
    """既存設定に全角のまま保存された user_name でも正しくマッピングできること（後方互換）。"""
    parser = InputParser()
    children = ("児童ＩＤ,世帯ID,年齢,score_1,pref_1\n" "1,10,1,100,100\n").encode("utf-8")

    # 全角ID が設定に保存されているケース
    mapping = {
        "child_id": "児童ＩＤ",
        "household_id": "世帯ID",
        "age": "年齢",
    }
    parsed = parser.parse_children(file_bytes=children, file_format="csv", mapping=mapping)

    assert "child_id" in parsed.columns
    assert parsed.loc[0, "child_id"] == "1"


def test_parser_maps_custom_preference_prefix():
    parser = InputParser()
    children = ("児童ID,世帯ID,年齢,score_1,希望1,希望2\n" "1,10,1,100,100,101\n").encode("utf-8")

    mapping = {
        "child_id": "児童ID",
        "household_id": "世帯ID",
        "age": "年齢",
        "preference_prefix": "希望",
    }
    parsed = parser.parse_children(file_bytes=children, file_format="csv", mapping=mapping)

    assert "pref_1" in parsed.columns
    assert "pref_2" in parsed.columns
    assert parsed.loc[0, "pref_1"] == "100"


def test_parser_maps_custom_score_prefix():
    parser = InputParser()
    children = (
        "child_id,household_id,age,スコア1,スコア2,pref_1,pref_2,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,90,100,101,,\n"
    ).encode("utf-8")

    mapping = {
        "score_prefix": "スコア",
    }
    parsed = parser.parse_children(file_bytes=children, file_format="csv", mapping=mapping)

    assert "score_1" in parsed.columns
    assert "score_2" in parsed.columns
    assert parsed.loc[0, "score_1"] == "100"
    assert parsed.loc[0, "score_2"] == "90"


def test_parser_maps_n_placeholder_prefix():
    """N が先頭にある列名（例: N歳定員 → 0歳定員, 1歳定員）のマッピングを確認する。"""
    parser = InputParser()
    daycares = (
        "daycare_id,daycare_name,0歳定員,1歳定員,2歳定員,3歳定員,4歳定員,5歳定員\n" "100,A,0,2,3,4,5,6\n"
    ).encode("utf-8")

    mapping = {"capacity_prefix": "N歳定員"}
    parsed = parser.parse_daycares(file_bytes=daycares, file_format="csv", mapping=mapping)

    assert "capacity_age0" in parsed.columns
    assert "capacity_age1" in parsed.columns
    assert parsed.loc[0, "capacity_age0"] == "0"
    assert parsed.loc[0, "capacity_age1"] == "2"


def test_parser_n_not_placeholder_when_followed_by_lowercase():
    """'N' の後に小文字英字が続く場合（例: 'No.'）はプレースホルダと見なさない。"""
    parser = InputParser()
    children = (
        "child_id,household_id,age,score_1,No.1,No.2,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,101,,\n"
    ).encode("utf-8")

    mapping = {"preference_prefix": "No."}
    parsed = parser.parse_children(file_bytes=children, file_format="csv", mapping=mapping)

    assert "pref_1" in parsed.columns
    assert "pref_2" in parsed.columns
    assert parsed.loc[0, "pref_1"] == "100"
    assert parsed.loc[0, "pref_2"] == "101"


def test_validate_unknown_daycare_error():
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,999,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("保育所ファイルに存在しない保育所ID" in e["message"] for e in result["errors"])


def test_match_tie_breaks_by_input_order_with_same_score():
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,,\n"
        "2,11,1,100,100,,\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["matching_result_dict"]["1"] == "100"
    assert result["matching_result_dict"]["2"] is None


def test_validate_rejects_inconsistent_sibling_pattern_in_same_household():
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,sibling_pattern,enrolled_daycare_id\n"
        "1,10,2,100,100,1,\n"
        "2,10,1,100,100,7,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("きょうだいパターン」が同一世帯内で一致しません" in e["message"] for e in result["errors"])


def test_validate_rejects_inf_sibling_pattern():
    """inf は有限整数ではないので reject する。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,sibling_pattern,enrolled_daycare_id\n"
        "1,10,1,100,100,inf,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("きょうだいパターン」列に無効な値" in e["message"] for e in result["errors"])


def test_validate_rejects_non_integer_sibling_pattern():
    """2.5 のような小数は整数 1〜7 の仕様外なので reject する。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,sibling_pattern,enrolled_daycare_id\n"
        "1,10,1,100,100,2.5,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("きょうだいパターン」列に無効な値" in e["message"] for e in result["errors"])


def test_validate_accepts_float_integer_sibling_pattern():
    """2.0 のように整数値を表す小数は 2 として受け入れる。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,sibling_pattern,enrolled_daycare_id\n"
        "1,10,1,100,100,2.0,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is True


def test_validate_treats_integer_and_float_integer_as_same_in_household():
    """同一世帯で 2 と 2.0 が混在しても一致とみなす（Excel由来の .0 対策）。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,sibling_pattern,enrolled_daycare_id\n"
        "1,10,2,100,100,2,\n"
        "2,10,1,100,100,2.0,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is True


def test_validate_rejects_non_integer_score():
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100.5,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("整数" in e["message"] for e in result["errors"])


def test_validate_accepts_float_integer_score():
    """pandas が NaN 起因で float64 化した '512200400.0' を整数として受理する。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,512200400.0,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is True


def test_validate_accepts_mixed_empty_and_float_integer_score():
    """空欄スコアと '.0' 付き整数スコアが同居する現実パターン（pandas が float64 化したり、
    Excel 由来データに '.0' が残ったりするケース）でも通る。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,score_2,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,512200400.0,,100,,\n"
        "2,20,1,512200400,512200400.0,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is True


def test_validate_accepts_negative_integer_float_score():
    """'-100.0' のように負の整数値を表す小数も受理する。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,-100.0,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is True


def test_validate_rejects_exponent_score():
    """'1.5e2' は parser の正規化対象外で matcher の int() も処理できないため拒否する。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,1.5e2,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("整数" in e["message"] for e in result["errors"])


def test_validate_rejects_score_with_precision_loss_decimal():
    """'10000000000000000.5' は float 精度で 1e16 に丸まり is_integer が True になるため、
    厳密 regex で拒否することを保証する。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,10000000000000000.5,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("整数" in e["message"] for e in result["errors"])


def test_validate_rejects_infinity_score():
    """'inf' は数値だが整数ではないため拒否する（is_integer は False、isfinite も False）。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,inf,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("整数" in e["message"] for e in result["errors"])


def test_validate_rejects_non_numeric_score():
    """'abc' のような非数値文字列は float() で ValueError になり拒否する。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,abc,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("整数" in e["message"] for e in result["errors"])


def test_validate_rejects_empty_score_1():
    """score_1 列に空欄行があれば EMPTY_SCORE_1 で弾く（matcher が silent に 0 として扱うのを防ぐ）。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,,\n"
        "2,20,1,,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any(e["code"] == ErrorCode.EMPTY_SCORE_1 for e in result["errors"])


@pytest.mark.parametrize(
    "score_1_cell",
    [
        '" "',  # quoted single space
        '"   "',  # quoted multi-space
        "   ",  # unquoted multi-space（pandas は skipinitialspace=False がデフォルトで保持）
        '"\t"',  # quoted tab
    ],
    ids=["quoted-single-space", "quoted-multi-space", "unquoted-multi-space", "quoted-tab"],
)
def test_validate_rejects_whitespace_only_score_1(score_1_cell: str):
    """score_1 が空白文字のみの行も空扱いで弾く（CSV 表記揺れに耐えること）。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,,\n"
        f"2,20,1,{score_1_cell},100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any(e["code"] == ErrorCode.EMPTY_SCORE_1 for e in result["errors"])


def test_validate_accepts_empty_score_2():
    """score_2 以降の空欄は現挙動どおり許容する（base_score フォールバック）。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,score_2,pref_1,pref_2,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,90,100,101,,\n"
        "2,20,1,200,,100,101,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is True


def test_validate_rejects_age_out_of_range():
    """age が 0〜5 以外なら INVALID_AGE_RANGE で弾く（CP ソルバの IndexError 予防）。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,7,100,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any(e["code"] == ErrorCode.INVALID_AGE_RANGE for e in result["errors"])


def test_validate_accepts_age_zero_and_five():
    """境界値 0 と 5 は許容されること。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,0,100,100,,\n"
        "2,20,5,100,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is True


def test_validate_rejects_duplicate_child_id():
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,,\n"
        "1,11,1,80,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("申請者番号」列に重複した値" in e["message"] for e in result["errors"])


def test_validate_rejects_duplicate_daycare_id():
    service = MatchingService()
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,A,0,1,0,0,0,0\n"
        "100,B,0,1,0,0,0,0\n"
    ).encode("utf-8")
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("保育所ID」列に重複した値" in e["message"] for e in result["errors"])


def test_match_whitespace_pref_treated_as_missing():
    """空白のみの pref セルは欠損として扱われ、KeyError を起こさない。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,pref_2,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,  ,,\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["matching_result_dict"]["1"] == "100"


def test_validate_rejects_missing_enrolled_daycare_id_column():
    """enrolled_daycare_id 列が無い場合は MISSING_CHILDREN_COLUMNS エラーになる。"""
    service = MatchingService()
    children = ("child_id,household_id,age,score_1,pref_1,sibling_pattern\n" "1,10,1,100,100,1\n").encode(
        "utf-8"
    )

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any(
        e["code"] == ErrorCode.MISSING_CHILDREN_COLUMNS and "在籍保育所ID" in e["message"]
        for e in result["errors"]
    )


def test_validate_rejects_missing_sibling_pattern_column():
    """sibling_pattern 列が無い場合は MISSING_CHILDREN_COLUMNS エラーになる。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id\n" "1,10,1,100,100,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any(
        e["code"] == ErrorCode.MISSING_CHILDREN_COLUMNS and "きょうだいパターン" in e["message"]
        for e in result["errors"]
    )


def test_validate_accepts_all_blank_required_columns_for_single_children():
    """両必須列があり全行空欄でも、単独児・転園なしならエラーにならない。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,,\n"
        "2,11,1,80,101,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is True
    assert result["errors"] == []


def test_validate_rejects_sibling_household_with_all_blank_sibling_pattern():
    """sibling_pattern列があり、きょうだい世帯（2人以上）の全行が空欄の場合はエラー。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,sibling_pattern,enrolled_daycare_id\n"
        "1,10,2,100,100,,\n"
        "2,10,1,100,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any(e["code"] == ErrorCode.SIBLING_PATTERN_BLANK_IN_HOUSEHOLD for e in result["errors"])


def test_validate_accepts_single_child_household_with_blank_sibling_pattern():
    """単独児世帯の sibling_pattern が空欄でもエラーにならない。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,sibling_pattern,enrolled_daycare_id\n"
        "1,10,1,100,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is True


def test_validate_rejects_empty_child_id():
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n" ",10,1,100,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("申請者番号」列に空の値" in e["message"] for e in result["errors"])


def test_validate_rejects_empty_household_id():
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n" "1,,1,100,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("世帯番号」列に空の値" in e["message"] for e in result["errors"])


def test_validate_rejects_blank_daycare_id():
    """空文字の daycare_id は弾く。負値や文字列IDはIDマッパーで安全に扱われるため許容する。"""
    service = MatchingService()
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "  ,A,0,1,0,0,0,0\n"
    ).encode("utf-8")
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("保育所ID」列に空の値" in e["message"] for e in result["errors"])


def test_validate_rejects_empty_daycare_id_cell():
    """CSV の空セル（NaN になる値）の daycare_id も弾く。"""
    service = MatchingService()
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        ",A,0,1,0,0,0,0\n"
    ).encode("utf-8")
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("保育所ID」列に空の値" in e["message"] for e in result["errors"])


def test_validate_rejects_empty_daycare_id_cell_in_excel():
    """Excel の空セル（daycare_id 未入力）も弾く。"""
    service = MatchingService()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(
        [
            "daycare_id",
            "daycare_name",
            "capacity_age0",
            "capacity_age1",
            "capacity_age2",
            "capacity_age3",
            "capacity_age4",
            "capacity_age5",
        ]
    )
    ws.append([None, "A", 0, 1, 0, 0, 0, 0])
    buffer = io.BytesIO()
    wb.save(buffer)
    daycares = buffer.getvalue()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="xlsx",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("保育所ID」列に空の値" in e["message"] for e in result["errors"])


def test_validate_rejects_unknown_enrolled_daycare_id():
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,999,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("保育所ファイルに存在しない保育所ID" in e["message"] for e in result["errors"])


# --- 転園希望者の無効な希望リストに対するバリデーションテスト ---


def test_transfer_child_empty_pref_value_fails_validation():
    """転園希望者でも pref_1 が空の場合はバリデーションエラーになること。

    転園希望者であっても pref_1 には少なくとも 1 件の有効な希望が必要である。
    在籍園フォールバック（IR）はマッチング内部の制約であり、
    入力データとして希望が全く入っていない状態はバリデーションで検出すべきエラーである。
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,,100,\n"  # enrolled at D1 (100), pref_1 is empty
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("希望保育所が1件も登録されていない" in e["message"] for e in result["errors"])


def test_transfer_child_pref_includes_enrolled_daycare_id_fails_validation():
    """転園希望者の pref に在籍園 ID が含まれる場合はバリデーションエラーになること。

    在籍園 ID を pref に含めることは意味的に冗長であり、
    転園希望者は IR 制約によりどのみち在籍園に戻れるため、
    ユーザーの混乱を防ぐためにバリデーションで弾く。
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,100,\n"  # pref_1 == enrolled_daycare_id
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("が希望列に含まれている" in e["message"] for e in result["errors"])


def test_transfer_child_pref2_includes_enrolled_daycare_id_fails_validation():
    """pref_2 に在籍園 ID が含まれる場合もバリデーションエラーになること。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,pref_2,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,101,100,100,\n"  # pref_2 == enrolled_daycare_id
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("が希望列に含まれている" in e["message"] for e in result["errors"])


def test_non_transfer_child_pref_same_as_any_daycare_passes_validation():
    """enrolled_daycare_id が空欄（新規申請者）の場合、pref に何を書いてもエラーにならないこと。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is True
    assert not any("が希望列に含まれている" in e["message"] for e in result["errors"])


def test_transfer_child_with_nan_enrolled_and_conflict_child_reports_only_conflict():
    """enrolled_daycare_id が NaN の行と conflict 行が混在する場合、conflict 行のみエラーになること。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,,\n"  # enrolled NaN → エラーにならない
        "2,20,1,100,100,100,\n"  # pref_1 == enrolled_daycare_id → エラー
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    error = next(e["message"] for e in result["errors"] if "が希望列に含まれている" in e["message"])
    assert "2" in error
    assert "1" not in error


def test_transfer_child_pref_float_matches_enrolled_int_fails_validation():
    """pandas が float 読みした ID（"100.0"）でも norm_id により conflict を検出できること。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100.0,100,\n"  # pref_1="100.0" → norm_id → "100" == enrolled "100"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("が希望列に含まれている" in e["message"] for e in result["errors"])


def test_family_pref_build_deduplicates_duplicate_pref_ids():
    """pref_1 == pref_2 の重複が FamilyPrefBuilder.build で除去されること。

    FamilyPrefBuilder._to_pref_list が重複 daycare_id を除去するため、
    family_pref には一意のエントリのみが含まれる。
    単一児童の family_pref は (daycare_id,) の 1-tuple のリストになる。
    """
    from chilmai.generic.family_pref_builder import FamilyPrefBuilder
    from chilmai.generic.parser import InputParser

    children_csv = (
        "child_id,household_id,age,score_1,pref_1,pref_2,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,101,101,100,\n"  # pref_1 == pref_2 (duplicate D2)
    ).encode("utf-8")

    parser = InputParser()
    children_df = parser.parse_children(
        file_bytes=children_csv,
        file_format="csv",
        mapping=DEFAULT_CONFIG["children"],
    )
    # matcher.py と同様に _input_order を付与してから build する
    children_df = children_df.reset_index(drop=False).rename(columns={"index": "_input_order"})
    households = FamilyPrefBuilder.build(children_df)

    assert len(households) == 1
    h = households[0]
    # 重複が除去された結果、101 は 1 回だけ現れる（単一児童 household の family_pref は (101,), (100,) のような 1-tuple）
    daycare_ids_in_pref = [combo[0] for combo in h.family_pref]
    assert daycare_ids_in_pref.count(101) == 1


def test_match_duplicate_pref_uses_first_occurrence_score():
    """pref_1 == pref_2 のとき、score は pref_1 のもの（earliest-win）が使われること。

    child1: score_1=100, score_2=0, pref_1=101, pref_2=101
    child2: score_1=50,             pref_1=101

    重複除去なし（後勝ち）だと child1 の score_lookup[(1,101)] == 0 になり
    child2 (score=50) が 101 に入ってしまう。
    earliest-win なら child1 (score=100) が 101 に入る。
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,score_2,pref_1,pref_2,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,0,101,101,,\n"  # duplicate pref; score_2=0 should be ignored
        "2,11,1,50,,101,,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "101,X,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["matching_result_dict"]["1"] == "101"
    assert result["matching_result_dict"]["2"] is None


def test_parser_maps_fullwidth_N_in_prefix():
    """prefix 設定値に全角 Ｎ が含まれていても score_1, score_2 に変換できること（P2）。"""
    parser = InputParser()
    children = (
        "child_id,household_id,age,スコア１,スコア２,pref_1,pref_2,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,90,100,101,,\n"
    ).encode("utf-8")
    mapping = {"score_prefix": "スコアＮ"}  # 全角Ｎ
    parsed = parser.parse_children(file_bytes=children, file_format="csv", mapping=mapping)

    assert "score_1" in parsed.columns
    assert "score_2" in parsed.columns
    assert parsed.loc[0, "score_1"] == "100"
    assert parsed.loc[0, "score_2"] == "90"


def test_match_fullwidth_child_id_column():
    """raw ファイルの全角列名（児童ＩＤ）と設定の半角列名（児童ID）が一致しても match が成功すること（P1）。"""
    service = MatchingService()
    # raw CSV の列名は全角ＩＤ、設定（read_columns 経由で保存）は NFKC 正規化後の半角
    children = (
        "児童ＩＤ,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,,\n"
    ).encode("utf-8")
    mapping = {
        "children": {
            "child_id": "児童ID",
            "household_id": "household_id",
            "age": "age",
            "score_prefix": "score_",
            "preference_prefix": "pref_",
        },
        "daycares": {
            "daycare_id": "daycare_id",
            "daycare_name": "daycare_name",
            "capacity_prefix": "capacity_age",
        },
        "output": {
            "result_daycare_id": "入所選考結果保育所ID",
            "result_daycare_name": "入所選考結果保育所名",
        },
    }
    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=mapping,
    )

    assert "matching_result_dict" in result
    assert "1" in result["matching_result_dict"]
    # 元ファイルの全角列名が出力でも保持されること（NFKC 変換されていないこと）
    assert "児童ＩＤ" in result["output_columns"]
    assert "児童ID" not in result["output_columns"]


def test_parser_raises_on_duplicate_columns_after_normalization():
    """全角・半角混在列（希望1 と 希望１）が正規化後に重複する場合 ValueError を送出すること。"""
    import pytest

    parser = InputParser()
    # "希望1"（半角）と "希望１"（全角）が共存 → NFKC 後に両方 "希望1" になる
    children = ("child_id,希望1,希望１\n" "1,100,101\n").encode("utf-8")
    with pytest.raises(ValueError, match="重複"):
        parser.parse_children(file_bytes=children, file_format="csv", mapping={})


def test_parser_renames_bare_score_to_score_1():
    """「score」列（suffix なし）が単独で存在する場合、「score_1」にリネームして処理続行すること。"""
    parser = InputParser()
    children = (
        "child_id,household_id,age,score,pref_1,enrolled_daycare_id,sibling_pattern\n" "1,10,1,100,999,,\n"
    ).encode("utf-8")
    parsed = parser.parse_children(file_bytes=children, file_format="csv", mapping={})
    assert "score_1" in parsed.columns
    assert "score" not in parsed.columns
    assert parsed.loc[0, "score_1"] == "100"


def test_parser_raises_when_score_and_score_1_both_exist():
    """「score」と「score_1」が両方存在する場合 ValueError を送出すること。"""
    import pytest

    parser = InputParser()
    children = (
        "child_id,household_id,age,score,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,999,,\n"
    ).encode("utf-8")
    with pytest.raises(ValueError, match="score_1"):
        parser.parse_children(file_bytes=children, file_format="csv", mapping={})


def test_parser_raises_when_score_and_score_2_exist_without_score_1():
    """「score」と「score_2」が存在し「score_1」がない場合 ValueError を送出すること。"""
    import pytest

    parser = InputParser()
    children = (
        "child_id,household_id,age,score,score_2,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,90,999,,\n"
    ).encode("utf-8")
    with pytest.raises(ValueError, match="score"):
        parser.parse_children(file_bytes=children, file_format="csv", mapping={})


def test_parser_renames_mapped_score_column_to_score_1():
    """「score」キーで日本語列名（例: 点数）をマッピングすると score_1 として扱われること。"""
    parser = InputParser()
    children = (
        "child_id,household_id,age,点数,pref_1,enrolled_daycare_id,sibling_pattern\n" "1,10,1,100,999,,\n"
    ).encode("utf-8")
    parsed = parser.parse_children(file_bytes=children, file_format="csv", mapping={"score": "点数"})
    assert "score_1" in parsed.columns
    assert "score" not in parsed.columns
    assert "点数" not in parsed.columns
    assert parsed.loc[0, "score_1"] == "100"


def test_display_col_uses_score_mapping_for_score_1():
    """score マッピングが設定されている場合、score_1 の表示名に mapping["score"] を使うこと。"""
    from chilmai.generic.validator import ValidationService

    svc = ValidationService()
    mapping = {"score": "点数", "score_prefix": "スコアN"}
    assert svc._display_col("score_1", mapping) == "点数"
    assert svc._display_col("score_2", mapping) == "スコア2"


def test_column_aliases_detects_bare_score_column():
    """column_aliases.json に score キーが存在し、「点数」列が score として検出されること。"""
    from chilmai.generic.column_mapper import detect_section
    from chilmai.generic.config import DEFAULT_CONFIG

    suggestions = detect_section(["点数", "pref_1"], "children", DEFAULT_CONFIG["children"])
    keys = [s.internal_key for s in suggestions]
    assert "score" in keys


def test_validate_accepts_16digit_score():
    """16桁のスコアがバリデーションを通過すること（15桁制限の解消確認）。"""
    service = MatchingService()
    score_16 = "1234567890123456"
    children = (
        f"child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        f"1,10,1,{score_16},100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is True


def test_validate_accepts_float_string_score():
    """'100.0' のように整数値を表す小数文字列はスコアとして受理する。

    pandas は CSV 列に NaN（空欄）が含まれると列全体を float64 化するため、
    整数だった値が '.0' 付きの文字列で読み込まれる。これを弾くと通常 CSV が
    ほぼ受け付けられなくなるため、整数値を表す小数は許容する。
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100.0,100,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is True


# ── エラーコード体系のテスト ────────────────────────────────────────────────────


def test_parser_raises_chilmerror_with_code_for_unsupported_format():
    """非対応ファイル形式で ChilmError が code=401 付きで送出されること。"""
    import pytest
    from chilmai.generic.error_codes import ChilmError, ErrorCode

    parser = InputParser()
    with pytest.raises(ChilmError) as exc_info:
        parser.parse_children(file_bytes=b"dummy", file_format="xml", mapping={})
    assert exc_info.value.code == ErrorCode.UNSUPPORTED_FILE_FORMAT


def test_chilmerror_is_caught_as_value_error():
    """ChilmError は ValueError として捕捉できること（後方互換）。"""
    import pytest

    parser = InputParser()
    with pytest.raises(ValueError):
        parser.parse_children(file_bytes=b"dummy", file_format="xml", mapping={})


def test_parse_children_raises_chilmerror_with_code_for_shiftjis_csv():
    """Shift-JIS の CSV を parse_children で読むと code=405 の ChilmError になること。"""
    from chilmai.generic.error_codes import ChilmError, ErrorCode

    # Excel 既定の「CSV (コンマ区切り)」保存を模した Shift-JIS (cp932) バイト列。
    shiftjis_csv = "児童ID,年齢,score_1,pref_1\n1,2,100,100\n".encode("cp932")
    parser = InputParser()
    with pytest.raises(ChilmError) as exc_info:
        parser.parse_children(
            file_bytes=shiftjis_csv, file_format="csv", mapping=DEFAULT_CONFIG["children"]
        )
    assert exc_info.value.code == ErrorCode.CSV_ENCODING_ERROR


def test_read_columns_raises_chilmerror_with_code_for_shiftjis_csv():
    """Shift-JIS の CSV を read_columns で読むと code=405 の ChilmError になること。"""
    from chilmai.generic.error_codes import ChilmError, ErrorCode

    shiftjis_csv = "児童ID,希望1,希望2\n1,100,101\n".encode("cp932")
    parser = InputParser()
    with pytest.raises(ChilmError) as exc_info:
        parser.read_columns(io.BytesIO(shiftjis_csv), "csv")
    assert exc_info.value.code == ErrorCode.CSV_ENCODING_ERROR


def test_utf8_csv_still_reads_after_encoding_guard():
    """UTF-8 の CSV は従来どおり問題なく読めること（エンコーディング判定の巻き込み回帰防止）。"""
    utf8_csv = "児童ID,希望1,希望2\n1,100,101\n".encode("utf-8")
    parser = InputParser()
    cols = parser.read_columns(io.BytesIO(utf8_csv), "csv")
    assert "児童ID" in cols


def test_validator_error_dicts_contain_code_field():
    """バリデーションエラーの各 dict に整数の code フィールドが含まれること。"""
    from chilmai.generic.error_codes import ErrorCode

    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,999,,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    for e in result["errors"]:
        assert "code" in e, f"code フィールドがない: {e}"
        assert isinstance(e["code"], int), f"code が int でない: {e['code']!r}"
    unknown_pref = next(e for e in result["errors"] if "保育所ファイルに存在しない保育所ID" in e["message"])
    assert unknown_pref["code"] == ErrorCode.UNKNOWN_DAYCARE_IN_PREF


# ---------------------------------------------------------------------------
# 任意きょうだい組み合わせ（別ファイル方式 / combination_df）
# ---------------------------------------------------------------------------


def _combination_csv() -> bytes:
    return (
        "ファミリーコード,総当たり順位,宛名コード1,宛名コード2,希望施設1,希望施設2\n"
        "10,1,1,2,100,101\n"
        "10,2,1,2,101,100\n"
    ).encode("utf-8")


def test_parse_combination_basic():
    """デフォルトマッピングで CSV を正しく内部列名に変換する。"""
    from chilmai.generic.config import DEFAULT_CONFIG

    parser = InputParser()
    combo = _combination_csv()
    parsed = parser.parse_combination(
        file_bytes=combo,
        file_format="csv",
        mapping=DEFAULT_CONFIG["combination"],
    )
    assert "household_id" in parsed.columns
    assert "rank" in parsed.columns
    assert "child_code_0" in parsed.columns
    assert "child_code_1" in parsed.columns
    assert "facility_0" in parsed.columns
    assert "facility_1" in parsed.columns
    assert parsed.loc[0, "household_id"] == "10"
    assert parsed.loc[0, "rank"] == "1"
    assert parsed.loc[0, "child_code_0"] == "1"
    assert parsed.loc[0, "facility_0"] == "100"


def test_parse_combination_japanese_prefix():
    """日本語テンプレートで child_code / facility 列を内部名に変換できる。"""
    parser = InputParser()
    combo = (
        "ファミリーコード,総当たり順位,宛名コード1,宛名コード2,希望施設1,希望施設2\n" "10,1,1,2,100,101\n"
    ).encode("utf-8")
    mapping = {
        "household_id": "ファミリーコード",
        "rank": "総当たり順位",
        "child_code_prefix": "宛名コードN",
        "facility_prefix": "希望施設N",
    }
    parsed = parser.parse_combination(file_bytes=combo, file_format="csv", mapping=mapping)
    assert "child_code_0" in parsed.columns
    assert "facility_0" in parsed.columns


def test_parse_combination_empty_cells_stay_nan():
    """空欄の facility セルが NaN のまま保持される。"""
    from chilmai.generic.config import DEFAULT_CONFIG

    parser = InputParser()
    combo = (
        "ファミリーコード,総当たり順位,宛名コード1,宛名コード2,希望施設1,希望施設2\n" "10,1,1,2,100,\n"
    ).encode("utf-8")
    parsed = parser.parse_combination(
        file_bytes=combo,
        file_format="csv",
        mapping=DEFAULT_CONFIG["combination"],
    )
    import pandas as pd

    assert pd.isna(parsed.loc[0, "facility_1"])


def test_validate_with_combination_file_valid():
    """有効な組み合わせファイルがあれば is_valid=True。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,2,100,100,,\n"
        "2,10,1,100,101,,\n"
        "3,11,1,80,101,,\n"
    ).encode("utf-8")
    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
        combination_file_bytes=_combination_csv(),
        combination_file_format="csv",
    )
    assert result["is_valid"] is True


def test_validate_rejects_combination_unknown_household():
    """組み合わせファイルに存在しない世帯ID → COMBINATION_UNKNOWN_HOUSEHOLD エラー。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,2,100,100,,\n"
        "2,10,1,100,101,,\n"
    ).encode("utf-8")
    combo = (
        "ファミリーコード,総当たり順位,宛名コード1,宛名コード2,希望施設1,希望施設2\n" "99,1,1,2,100,101\n"
    ).encode("utf-8")
    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
        combination_file_bytes=combo,
        combination_file_format="csv",
    )
    assert result["is_valid"] is False
    assert any(e["code"] == ErrorCode.COMBINATION_UNKNOWN_HOUSEHOLD for e in result["errors"])


def test_validate_rejects_combination_unknown_child_code():
    """組み合わせファイルに存在しない child_id → COMBINATION_UNKNOWN_CHILD_CODE エラー。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,2,100,100,,\n"
        "2,10,1,100,101,,\n"
    ).encode("utf-8")
    combo = (
        "ファミリーコード,総当たり順位,宛名コード1,宛名コード2,希望施設1,希望施設2\n" "10,1,1,99,100,101\n"
    ).encode("utf-8")
    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
        combination_file_bytes=combo,
        combination_file_format="csv",
    )
    assert result["is_valid"] is False
    assert any(e["code"] == ErrorCode.COMBINATION_UNKNOWN_CHILD_CODE for e in result["errors"])


def test_validate_rejects_combination_child_code_from_wrong_household():
    """組み合わせ行の child_code が当該世帯以外の子どもを指す場合 COMBINATION_UNKNOWN_CHILD_CODE になること。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,2,100,100,,\n"
        "2,10,1,100,101,,\n"
        "3,11,1,80,100,,\n"  # child 3 は世帯 11 に属する
    ).encode("utf-8")
    # 世帯 10 の組み合わせ行に、世帯 11 の child 3 を混入させる
    combo = (
        "ファミリーコード,総当たり順位,宛名コード1,宛名コード2,希望施設1,希望施設2\n" "10,1,1,3,100,101\n"
    ).encode("utf-8")
    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
        combination_file_bytes=combo,
        combination_file_format="csv",
    )
    assert result["is_valid"] is False
    assert any(e["code"] == ErrorCode.COMBINATION_UNKNOWN_CHILD_CODE for e in result["errors"])


def test_match_applies_combination_file():
    """組み合わせファイルが実際にマッチングへ適用されること（ID正規化の回帰テスト）。

    sibling_pattern=1 は「同所・同月（両児同一保育所）」のため、正しく適用された場合は
    組み合わせファイルで指定した「別々の保育所」への割り当てになる。
    組み合わせファイルが無視されると同一保育所になり、このアサートが失敗する。
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,pref_2,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,101,,\n"  # 世帯 10・組み合わせファイル対象（sibling_pattern 空欄）
        "2,10,1,80,101,100,,\n"
        "3,11,1,90,100,,,\n"  # 世帯 11・単独児
    ).encode("utf-8")
    # rank1: child1→100, child2→101（別々の保育所）
    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
        combination_file_bytes=_combination_csv(),
        combination_file_format="csv",
    )
    rd = result["matching_result_dict"]
    # 組み合わせファイルが適用されていれば child 1 と child 2 は異なる保育所に割り当てられる
    assert rd.get("1") is not None
    assert rd.get("2") is not None
    assert rd.get("1") != rd.get("2")


# --- きょうだい同保パターン × 共通希望施設の整合性チェック ---


def test_validate_rejects_sibling_pattern1_without_common_preference():
    """パターン1（同保同時）できょうだい間に共通希望施設がない場合はエラー。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,sibling_pattern,enrolled_daycare_id\n"
        "1,10,2,100,100,1,\n"
        "2,10,1,100,101,1,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any(e["code"] == ErrorCode.SIBLING_NO_COMMON_PREFERENCE for e in result["errors"])


def test_validate_rejects_sibling_pattern2_without_common_preference():
    """パターン2（同保・上の子優先）で共通希望施設がない場合は年下が対象外になる旨のエラー。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,sibling_pattern,enrolled_daycare_id\n"
        "1,10,2,100,100,2,\n"
        "2,10,1,100,101,2,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    msgs = [e["message"] for e in result["errors"] if e["code"] == ErrorCode.SIBLING_NO_COMMON_PREFERENCE]
    assert msgs and "年下" in msgs[0]


def test_validate_rejects_sibling_pattern3_without_common_preference():
    """パターン3（同保・下の子優先）で共通希望施設がない場合は年上が対象外になる旨のエラー。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,sibling_pattern,enrolled_daycare_id\n"
        "1,10,2,100,100,3,\n"
        "2,10,1,100,101,3,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    msgs = [e["message"] for e in result["errors"] if e["code"] == ErrorCode.SIBLING_NO_COMMON_PREFERENCE]
    assert msgs and "年上" in msgs[0]


def test_validate_accepts_sibling_pattern1_with_common_preference():
    """パターン1でも共通希望施設があればエラーにしない。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,pref_2,sibling_pattern,enrolled_daycare_id\n"
        "1,10,2,100,100,101,1,\n"
        "2,10,1,100,101,,1,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is True
    assert not any(e["code"] == ErrorCode.SIBLING_NO_COMMON_PREFERENCE for e in result["errors"])


def test_validate_accepts_separate_daycare_pattern_without_common_preference():
    """別保系パターン（5）は共通希望施設が無くてもエラーにしない。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,sibling_pattern,enrolled_daycare_id\n"
        "1,10,2,100,100,5,\n"
        "2,10,1,100,101,5,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is True
    assert not any(e["code"] == ErrorCode.SIBLING_NO_COMMON_PREFERENCE for e in result["errors"])


def test_validate_skips_sibling_common_pref_for_combination_household():
    """組み合わせファイル掲載世帯は family_pref を直接生成するため Rule 2 の対象外。"""
    import pandas as pd

    from chilmai.generic.validator import ValidationService

    children_df = pd.DataFrame(
        {
            "child_id": [1, 2],
            "household_id": [10, 10],
            "age": [2, 1],
            "enrolled_daycare_id": [None, None],
            "sibling_pattern": [1, 1],
            "score_1": [100, 100],
            "pref_1": [100, 101],  # 共通希望なし
        }
    )
    daycares_df = pd.DataFrame(
        {
            "daycare_id": [100, 101],
            "daycare_name": ["A", "B"],
            "capacity_age0": [1, 1],
            "capacity_age1": [1, 1],
            "capacity_age2": [1, 1],
            "capacity_age3": [0, 0],
            "capacity_age4": [0, 0],
            "capacity_age5": [0, 0],
        }
    )
    combination_df = pd.DataFrame(
        {
            "household_id": [10],
            "rank": [1],
            "child_code_1": [1],
            "child_code_2": [2],
            "facility_1": [100],
            "facility_2": [101],
        }
    )

    result = ValidationService().validate(children_df, daycares_df, combination_df=combination_df)

    assert not any(e["code"] == ErrorCode.SIBLING_NO_COMMON_PREFERENCE for e in result["errors"])


def test_validate_does_not_raise_on_non_numeric_pref_in_sibling_household():
    """同保系きょうだい世帯に非数値の希望ID（例：'ABC'）があっても、
    共通希望施設チェックは例外で落ちず UNKNOWN_DAYCARE_IN_PREF を返すこと（回帰）。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,sibling_pattern,enrolled_daycare_id\n"
        "1,10,2,100,100,1,\n"
        "2,10,1,100,ABC,1,\n"
    ).encode("utf-8")

    # 修正前は ValidationService._validate_sibling_common_preferences が
    # int(pd.to_numeric('ABC')) で ValueError を投げ、validate() が 500 相当で落ちていた。
    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any(e["code"] == ErrorCode.UNKNOWN_DAYCARE_IN_PREF for e in result["errors"])


def test_validate_out_of_range_sibling_pattern_does_not_emit_common_pref_error():
    """範囲外の sibling_pattern（例：8）は INVALID_SIBLING_PATTERN のみを報告し、
    パターン1 へのフォールバックに由来する誤った SIBLING_NO_COMMON_PREFERENCE を出さないこと。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,sibling_pattern,enrolled_daycare_id\n"
        "1,10,2,100,100,8,\n"
        "2,10,1,100,101,8,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any(e["code"] == ErrorCode.INVALID_SIBLING_PATTERN for e in result["errors"])
    assert not any(e["code"] == ErrorCode.SIBLING_NO_COMMON_PREFERENCE for e in result["errors"])


def test_validate_non_numeric_sibling_pattern_does_not_emit_common_pref_error():
    """非数値の sibling_pattern（例：'abc'）が世帯内で揃っていても、
    INVALID_SIBLING_PATTERN のみを報告し SIBLING_NO_COMMON_PREFERENCE は出さないこと。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,sibling_pattern,enrolled_daycare_id\n"
        "1,10,2,100,100,abc,\n"
        "2,10,1,100,101,abc,\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any(e["code"] == ErrorCode.INVALID_SIBLING_PATTERN for e in result["errors"])
    assert not any(e["code"] == ErrorCode.SIBLING_NO_COMMON_PREFERENCE for e in result["errors"])
