"""マッチング結果のスナップショット回帰テスト。

アルゴリズム変更によってマッチング結果が意図せず変化した場合に検知するため、
固定入力に対する期待結果をハードコードして比較する。
"""

from __future__ import annotations

from chilmai.generic.config import DEFAULT_CONFIG
from chilmai.generic.service import MatchingService

# ---------------------------------------------------------------------------
# 固定テストデータ（test_match_cp_sat_default と同一入力）
# ---------------------------------------------------------------------------

_CHILDREN_CSV = (
    "child_id,household_id,age,score_1,pref_1,pref_2,enrolled_daycare_id,sibling_pattern\n"
    "1,10,1,100,100,101,,\n"
    "2,11,1,80,100,101,,1\n"
    "3,11,1,80,101,100,,1\n"
).encode("utf-8")

_DAYCARES_CSV = (
    "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
    "100,A,0,1,0,0,0,0\n"
    "101,B,0,1,0,0,0,0\n"
).encode("utf-8")

# ---------------------------------------------------------------------------
# 既知の正しい結果（スナップショット）
# child 1 (score 100, household 10) takes D100 (top pref).
# children 2 & 3 (score 80, household 11): sibling_pattern=1 (same_simultaneous).
# D100 and D101 each have capacity 1 for age 1; no daycare can accommodate both
# siblings → both unmatched.
# ---------------------------------------------------------------------------
_EXPECTED_MATCHING: dict[str, str | None] = {
    "1": "100",
    "2": None,
    "3": None,
}
_EXPECTED_TOTAL = 1


def test_snapshot_matching_result_is_stable():
    """固定入力に対して常に同じマッチング結果が返ること（アルゴリズム回帰検知）。

    このテストが失敗した場合、アルゴリズムまたはデータ処理の変更が
    意図せず結果を変えた可能性がある。
    """
    service = MatchingService()
    result = service.match(
        children_file_bytes=_CHILDREN_CSV,
        children_file_format="csv",
        daycares_file_bytes=_DAYCARES_CSV,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["matching_result_dict"] == _EXPECTED_MATCHING


def test_snapshot_matched_count_is_exact():
    """コード変更後もマッチング数が既知の値と完全に一致すること。

    増加・減少いずれもアルゴリズムの意図しない変化を示すため、== で厳密に比較する。
    """
    service = MatchingService()
    result = service.match(
        children_file_bytes=_CHILDREN_CSV,
        children_file_format="csv",
        daycares_file_bytes=_DAYCARES_CSV,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["matched_children"]["total"] == _EXPECTED_TOTAL


def test_snapshot_result_structure_is_complete():
    """マッチング結果のレスポンス構造が壊れていないこと。

    全必須キーが存在し、matching_result_dict の件数が入力と一致することを確認する。
    """
    service = MatchingService()
    result = service.match(
        children_file_bytes=_CHILDREN_CSV,
        children_file_format="csv",
        daycares_file_bytes=_DAYCARES_CSV,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert "matching_result_dict" in result
    assert "household_result_dict" in result
    assert "matched_children" in result
    assert "meta" in result
    assert result["meta"]["algorithm"] == "cp_use_transfer"
    # 入力の児童数（3 人）と出力のキー数が一致すること
    assert len(result["matching_result_dict"]) == 3
