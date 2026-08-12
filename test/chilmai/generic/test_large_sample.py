from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pytest

from chilmai.generic.matcher import norm_id
from chilmai.generic.parser import InputParser
from chilmai.generic.service import MatchingService

DATA_DIR = Path(__file__).resolve().parents[3] / "test" / "data" / "e2e"
CHILDREN_PATH = DATA_DIR / "children_large_sample.csv"
DAYCARES_PATH = DATA_DIR / "daycares_large_sample.csv"

pytestmark = pytest.mark.skipif(
    not (CHILDREN_PATH.exists() and DAYCARES_PATH.exists()),
    reason="large sample data not available",
)

JP_MAPPING = {
    "children": {
        "child_id": "児童ID",
        "household_id": "世帯ID",
        "age": "年齢",
        "score_prefix": "スコア",
        "preference_prefix": "希望",
        "enrolled_daycare_id": "在籍保育所ID",
        "sibling_pattern": "きょうだいパターン",
    },
    "daycares": {
        "daycare_id": "保育所ID",
        "daycare_name": "保育所名",
        "capacity_prefix": "N歳定員",
    },
}


def test_large_sample_validates():
    service = MatchingService()
    result = service.validate(
        children_file_bytes=CHILDREN_PATH.read_bytes(),
        children_file_format="csv",
        daycares_file_bytes=DAYCARES_PATH.read_bytes(),
        daycares_file_format="csv",
        mapping=JP_MAPPING,
    )
    assert result["is_valid"] is True
    assert result["errors"] == []


def test_large_sample_matches():
    children_bytes = CHILDREN_PATH.read_bytes()
    daycares_bytes = DAYCARES_PATH.read_bytes()

    service = MatchingService()
    result = service.match(
        children_file_bytes=children_bytes,
        children_file_format="csv",
        daycares_file_bytes=daycares_bytes,
        daycares_file_format="csv",
        mapping=JP_MAPPING,
    )
    assert result["meta"]["algorithm"] == "cp_use_transfer"
    assert result["matched_children"]["total"] > 0

    parser = InputParser()
    children_df = parser.parse_children(
        file_bytes=children_bytes,
        file_format="csv",
        mapping=JP_MAPPING["children"],
    )
    daycares_df = parser.parse_daycares(
        file_bytes=daycares_bytes,
        file_format="csv",
        mapping=JP_MAPPING["daycares"],
    )

    matching = result["matching_result_dict"]

    # 児童ごとの年齢・転園元・希望リストを一括構築
    pref_cols = sorted(
        [c for c in children_df.columns if re.fullmatch(r"pref_\d+", c)],
        key=lambda c: int(c.split("_")[1]),
    )
    child_age: dict[str, int] = {}
    child_enrolled: dict[str, str | None] = {}
    child_pref: dict[str, set[str]] = {}
    for _, row in children_df.iterrows():
        c_id = norm_id(str(row["child_id"]))
        child_age[c_id] = int(row["age"])
        enrolled = row.get("enrolled_daycare_id")
        child_enrolled[c_id] = (
            norm_id(str(enrolled)) if pd.notna(enrolled) and norm_id(str(enrolled)) != "" else None
        )
        child_pref[c_id] = {
            norm_id(str(row[col]))
            for col in pref_cols
            if pd.notna(row[col]) and norm_id(str(row[col])) != ""
        }

    # --- 1. 定員超過なし（転園アウト数による定員増加を考慮） ---
    # 転園アウト数: enrolled_daycare_id を持つ児童が退所する (daycare_id, age) ごとのカウント
    transfer_out: dict[tuple[str, int], int] = defaultdict(int)
    for c_id, enrolled in child_enrolled.items():
        if enrolled is not None:
            transfer_out[(enrolled, child_age[c_id])] += 1

    # 有効定員: capacity_age{A} + transfer_out_count（転園元保育所の空き枠が増える）
    effective_capacity: dict[tuple[str, int], int] = {}
    for _, row in daycares_df.iterrows():
        d_id = norm_id(str(row["daycare_id"]))
        for age in range(6):
            base = int(pd.to_numeric(row[f"capacity_age{age}"]))
            effective_capacity[(d_id, age)] = base + transfer_out.get((d_id, age), 0)

    # 割り当て数を集計（転園元に戻った児童も含む）
    assignment_counts: dict[tuple[str, int], int] = defaultdict(int)
    for child_id, daycare_id in matching.items():
        if daycare_id is None:
            continue
        c_id = str(child_id)
        assignment_counts[(str(daycare_id), child_age[c_id])] += 1

    for (d_id, age), count in assignment_counts.items():
        cap = effective_capacity.get((d_id, age), 0)
        assert count <= cap, f"daycare {d_id} age {age}: assigned {count} > effective capacity {cap}"

    # --- 2. 割り当て先が希望リスト内または転園元 ---
    for child_id, daycare_id in matching.items():
        if daycare_id is None:
            continue
        c_id = str(child_id)
        d_id = str(daycare_id)
        allowed = child_pref[c_id] | ({child_enrolled[c_id]} if child_enrolled[c_id] else set())
        assert d_id in allowed, f"child {c_id} assigned to {d_id}, not in pref list or enrolled daycare"
