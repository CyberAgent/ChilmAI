from __future__ import annotations

import pandas as pd
import pytest

from chilmai.algorithm.cp_use_transfer.CP_algo import OptimizationFailureError
from chilmai.generic import matcher as matcher_mod
from chilmai.generic.config import DEFAULT_CONFIG
from chilmai.generic.error_codes import ErrorCode
from chilmai.generic.matcher import CpSatMatcher, _IdMapper, norm_id
from chilmai.generic.service import MatchingService


def _children_csv() -> bytes:
    return (
        "child_id,household_id,age,score_1,pref_1,pref_2,sibling_pattern,enrolled_daycare_id\n"
        "1,10,1,100,100,101,,\n"
        "2,11,1,80,100,101,2,\n"
        "3,11,1,80,101,100,2,\n"
    ).encode("utf-8")


def _daycares_csv() -> bytes:
    return (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,A,0,1,0,0,0,0\n"
        "101,B,0,1,0,0,0,0\n"
    ).encode("utf-8")


def test_validate_success():
    service = MatchingService()
    result = service.validate(
        children_file_bytes=_children_csv(),
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )
    assert result["is_valid"] is True
    assert result["errors"] == []
    assert result["summary"]["children_count"] == 3


def test_validate_missing_column():
    service = MatchingService()
    children = "child_id,household_id,age,pref_1\n1,10,1,100\n".encode("utf-8")
    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )
    assert result["is_valid"] is False
    assert any("点数1" in e["message"] for e in result["errors"])


def test_match_cp_sat_default():
    service = MatchingService()
    result = service.match(
        children_file_bytes=_children_csv(),
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    # child 1 (score 100) takes daycare 100; household 11 (same_prefer_older) places older child 2 solo at 101.
    assert result["matching_result_dict"]["1"] == "100"
    assert result["matching_result_dict"]["2"] == "101"
    assert result["matching_result_dict"]["3"] is None
    assert result["matched_children"]["total"] == 2
    assert result["meta"]["algorithm"] == "cp_use_transfer"


def test_match_returns_household_result_dict_with_combo_rank():
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,pref_2,sibling_pattern,enrolled_daycare_id\n"
        "1,10,2,100,100,101,2,\n"
        "2,10,1,100,100,101,2,\n"
        "3,11,1,80,101,100,1,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,A,0,1,1,0,0,0\n"
        "101,B,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
        solver_config={"algorithm": "cp_sat"},
    )

    # household 10 can be assigned (100, 100) as its first combo
    assert result["matching_result_dict"]["1"] == "100"
    assert result["matching_result_dict"]["2"] == "100"

    household_result = result["household_result_dict"]["10"]
    assert household_result["household_id"] == "10"
    assert household_result["child_ids"] == ["1", "2"]
    assert household_result["assigned"] == ["100", "100"]
    assert household_result["selected_combo"] == ["100", "100"]
    assert household_result["combo_rank"] == 1


def test_match_preserves_integer_score_from_decimal_string():
    """スコアが '.0' 付き文字列でも、parser の正規化で整数として扱われ、
    matcher の int() が落ちず、silent な base_score=0 フォールバックも起きないこと。

    比較対象として、'.0' なし版と一致する matching 結果になることを確認する。
    """
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,A,0,1,0,0,0,0\n"
        "101,B,0,1,0,0,0,0\n"
    ).encode("utf-8")
    # score_1='.0' 付き、score_2=空欄、pref_1 で daycare 100 と 101 が競合
    children_with_dot_zero = (
        "child_id,household_id,age,score_1,pref_1,pref_2,sibling_pattern,enrolled_daycare_id\n"
        "1,10,1,100.0,100,101,,\n"
        "2,20,1,80.0,100,101,,\n"
    ).encode("utf-8")
    children_plain = (
        "child_id,household_id,age,score_1,pref_1,pref_2,sibling_pattern,enrolled_daycare_id\n"
        "1,10,1,100,100,101,,\n"
        "2,20,1,80,100,101,,\n"
    ).encode("utf-8")

    service = MatchingService()
    result_dot = service.match(
        children_file_bytes=children_with_dot_zero,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )
    result_plain = service.match(
        children_file_bytes=children_plain,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    # score=100 の child 1 が daycare 100 に、score=80 の child 2 が daycare 101 に入る想定。
    # silent fallback が起きていると両者とも score=0 となり順序が崩れる。
    assert result_dot["matching_result_dict"] == result_plain["matching_result_dict"]
    assert result_dot["matching_result_dict"]["1"] == "100"
    assert result_dot["matching_result_dict"]["2"] == "101"


# --- _IdMapper 単体テスト ---


def test_id_mapper_roundtrip_string_ids():
    m = _IdMapper(["A001", "A002", "B001"])
    assert m.to_orig(m.to_int("A001")) == "A001"
    assert m.to_orig(m.to_int("B001")) == "B001"


def test_id_mapper_roundtrip_zero_padded():
    m = _IdMapper(["0000000001", "0000000002"])
    assert m.to_orig(m.to_int("0000000001")) == "0000000001"
    assert m.to_orig(m.to_int("0000000002")) == "0000000002"


def test_id_mapper_sequential_starts_at_one():
    m = _IdMapper(["x", "y", "z"])
    assert m.to_int("x") == 1
    assert m.to_int("y") == 2
    assert m.to_int("z") == 3


def test_id_mapper_deduplication():
    m = _IdMapper(["a", "b", "a", "c"])
    assert m.to_int("a") == 1
    assert m.to_int("b") == 2
    assert m.to_int("c") == 3
    assert m.to_orig(1) == "a"


def test_id_mapper_integer_input_returns_string():
    # pandas が整数として読んだ列を astype(str) した場合の挙動
    m = _IdMapper(["100", "101"])
    assert m.to_orig(m.to_int(100)) == "100"


def test_id_mapper_apply_series_normalizes_float_suffix():
    # apply_series も norm_id を通すため "11001.0" → "11001" として正しく解決できる
    import pandas as pd

    m = _IdMapper(["11001", "11002"])
    series = pd.Series(["11001.0", "11002.0"])
    result = m.apply_series(series)
    assert result.tolist() == [1, 2]


# --- norm_id 単体テスト ---


def testnorm_id_strips_float_suffix():
    assert norm_id("11005.0") == "11005"
    assert norm_id("11005.00") == "11005"


def testnorm_id_preserves_zero_padded():
    assert norm_id("0000000001") == "0000000001"


def testnorm_id_preserves_non_numeric():
    assert norm_id("A001") == "A001"
    assert norm_id("A001.0X") == "A001.0X"  # 末尾が 0 のみでなければ変換しない
    assert norm_id("A.0") == "A.0"  # 数値以外の ID は変換しない
    assert norm_id("A1.0") == "A1.0"  # 先頭が非数値なら変換しない


def testnorm_id_strips_whitespace():
    assert norm_id("  100  ") == "100"
    assert norm_id("  100.0  ") == "100"


# --- 文字列ID・ゼロパディングID の統合テスト ---


def test_match_string_child_ids_preserved_in_output():
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "C001,H01,1,100,D100,,\n"
        "C002,H02,1,80,D100,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "D100,Alpha,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert "C001" in result["matching_result_dict"]
    assert "C002" in result["matching_result_dict"]
    # 高スコアの C001 が D100 に割当
    assert result["matching_result_dict"]["C001"] == "D100"
    assert result["matching_result_dict"]["C002"] is None


def test_match_zero_padded_ids_preserved_in_output():
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "0000000001,0000000010,1,100,0000000100,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "0000000100,Alpha,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    # ゼロパディングが保持されること
    assert "0000000001" in result["matching_result_dict"]
    assert result["matching_result_dict"]["0000000001"] == "0000000100"
    assert "0000000010" in result["household_result_dict"]


def test_validate_accepts_string_daycare_ids():
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "C001,H01,1,100,D100,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "D100,Alpha,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is True
    assert result["errors"] == []


# --- 転園希望者（transfer applicant）テスト ---


def test_transfer_child_assigned_to_preferred_daycare():
    """転園希望者が希望保育所に空きがある場合、そこに割り当てられること。"""
    service = MatchingService()
    # Child 1: enrolled at D1, prefers D2. D2 has capacity.
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,101,100,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,0,0,0,0,0\n"
        "101,D2,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    # Transfer child prefers D2 and D2 has a seat — should be assigned there.
    assert result["matching_result_dict"]["1"] == "101"


def test_transfer_child_leaves_and_new_applicant_takes_freed_slot():
    """転園が成立した場合、在籍園の空き枠に新規申込者が入れること。"""
    service = MatchingService()
    # Child 1: transfer (enrolled D1, prefers D2, score 100). D2 has capacity → child 1 gets D2.
    # Child 2: new applicant (prefers D1, score 80). D1 gets 1 inflated slot from child 1's departure.
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,101,100,\n"
        "2,20,1,80,100,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,0,0,0,0,0\n"
        "101,D2,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    # Transfer child gets preferred daycare; freed slot goes to new applicant.
    assert result["matching_result_dict"]["1"] == "101"
    assert result["matching_result_dict"]["2"] == "100"


def test_multiple_transfer_one_returns_new_applicant_takes_freed_slot():
    """複数の転園希望者のうち1人が在籍園に戻り（IR）、転園した分の空き枠に新規申込者が入れること。"""
    service = MatchingService()
    # D2 has 1 seat.
    # Child 1: transfer from D1, score 100, prefers D2 → gets D2.
    # Child 2: transfer from D1, score 50, prefers D2 → D2 full, returns to D1 (IR).
    # Child 3: new applicant, score 70, prefers D1 → takes Child 1's freed slot at D1.
    # D1 base capacity 0, inflated by 2 transfer children → capacity 2.
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,101,100,\n"
        "2,20,1,50,101,100,\n"
        "3,30,1,70,100,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,0,0,0,0,0\n"
        "101,D2,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["matching_result_dict"]["1"] == "101"  # gets D2
    assert result["matching_result_dict"]["2"] == "100"  # IR fallback to D1
    assert result["matching_result_dict"]["3"] == "100"  # freed slot from child 1's departure


def test_transfer_child_falls_back_to_enrolled_daycare():
    """転園希望者の希望保育所が高スコアの別申込者で埋まる場合、在籍園に戻れること（IR）。"""
    service = MatchingService()
    # Child 1: transfer applicant (enrolled at D1), prefers D2, score 50.
    # Child 2: new applicant (no enrolled daycare), prefers D2, score 100.
    # D2 has only 1 seat → child 2 (higher score) wins D2.
    # D1 gets 1 transfer seat freed → child 1 must be assigned there (IR).
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,50,101,100,\n"
        "2,20,1,100,101,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,0,0,0,0,0\n"
        "101,D2,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    # High-score new applicant takes D2.
    assert result["matching_result_dict"]["2"] == "101"
    # Transfer child falls back to enrolled daycare D1 (IR guaranteed).
    assert result["matching_result_dict"]["1"] == "100"


def test_transfer_no_capacity_exceeded():
    """転園元に戻った児童を含めても定員超過にならないこと。

    D1 base_cap=0, 2 transfer children (child 1, child 2).
    effective cap = 0 + 2 = 2.
    D2 cap=1.
    Child 1 (score 100) → D2. Child 2 (score 50) → IR to D1.
    Child 3 (new, score 70) → D1 freed slot.
    Total at D1 = child 2 (return) + child 3 (new) = 2 ≤ effective cap 2.
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,101,100,\n"
        "2,20,1,50,101,100,\n"
        "3,30,1,70,100,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,0,0,0,0,0\n"
        "101,D2,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    matching = result["matching_result_dict"]
    assert matching["1"] == "101"  # transfer to D2
    assert matching["2"] == "100"  # IR back to D1
    assert matching["3"] == "100"  # freed slot at D1

    # Capacity check: count total assignments per daycare
    from collections import Counter

    counts = Counter(d for d in matching.values() if d is not None)
    # D1: base_cap=0, transfer_out=2, effective=2
    assert counts.get("100", 0) <= 0 + 2, f"D1 over capacity: {counts['100']} > 2"
    # D2: cap=1
    assert counts.get("101", 0) <= 1, f"D2 over capacity: {counts['101']} > 1"


def test_transfer_assignment_within_pref_or_enrolled():
    """割り当て先が希望リストまたは転園元に含まれること。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,pref_2,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,101,102,100,\n"
        "2,20,1,80,100,,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,0,0,0,0,0\n"
        "101,D2,0,1,0,0,0,0\n"
        "102,D3,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    matching = result["matching_result_dict"]
    # Child 1: prefs=[101, 102], enrolled=100 → assigned to one of {100, 101, 102}
    assert matching["1"] in {"100", "101", "102"}
    # Child 2: prefs=[100] → assigned to 100 or unmatched
    assert matching["2"] in {"100", None}


def test_transfer_siblings_capacity_not_exceeded():
    """きょうだい転園で定員を超過しないこと。

    Sibling pair (child 1 age 1, child 2 age 2) enrolled at D1, prefer D2.
    D2 has capacity for both ages → siblings transfer together.
    New applicant child 3 takes a freed slot at D1.
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,101,100,2\n"
        "2,10,2,100,101,100,2\n"
        "3,30,1,80,100,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,0,0,0,0,0\n"
        "101,D2,0,1,1,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    matching = result["matching_result_dict"]
    # Both siblings should transfer to D2
    assert matching["1"] == "101"
    assert matching["2"] == "101"
    # New applicant takes freed age-1 slot at D1
    assert matching["3"] == "100"

    # Capacity check
    from collections import Counter

    age_map = {"1": 1, "2": 2, "3": 1}
    daycare_age_counts: dict[tuple[str, int], int] = Counter()
    for cid, did in matching.items():
        if did is not None:
            daycare_age_counts[(did, age_map[cid])] += 1

    # D1: base=0, transfer_out age1=1, transfer_out age2=1
    assert daycare_age_counts.get(("100", 1), 0) <= 0 + 1
    assert daycare_age_counts.get(("100", 2), 0) <= 0 + 1
    # D2: cap age1=1, cap age2=1
    assert daycare_age_counts.get(("101", 1), 0) <= 1
    assert daycare_age_counts.get(("101", 2), 0) <= 1


def test_low_score_transfer_child_returns_to_enrolled_daycare():
    """低スコアの転園児でも転園元に戻れること（IR保証）。

    Transfer child (score 10) enrolled at D1, prefers D2.
    New child A (score 100): prefers D2 → gets D2.
    New child B (score 90): prefers D1.
    D1 base_cap=0, 1 transfer → effective=1. Only 1 slot.
    Transfer child must return to D1 despite score 10 < 90.
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,10,101,100,\n"  # transfer: very low score
        "2,20,1,100,101,,\n"  # new: wants D2
        "3,30,1,90,100,,\n"  # new: wants D1, much higher score
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,0,0,0,0,0\n"
        "101,D2,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    matching = result["matching_result_dict"]
    # Transfer child must return to D1 (IR guaranteed regardless of score)
    assert matching["1"] == "100"
    assert matching["2"] == "101"


def test_low_score_transfer_siblings_return_to_enrolled_daycare():
    """低スコアのきょうだい転園児でも転園元に戻れること。

    Siblings (score 10 each) enrolled at D1, prefer D2.
    D2 cap=0 → no room. Both must return to D1.
    New child (score 100) wants D1 but no free slots.
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,10,101,100,2\n"
        "2,10,2,10,101,100,2\n"
        "3,30,1,100,100,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,0,0,0,0,0\n"
        "101,D2,0,0,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    matching = result["matching_result_dict"]
    # Both siblings must return to D1 (D2 has no capacity)
    assert matching["1"] == "100"
    assert matching["2"] == "100"
    # New child can't get D1 (both slots taken by returning siblings)
    assert matching["3"] is None


# --- 転園希望者の無効な希望リストに対するマッチングテスト ---


def test_transfer_child_empty_pref_raises_validation_error():
    """転園希望者でも pref_1 が空の場合は match 呼び出し時にバリデーションエラーになること。

    転園希望者であっても有効な希望を少なくとも 1 件入力する必要がある。
    空 pref のまま match を呼ぶと ValidationError が発生し、マッチングは実行されない。
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,,100,\n"  # enrolled at D1 (100), no preference given
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,0,0,0,0,0\n"
        "101,D2,0,1,0,0,0,0\n"
    ).encode("utf-8")

    with pytest.raises(ValueError, match="Validation failed"):
        service.match(
            children_file_bytes=children,
            children_file_format="csv",
            daycares_file_bytes=daycares,
            daycares_file_format="csv",
            mapping=DEFAULT_CONFIG,
        )


def test_transfer_child_duplicate_pref_ids_no_crash():
    """希望リストに重複した保育園 ID があっても例外が発生しないこと。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,pref_2,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,101,101,100,\n"  # pref_1 == pref_2 (duplicate D2)
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,0,0,0,0,0\n"
        "101,D2,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    # D1 base_cap=0 (transfer-out frees 1 slot, but that goes back to the transfer child's IR).
    # D2 cap=1 is the only available seat → child must go to D2 (top pref).
    assert result["matching_result_dict"]["1"] == "101"


# --- 過制約・全員未マッチになるケース ---


def test_all_zero_capacity_all_children_unmatched():
    """全保育園の定員が 0 の場合、全児童が未マッチ（None）になること。

    非転園児は sum(xfp) <= 1 制約なので、定員 0 では xfp=0 となり全員未マッチ。
    ソルバーは OPTIMAL（目標値 0）を返す。クラッシュしない。
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,,\n"
        "2,20,1,90,100,,\n"
        "3,30,1,80,100,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,0,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["matched_children"]["total"] == 0
    assert all(v is None for v in result["matching_result_dict"].values())


def test_single_seat_many_applicants_one_matched():
    """定員 1 で多数の申請者が同じ保育園を希望した場合、1 人だけマッチすること。"""
    service = MatchingService()
    header = "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
    rows = "".join(f"{i},{i + 100},1,100,100,,\n" for i in range(1, 11))
    children = (header + rows).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["matched_children"]["total"] == 1
    matched_daycares = [v for v in result["matching_result_dict"].values() if v is not None]
    assert matched_daycares == ["100"]


# --- 転園希望者が希望落選時に在籍園へフォールバックするケース ---


def test_multiple_transfers_from_different_daycares_all_fall_back():
    """異なる在籍園を持つ複数の転園希望者が全員落選し、それぞれの在籍園へ戻ること。

    - 児童 1: 在籍 D1(100)、希望 D3(300)、スコア 50
    - 児童 2: 在籍 D2(200)、希望 D3(300)、スコア 60
    - 児童 3: 新規、希望 D3(300)、スコア 100  ← 唯一の 1 席を獲得
    期待: 児童 1 → D1、児童 2 → D2、児童 3 → D3
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,50,300,100,\n"
        "2,20,1,60,300,200,\n"
        "3,30,1,100,300,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,0,0,0,0,0\n"
        "200,D2,0,0,0,0,0,0\n"
        "300,D3,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    matching = result["matching_result_dict"]
    assert matching["3"] == "300"  # new applicant wins D3
    assert matching["1"] == "100"  # child 1 falls back to enrolled D1
    assert matching["2"] == "200"  # child 2 falls back to enrolled D2


# --- 同一保育園から複数の転園希望者が出る場合の定員インフレーションテスト ---


def test_three_transfers_from_same_daycare_inflate_capacity():
    """3 人が同一保育園（D1）から転出し、実効定員が 3 になること。

    D1 base cap = 0。3 人が転出 → 実効定員 = 3。
    新規申請者 3 人が全員 D1 を希望 → 全員 D1 に入れること。
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,200,100,\n"  # transfer from D1, wants D2
        "2,20,1,100,200,100,\n"  # transfer from D1, wants D2
        "3,30,1,100,200,100,\n"  # transfer from D1, wants D2
        "4,40,1,80,100,,\n"  # new applicant, wants D1
        "5,50,1,80,100,,\n"  # new applicant, wants D1
        "6,60,1,80,100,,\n"  # new applicant, wants D1
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,0,0,0,0,0\n"  # base cap=0; 3 transfer-out → effective age1=3
        "200,D2,0,3,0,0,0,0\n"  # cap=3 for the 3 transfer children
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    matching = result["matching_result_dict"]
    # All 3 transfer children move to D2
    assert matching["1"] == "200"
    assert matching["2"] == "200"
    assert matching["3"] == "200"
    # All 3 new applicants take freed D1 slots
    assert matching["4"] == "100"
    assert matching["5"] == "100"
    assert matching["6"] == "100"


# --- スコア同点時の定員制約とタイブレーク挙動テスト ---


def test_tiebreak_is_deterministic_across_runs():
    """同スコア・同希望の競合で、複数回実行しても結果が同一であること（決定論的挙動）。

    小規模・固定入力では OR-Tools CP-SAT はランダム性なしで即座に OPTIMAL を返すため、
    同一問題に対して常に同じ割り当てを出力する。
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,,\n"
        "2,20,1,100,100,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,1,0,0,0,0\n"
    ).encode("utf-8")

    results = []
    for _ in range(3):
        r = service.match(
            children_file_bytes=children,
            children_file_format="csv",
            daycares_file_bytes=daycares,
            daycares_file_format="csv",
            mapping=DEFAULT_CONFIG,
        )
        results.append(r["matching_result_dict"])

    # All runs must yield the same result
    assert results[0] == results[1] == results[2]
    # Exactly 1 child should be matched (capacity=1)
    assert sum(1 for v in results[0].values() if v is not None) == 1


def test_tiebreak_by_preference_rank_when_same_score():
    """同スコアでも希望順位が異なる 2 人が、それぞれの第 1 希望保育園に割り当てられること。

    Child 1: D1 第 1 希望、Child 2: D2 第 1 希望、競合なし。
    安定性制約（bp_num=0）により各自が第 1 希望を得ることが保証される。
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,pref_2,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,101,,\n"
        "2,20,1,100,101,100,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,1,0,0,0,0\n"
        "101,D2,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["matching_result_dict"]["1"] == "100"
    assert result["matching_result_dict"]["2"] == "101"


# --- CP ソルバーのタイムアウトおよび SUBOPTIMAL 返却時の挙動テスト ---


def test_short_timeout_does_not_crash():
    """デフォルトより短いタイムアウトを設定しても、小規模問題では正しい結果を返すこと。

    小規模な入力ではソルバーが即座に OPTIMAL を返すため、例外は発生しない。
    max_time_seconds は service.match の solver_config で渡せる。

    注: 0.001s のような極端な値は OR-Tools が UNKNOWN を返すため例外になる。
    ここでは "デフォルト(10s)より短いが問題を解くには十分" な値を使う。
    """
    service = MatchingService()
    result = service.match(
        children_file_bytes=_children_csv(),
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
        solver_config={"max_time_seconds": 1.0},
    )

    assert "matching_result_dict" in result
    assert "matched_children" in result
    assert result["meta"]["algorithm"] == "cp_use_transfer"


def test_extreme_timeout_raises_error():
    """極端に短いタイムアウト（UNKNOWN 状態）では例外が送出されること。

    max_time_seconds=0 を渡すと OR-Tools は実行前に終了し UNKNOWN を返す。
    matcher はこれを OptimizationFailureError として raise するため、
    service.match() は例外を呼び出し元に伝播させる。
    このテストはその例外パスを実際にカバーする。
    """
    service = MatchingService()
    with pytest.raises(Exception):
        service.match(
            children_file_bytes=_children_csv(),
            children_file_format="csv",
            daycares_file_bytes=_daycares_csv(),
            daycares_file_format="csv",
            mapping=DEFAULT_CONFIG,
            solver_config={"max_time_seconds": 0},
        )


# --- 最小構成（児童 1 人・保育園 1 つ）のマッチングテスト ---


def test_minimal_one_child_one_daycare_matched():
    """1 児童・1 保育園・定員 1：正しくマッチングされること。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["matching_result_dict"]["1"] == "100"
    assert result["matched_children"]["total"] == 1


def test_minimal_one_child_one_daycare_zero_cap_unmatched():
    """1 児童・1 保育園・定員 0：未マッチ（None）になること。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,100,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,0,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["matching_result_dict"]["1"] is None
    assert result["matched_children"]["total"] == 0


def test_minimal_no_pref_column_fails_validation():
    """希望カラム（pref_1）が存在しない場合、バリデーションエラーになること。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,enrolled_daycare_id,sibling_pattern\n" "1,10,1,100,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["is_valid"] is False
    assert any("希望列が見つかりません" in e["message"] for e in result["errors"])


def test_missing_score1_column_uses_custom_score_prefix_in_message():
    """score_prefix をカスタム設定した場合、score_1 欠落エラーに表示名が使われること。"""
    from copy import deepcopy

    service = MatchingService()
    custom_mapping = deepcopy(DEFAULT_CONFIG)
    custom_mapping["children"]["score_prefix"] = "第N希望点数"

    children = (
        "child_id,household_id,age,pref_1,enrolled_daycare_id,sibling_pattern\n" "1,10,1,100,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=custom_mapping,
    )

    assert result["is_valid"] is False
    assert any("第1希望点数" in e["message"] for e in result["errors"])


def test_unknown_daycare_error_uses_custom_preference_prefix_in_message():
    """preference_prefix をカスタム設定した場合、不明保育所IDエラーに表示名が使われること。"""
    from copy import deepcopy

    service = MatchingService()
    custom_mapping = deepcopy(DEFAULT_CONFIG)
    custom_mapping["children"]["preference_prefix"] = "第N志望"

    children = (
        "child_id,household_id,age,score_1,第1志望,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,999,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.validate(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=custom_mapping,
    )

    assert result["is_valid"] is False
    assert any("第1志望" in e["message"] for e in result["errors"])


def test_minimal_single_transfer_child_gets_preferred_daycare():
    """転園希望者 1 人のみ：空きのある希望先に割り当てられること。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,101,100,\n"  # enrolled at D1 (100), prefers D2 (101)
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,0,0,0,0,0\n"
        "101,D2,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["matching_result_dict"]["1"] == "101"
    assert result["matched_children"]["total"] == 1


# --- 転園元保育所への割当を結果に含めないオプションのテスト ---


def test_exclude_transfer_back_works_with_canonical_enrolled_column():
    """CSV の在籍保育所列がカノニカル名 enrolled_daycare_id のとき exclude_transfer_back が有効になること。

    DEFAULT_CONFIG では enrolled_daycare_id のマッピング先を "在籍保育所ID" とするが、
    原始 CSV が "enrolled_daycare_id" を列名に使う場合、フォールバックがなければ
    機能が silently no-op になる。
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,101,100,\n"  # enrolled at D1, prefers D2 (cap=0) → IR to D1
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,0,0,0,0,0\n"
        "101,D2,0,0,0,0,0,0\n"
    ).encode("utf-8")
    mapping = {
        **DEFAULT_CONFIG,
        "output": {**DEFAULT_CONFIG["output"], "exclude_transfer_back": "true"},
    }

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=mapping,
    )

    # Child 1 IR'd to D1 (enrolled daycare) → result must be blanked
    assert result["matching_result_dict"]["1"] is None
    output_row = result["output_rows"][0]
    assert output_row["入所選考結果保育所ID"] == ""
    assert output_row["入所選考結果保育所名"] == ""

    # household_result_dict も整合していること
    hh = result["household_result_dict"]["10"]
    assert hh["assigned"] == [None]
    assert hh["selected_combo"] == [None]


def test_exclude_transfer_back_decrements_only_child_and_siblings_correctly():
    """exclude_transfer_back 時に matched_children.only_child と siblings の両方が減算されること。

    - きょうだいペア（HH 10, 年齢 1+2）: 在籍 D1、希望 D3（年齢 2 定員 0 → 一緒に入れない）→ IR to D1 → 空欄
    - 単独申込（HH 20, 年齢 1）: 在籍 D2、希望 D3（先に取られる）→ IR to D2 → 空欄
    - 単独申込（HH 30, 年齢 1）: 在籍なし、スコア最大、希望 D3 → D3 割当 → 空欄にしない

    除外後: total=1, siblings=0, only_child=1（total == only_child + siblings が成立すること）
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,50,103,100,2\n"  # sibling, enrolled D1, prefer D3 (age2 cap 0) → IR to D1
        "2,10,2,50,103,100,2\n"  # sibling, enrolled D1, prefer D3 (age2 cap 0) → IR to D1
        "3,20,1,50,103,101,\n"  # only, enrolled D2, prefer D3 (full) → IR to D2
        "4,30,1,100,103,,\n"  # only, no enrolled, score 100, prefer D3 → gets D3
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,0,0,0,0,0\n"  # base 0; effective age1=1 age2=1 (2 transfer-outs)
        "101,D2,0,0,0,0,0,0\n"  # base 0; effective age1=1 (1 transfer-out)
        "103,D3,0,1,0,0,0,0\n"  # real cap age1=1 only (no age2 → siblings can't go together)
    ).encode("utf-8")
    mapping = {
        **DEFAULT_CONFIG,
        "output": {**DEFAULT_CONFIG["output"], "exclude_transfer_back": "true"},
    }

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=mapping,
    )

    # Child 4 (no enrolled_daycare) is the only unaffected match
    assert result["matching_result_dict"]["4"] == "103"
    # Children 1, 2, 3 were assigned to their enrolled daycare → blanked
    assert result["matching_result_dict"]["1"] is None
    assert result["matching_result_dict"]["2"] is None
    assert result["matching_result_dict"]["3"] is None

    mc = result["matched_children"]
    assert mc["total"] == 1
    assert mc["only_child"] == 1
    assert mc["siblings"] == 0
    # Invariant: total must equal the sum of its sub-buckets
    assert mc["total"] == mc["only_child"] + mc["siblings"]

    # household_result_dict も matching_result_dict と整合していること
    hh10 = result["household_result_dict"]["10"]
    assert hh10["assigned"] == [None, None]
    assert hh10["selected_combo"] == [None, None]
    hh20 = result["household_result_dict"]["20"]
    assert hh20["assigned"] == [None]
    assert hh20["selected_combo"] == [None]
    hh30 = result["household_result_dict"]["30"]
    assert hh30["assigned"] == ["103"]
    assert hh30["selected_combo"] == ["103"]


def test_matched_children_excludes_transfer_back_regardless_of_setting():
    """exclude_transfer_back が false（デフォルト）でも matched_children は転園元復帰を除外すること。

    Excel列の空欄化は行わないが、M/X%集計は常に新規割当のみを数える。
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,101,100,\n"  # enrolled D1, prefers D2 (cap=0) → IR to D1
        "2,20,1,100,101,,\n"  # no enrolled, prefers D2 (cap=0) → unmatched
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,0,0,0,0,0\n"
        "101,D2,0,0,0,0,0,0\n"
    ).encode("utf-8")
    mapping = {**DEFAULT_CONFIG}  # exclude_transfer_back == "false"（デフォルト）

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=mapping,
    )

    # matched_children は転園元復帰（child 1）を除くため 0
    mc = result["matched_children"]
    assert mc["total"] == 0
    assert result.get("transfer_back_count") == 1

    # Excel列は空欄にしない（exclude_transfer_back == "false"）
    assert result["matching_result_dict"]["1"] == "100"
    output_row = next(r for r in result["output_rows"] if str(r.get("child_id", "")) == "1")
    assert output_row["入所選考結果保育所ID"] == "100"

    # household_result_dict も空欄化しない
    hh = result["household_result_dict"]["10"]
    assert hh["assigned"] == ["100"]


def test_matched_children_by_age_basic():
    """matched_children に by_age と applied 系のフィールドが含まれること。"""
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,sibling_pattern,enrolled_daycare_id\n"
        "1,10,0,100,100,,\n"  # only, age 0 → matched
        "2,11,1,50,100,2,\n"  # sibling, age 1 → matched (cap 1)
        "3,11,2,50,100,2,\n"  # sibling, age 2 → unmatched (cap 0)
        "4,12,1,80,100,,\n"  # only, age 1 → unmatched (lower score than 2)
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,A,1,1,0,0,0,0\n"
    ).encode("utf-8")
    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )
    mc = result["matched_children"]
    assert mc["applied_total"] == 4
    assert mc["by_age"]["0"] == {"applied": 1, "matched": 1}
    assert mc["by_age"]["1"] == {"applied": 2, "matched": 1}
    assert mc["by_age"]["2"] == {"applied": 1, "matched": 0}
    assert mc["by_age"]["3"] == {"applied": 0, "matched": 0}


def test_matched_children_by_age_decrements_on_transfer_back():
    """転園元復帰が生じた場合、by_age の matched もその児童の年齢から減算されること。"""
    service = MatchingService()
    # child 1: age 1, enrolled D100, prefers D101 (cap=0) → IR to D100 → blanked from matched
    # child 2: age 2, no enrolled, prefers D101 (cap=0) → unmatched
    children = (
        "child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        "1,10,1,100,101,100,\n"
        "2,20,2,100,101,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "100,A,0,0,0,0,0,0\n"
        "101,B,0,0,0,0,0,0\n"
    ).encode("utf-8")
    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )
    mc = result["matched_children"]
    assert mc["total"] == 0
    assert result["transfer_back_count"] == 1
    # age 1: applied=1, matched は 1 → 0（転園元復帰）に減算
    assert mc["by_age"]["1"] == {"applied": 1, "matched": 0}
    assert mc["by_age"]["2"] == {"applied": 1, "matched": 0}


def test_build_result_by_age_consistent_with_applied_total():
    """想定外の年齢が混ざっても sum(by_age.applied) == applied_total が保たれること。"""
    children = pd.DataFrame(
        {
            "child_id": [1, 2, 3],
            "household_id": [10, 20, 30],
            "age": [2, 5, 7],  # 7 は仕様外だが防御的に集計対象とする
        }
    )
    assignments: dict[int, int | None] = {1: 100, 2: None, 3: None}
    result = CpSatMatcher._build_result(children, assignments, household_result_dict={})
    mc = result["matched_children"]
    assert mc["applied_total"] == 3
    assert sum(b["applied"] for b in mc["by_age"].values()) == mc["applied_total"]
    assert sum(b["matched"] for b in mc["by_age"].values()) == mc["total"]
    assert mc["by_age"]["7"] == {"applied": 1, "matched": 0}


def test_match_16digit_score_orders_correctly():
    """16桁スコアでも大小比較が正しく行われ、高スコア側が優先されること。"""
    service = MatchingService()
    high_score = "9" * 16
    low_score = "1" + "0" * 15
    children = (
        f"child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        f"1,10,1,{high_score},100,,\n"
        f"2,20,1,{low_score},100,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,"
        "capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["matching_result_dict"]["1"] == "100"
    assert result["matching_result_dict"]["2"] is None


def test_match_20digit_score_orders_correctly():
    """20桁スコアが FamilyPrefBuilder 経路を含めて match() まで精度を保つこと。"""
    service = MatchingService()
    high_score = "9" * 20
    low_score = "1" + "0" * 19
    children = (
        f"child_id,household_id,age,score_1,pref_1,enrolled_daycare_id,sibling_pattern\n"
        f"1,10,1,{high_score},100,,\n"
        f"2,20,1,{low_score},100,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,"
        "capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,1,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["matching_result_dict"]["1"] == "100"
    assert result["matching_result_dict"]["2"] is None


def test_match_20digit_per_daycare_score_orders_correctly():
    """score_2 など保育所別スコアも 20 桁で精度が保たれること。"""
    service = MatchingService()
    high_score = "9" * 20
    low_score = "1" + "0" * 19
    children = (
        f"child_id,household_id,age,score_1,score_2,pref_1,pref_2,enrolled_daycare_id,sibling_pattern\n"
        f"1,10,1,0,{high_score},100,101,,\n"
        f"2,20,1,0,{low_score},100,101,,\n"
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,"
        "capacity_age3,capacity_age4,capacity_age5\n"
        "100,D1,0,1,0,0,0,0\n"
        "101,D2,0,10,0,0,0,0\n"
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert result["matching_result_dict"]["1"] == "100"
    assert result["matching_result_dict"]["2"] == "101"


# --- check_outcome 検証＋リトライ ---


def test_match_calls_check_outcome_after_optimal(monkeypatch):
    """OPTIMAL 後に check_outcome が呼ばれ、違反なしなら通常通り結果を返すこと。"""
    calls: list[tuple] = []

    def check_stub(*args, **kwargs):
        calls.append((args, kwargs))
        return ([], [], {})  # 違反なし

    monkeypatch.setattr(matcher_mod, "check_outcome", check_stub)

    service = MatchingService()
    result = service.match(
        children_file_bytes=_children_csv(),
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    assert len(calls) == 1
    args, _ = calls[0]
    assert len(args) == 5  # children_dic, daycares_dic, families_dic, outcome_children_dic, outcome_fp
    assert "matching_result_dict" in result


def test_match_retries_when_verification_fails_then_succeeds(monkeypatch):
    """初回 check_outcome で違反検出 → max_time_seconds×10 で再試行 → 2回目成功でマッチング完了すること。"""
    cp_calls: list[float] = []
    check_calls: list[int] = []
    real_cp = matcher_mod.CP

    def cp_spy(*args, **kwargs):
        cp_calls.append(kwargs.get("solver_time"))
        return real_cp(*args, **kwargs)

    def check_stub(*args, **kwargs):
        check_calls.append(1)
        if len(check_calls) == 1:
            return ([1], [], {})  # 1回目: IR違反あり
        return ([], [], {})  # 2回目: クリーン

    monkeypatch.setattr(matcher_mod, "CP", cp_spy)
    monkeypatch.setattr(matcher_mod, "check_outcome", check_stub)

    service = MatchingService()
    result = service.match(
        children_file_bytes=_children_csv(),
        children_file_format="csv",
        daycares_file_bytes=_daycares_csv(),
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
        solver_config={"max_time_seconds": 1.0},
    )

    assert len(cp_calls) == 2
    assert len(check_calls) == 2
    assert cp_calls[0] == 1.0
    assert cp_calls[1] == 10.0  # max_time_seconds × 10
    assert "matching_result_dict" in result


def test_match_raises_verification_failed_after_retry(monkeypatch):
    """check_outcome が 2回連続で違反を返した場合 SOLVER_VERIFICATION_FAILED を raise すること。"""
    check_calls: list[int] = []

    def check_stub(*args, **kwargs):
        check_calls.append(1)
        return ([1], [200], {1: [0]})  # IR違反 + 定員違反 + BP

    monkeypatch.setattr(matcher_mod, "check_outcome", check_stub)

    service = MatchingService()
    with pytest.raises(OptimizationFailureError) as exc_info:
        service.match(
            children_file_bytes=_children_csv(),
            children_file_format="csv",
            daycares_file_bytes=_daycares_csv(),
            daycares_file_format="csv",
            mapping=DEFAULT_CONFIG,
            solver_config={"max_time_seconds": 1.0},
        )

    assert len(check_calls) == 2  # 1回目 + リトライ
    assert getattr(exc_info.value, "code", None) == ErrorCode.SOLVER_VERIFICATION_FAILED
    # docs（reference/web-ui/troubleshooting.md の E504）が引用している画面表示文言
    assert str(exc_info.value).startswith("マッチング結果の妥当性検証に失敗しました")


def test_match_raises_timeout_after_retry(monkeypatch, caplog):
    """2回連続 FEASIBLE で SOLVER_TIMEOUT を raise し、画面表示文言が docs の引用と一致すること。

    利用者向けメッセージにはソルバーステータス名を含めず、調査用にログへ残す。
    """
    import logging

    from ortools.sat.python import cp_model

    cp_calls: list[float] = []

    def cp_stub(*args, **kwargs):
        cp_calls.append(kwargs.get("solver_time"))
        return ({}, {}, None, None, None, cp_model.FEASIBLE)

    monkeypatch.setattr(matcher_mod, "CP", cp_stub)

    service = MatchingService()
    with caplog.at_level(logging.WARNING, logger="chilmai.matching"):
        with pytest.raises(OptimizationFailureError) as exc_info:
            service.match(
                children_file_bytes=_children_csv(),
                children_file_format="csv",
                daycares_file_bytes=_daycares_csv(),
                daycares_file_format="csv",
                mapping=DEFAULT_CONFIG,
                solver_config={"max_time_seconds": 1.0},
            )

    assert len(cp_calls) == 2  # 1回目 + 10倍リトライ
    assert cp_calls[1] == 10.0
    assert getattr(exc_info.value, "code", None) == ErrorCode.SOLVER_TIMEOUT
    message = str(exc_info.value)
    # docs（reference/web-ui/troubleshooting.md の E502）が引用している画面表示文言
    assert message.startswith("制限時間内にマッチング結果が確定しませんでした。")
    assert "FEASIBLE" not in message  # 利用者向けにはステータス名を出さない
    assert "FEASIBLE" in caplog.text  # 調査用にログへ残す


def test_match_feasible_then_verification_fail_raises_immediately(monkeypatch):
    """1回目 FEASIBLE → リトライ → 2回目 OPTIMAL+検証失敗 で `_retried` 共有により即 E504 を raise すること。"""
    from ortools.sat.python import cp_model

    cp_calls: list[float] = []
    check_calls: list[int] = []

    def cp_stub(*args, **kwargs):
        cp_calls.append(kwargs.get("solver_time"))
        if len(cp_calls) == 1:
            return ({}, {}, None, None, None, cp_model.FEASIBLE)
        return ({}, {}, None, None, None, cp_model.OPTIMAL)

    def check_stub(*args, **kwargs):
        check_calls.append(1)
        return ([1], [], {})  # IR違反

    monkeypatch.setattr(matcher_mod, "CP", cp_stub)
    monkeypatch.setattr(matcher_mod, "check_outcome", check_stub)

    service = MatchingService()
    with pytest.raises(OptimizationFailureError) as exc_info:
        service.match(
            children_file_bytes=_children_csv(),
            children_file_format="csv",
            daycares_file_bytes=_daycares_csv(),
            daycares_file_format="csv",
            mapping=DEFAULT_CONFIG,
            solver_config={"max_time_seconds": 1.0},
        )

    assert len(cp_calls) == 2  # FEASIBLE → 10倍リトライで OPTIMAL
    assert cp_calls[0] == 1.0
    assert cp_calls[1] == 10.0
    assert len(check_calls) == 1  # 2回目の OPTIMAL でのみ呼ばれる
    assert getattr(exc_info.value, "code", None) == ErrorCode.SOLVER_VERIFICATION_FAILED
