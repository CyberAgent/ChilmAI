"""
匿名化済み大規模サンプルデータを使ったマッチング統合テスト。

データファイルは test/data/municipal/ にローカルで配置してください。

期待値:
    2024: 申込者 1376 名、マッチ 1080 名
    2025: 申込者 1376 名、マッチ 1080 名
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pytest

from chilmai.generic.matcher import norm_id
from chilmai.generic.parser import InputParser
from chilmai.generic.service import MatchingService

DATA_DIR = Path(__file__).resolve().parents[3] / "test" / "data" / "municipal"

MAPPING = {
    "children": {
        "child_id": "child_id",
        "household_id": "household_id",
        "age": "age",
        "score_prefix": "score_",
        "preference_prefix": "pref_",
        "enrolled_daycare_id": "enrolled_daycare_id",
        "sibling_pattern": "sibling_pattern",
    },
    "daycares": {
        "daycare_id": "daycare_id",
        "daycare_name": "daycare_name",
        "capacity_prefix": "capacity_age",
    },
}

# (label, children_csv, daycares_csv, expected_total, expected_matched)
_DATASETS = [
    (
        "2024",
        DATA_DIR / "children_2024.csv",
        DATA_DIR / "daycares_2024.csv",
        1376,
        1080,
    ),
    (
        "2025",
        DATA_DIR / "children_2025.csv",
        DATA_DIR / "daycares_2025.csv",
        1376,
        1080,
    ),
]

_AVAILABLE = [d for d in _DATASETS if d[1].exists() and d[2].exists()]


@pytest.mark.parametrize(
    "label,children_path,daycares_path,expected_total,expected_matched",
    _AVAILABLE,
    ids=[d[0] for d in _AVAILABLE],
)
def test_municipal_large_sample_validates(
    label: str,
    children_path: Path,
    daycares_path: Path,
    expected_total: int,
    expected_matched: int,
) -> None:
    service = MatchingService()
    result = service.validate(
        children_file_bytes=children_path.read_bytes(),
        children_file_format="csv",
        daycares_file_bytes=daycares_path.read_bytes(),
        daycares_file_format="csv",
        mapping=MAPPING,
    )
    assert result["is_valid"] is True, f"[{label}] Validation errors: {result['errors']}"


@pytest.mark.parametrize(
    "label,children_path,daycares_path,expected_total,expected_matched",
    _AVAILABLE,
    ids=[d[0] for d in _AVAILABLE],
)
def test_municipal_large_sample_matches(
    label: str,
    children_path: Path,
    daycares_path: Path,
    expected_total: int,
    expected_matched: int,
) -> None:
    children_bytes = children_path.read_bytes()
    daycares_bytes = daycares_path.read_bytes()

    service = MatchingService()
    result = service.match(
        children_file_bytes=children_bytes,
        children_file_format="csv",
        daycares_file_bytes=daycares_bytes,
        daycares_file_format="csv",
        mapping=MAPPING,
    )

    assert result["meta"]["algorithm"] == "cp_use_transfer"

    parser = InputParser()
    children_df = parser.parse_children(
        file_bytes=children_bytes,
        file_format="csv",
        mapping=MAPPING["children"],
    )
    daycares_df = parser.parse_daycares(
        file_bytes=daycares_bytes,
        file_format="csv",
        mapping=MAPPING["daycares"],
    )

    matching = result["matching_result_dict"]

    assert (
        len(matching) == expected_total
    ), f"[{label}] 申込者数: expected {expected_total}, got {len(matching)}"
    matched_count = sum(1 for v in matching.values() if v is not None)
    assert (
        matched_count == expected_matched
    ), f"[{label}] マッチ数: expected {expected_matched}, got {matched_count}"

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

    transfer_out: dict[tuple[str, int], int] = defaultdict(int)
    for c_id, enrolled in child_enrolled.items():
        if enrolled is not None:
            transfer_out[(enrolled, child_age[c_id])] += 1

    effective_capacity: dict[tuple[str, int], int] = {}
    for _, row in daycares_df.iterrows():
        d_id = norm_id(str(row["daycare_id"]))
        for age in range(6):
            base = int(pd.to_numeric(row[f"capacity_age{age}"]))
            effective_capacity[(d_id, age)] = base + transfer_out.get((d_id, age), 0)

    assignment_counts: dict[tuple[str, int], int] = defaultdict(int)
    for child_id, daycare_id in matching.items():
        if daycare_id is None:
            continue
        c_id = str(child_id)
        assignment_counts[(str(daycare_id), child_age[c_id])] += 1

    for (d_id, age), count in assignment_counts.items():
        cap = effective_capacity.get((d_id, age), 0)
        assert (
            count <= cap
        ), f"[{label}] daycare {d_id} age {age}: assigned {count} > effective capacity {cap}"

    for child_id, daycare_id in matching.items():
        if daycare_id is None:
            continue
        c_id = str(child_id)
        d_id = str(daycare_id)
        allowed = child_pref[c_id] | ({child_enrolled[c_id]} if child_enrolled[c_id] else set())
        assert d_id in allowed, (
            f"[{label}] child {c_id} assigned to {d_id}, " "not in pref list or enrolled daycare"
        )
