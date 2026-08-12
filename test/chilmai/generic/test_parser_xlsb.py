"""`.xlsb` を calamine エンジンで読み込めることを保証する回帰テスト。

pyxlsb（LGPLv3）から python-calamine（MIT）へ置き換えた際、`.xlsb` は
calamine を明示指定して読む必要がある。calamine も pandas も `.xlsb`
書き出しをサポートしないため、テスト内で round-trip を生成できない。そこで
`test/data/xlsb/children_small.xlsb` にバイナリのフィクスチャをコミットし、
それを実際のパーサー経由で読み取ることで、engine 指定と dtype 維持が
壊れていないことを検証する。
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest

from chilmai.generic.config import DEFAULT_CONFIG
from chilmai.generic.parser import InputParser

FIXTURE = Path(__file__).resolve().parents[3] / "test" / "data" / "xlsb" / "children_small.xlsb"

pytestmark = pytest.mark.skipif(not FIXTURE.exists(), reason=f"xlsb fixture not found: {FIXTURE}")


def _fixture_bytes() -> bytes:
    return FIXTURE.read_bytes()


def test_read_columns_reads_xlsb_headers() -> None:
    """read_columns が calamine 経由で xlsb のヘッダ（日本語含む）を読めること。"""
    parser = InputParser()
    cols = parser.read_columns(io.BytesIO(_fixture_bytes()), "xlsb")

    assert cols == [
        "申請者番号",
        "世帯番号",
        "年齢",
        "点数1",
        "点数2",
        "希望保育園ID_1",
        "希望保育園ID_2",
        "在籍保育所ID",
        "きょうだいパターン",
    ]


def test_parse_children_maps_xlsb_to_internal_columns() -> None:
    """xlsb を parse_children で読み、日本語列が内部列へ正しく変換されること。"""
    parser = InputParser()
    parsed = parser.parse_children(
        file_bytes=_fixture_bytes(),
        file_format="xlsb",
        mapping=DEFAULT_CONFIG["children"],
    )

    assert list(parsed.columns) == [
        "child_id",
        "household_id",
        "age",
        "score_1",
        "score_2",
        "pref_1",
        "pref_2",
        "enrolled_daycare_id",
        "sibling_pattern",
    ]
    assert parsed.shape == (2, 9)


def test_parse_children_xlsb_preserves_string_values() -> None:
    """dtype=str が効いており、先頭ゼロ（"007"）が数値化されず保持されること。"""
    parser = InputParser()
    parsed = parser.parse_children(
        file_bytes=_fixture_bytes(),
        file_format="xlsb",
        mapping=DEFAULT_CONFIG["children"],
    )

    # 数値に見える ID も文字列のまま（int 化されない）。
    assert parsed["child_id"].iloc[0] == "101"
    assert parsed["score_1"].iloc[0] == "100"
    # 先頭ゼロが失われていないこと（calamine + dtype=str の要）。
    assert parsed["enrolled_daycare_id"].iloc[0] == "007"


def test_parse_children_xlsb_keeps_empty_cells_as_nan() -> None:
    """空セルは NaN として読み込まれること。"""
    parser = InputParser()
    parsed = parser.parse_children(
        file_bytes=_fixture_bytes(),
        file_format="xlsb",
        mapping=DEFAULT_CONFIG["children"],
    )

    assert pd.isna(parsed["sibling_pattern"].iloc[0])  # 1 行目 きょうだいパターン 空
    assert parsed["sibling_pattern"].iloc[1] == "1"
    assert pd.isna(parsed["enrolled_daycare_id"].iloc[1])  # 2 行目 在籍保育所ID 空
