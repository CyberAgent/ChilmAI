"""兄弟希望パターンの組み合わせがソルバーの割り当て結果に正しく反映されるテスト。

test_sibling_pref_patterns.py は希望リストの生成ロジックのみを検証しているが、
このファイルでは実際に CP ソルバーを通じた割り当て結果の正しさを検証する。
"""

from __future__ import annotations

from chilmai.generic.config import DEFAULT_CONFIG
from chilmai.generic.service import MatchingService


# ---------------------------------------------------------------------------
# パターン 2（同保順次・上）: 同園優先、上の子単独フォールバック
# ---------------------------------------------------------------------------


def test_sibling_pattern2_same_daycare_when_capacity_allows():
    """パターン 2: D1 に両年齢分の定員がある場合、同園コンボが選ばれること。

    family_pref = [(D1, D1), (D1, None)] のうち、(D1, D1) が feasible なので
    ソルバーはマッチ数を最大化するため両者を D1 に割り当てる。
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,sibling_pattern,enrolled_daycare_id\n"
        "1,10,2,100,200,2,\n"  # older child, age=2, prefers D1 (200)
        "2,10,1,100,200,2,\n"  # younger child, age=1, prefers D1 (200)
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "200,D1,0,1,1,0,0,0\n"  # D1 fits both age-1 and age-2
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    matching = result["matching_result_dict"]
    # Both siblings should be placed at D1 (same daycare combo, rank 1)
    assert matching["1"] == "200"
    assert matching["2"] == "200"


def test_sibling_pattern2_older_solo_when_no_shared_daycare_capacity():
    """パターン 2: 同園に年少者の定員がない場合、年長者のみが割り当てられること。

    D1: age2=1, age1=0 (年少者の枠なし)
    D2: age2=0, age1=1 (年長者の枠なし)
    family_pref = [(D1,D1), (D2,D2), (D1,None), (D2,None)]
    - (D1,D1): D1 age1=0 → not feasible
    - (D2,D2): D2 age2=0 → not feasible
    - (D1,None): D1 age2=1 → feasible → older at D1, younger unmatched
    - (D2,None): D2 age2=0 → not feasible
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,pref_2,sibling_pattern,enrolled_daycare_id\n"
        "1,10,2,100,200,201,2,\n"  # older child, age=2
        "2,10,1,100,200,201,2,\n"  # younger child, age=1
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "200,D1,0,0,1,0,0,0\n"  # D1: age2=1, age1=0
        "201,D2,0,1,0,0,0,0\n"  # D2: age1=1, age2=0
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    matching = result["matching_result_dict"]
    # Older child (age-2) goes to D1 (only feasible solo combo)
    assert matching["1"] == "200"
    # Younger child is unmatched (no same-daycare combo is feasible)
    assert matching["2"] is None


# ---------------------------------------------------------------------------
# パターン 1（同保同時）: 全員同所・全員同月必須
# ---------------------------------------------------------------------------


def test_sibling_pattern1_three_siblings_all_same_daycare():
    """パターン 1: D1 に全年齢分の定員がある場合、3 人全員が同園に割り当てられること。

    family_pref = [(D1, D1, D1)] のみ（全員同所）。
    D1 が全年齢をカバーするため feasible → 全員 D1。
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,sibling_pattern,enrolled_daycare_id\n"
        "1,10,2,100,200,1,\n"  # oldest, age=2
        "2,10,1,100,200,1,\n"  # middle, age=1
        "3,10,0,100,200,1,\n"  # youngest, age=0
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "200,D1,1,1,1,0,0,0\n"  # D1 fits age-0, age-1, age-2
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    matching = result["matching_result_dict"]
    # All three siblings assigned to D1 (same daycare required by pattern 1)
    assert matching["1"] == "200"
    assert matching["2"] == "200"
    assert matching["3"] == "200"
    assert result["matched_children"]["total"] == 3


def test_sibling_pattern1_all_unmatched_when_no_valid_same_daycare():
    """パターン 1: 全員が同一保育園に入れる選択肢がない場合、全員未マッチになること。

    D1: age0=0, age1=1, age2=1 (年少者=age0 の枠なし)
    D2: age0=1, age1=0, age2=0 (年少者のみ)
    family_pref = [(D1,D1,D1), (D2,D2,D2)]
    - (D1,D1,D1): D1 age0=0 → not feasible
    - (D2,D2,D2): D2 age1=0, age2=0 → not feasible
    非転園児は sum(xfp) <= 1 → xfp=0 も許容 → 全員未マッチ
    """
    service = MatchingService()
    children = (
        "child_id,household_id,age,score_1,pref_1,pref_2,sibling_pattern,enrolled_daycare_id\n"
        "1,10,2,100,200,201,1,\n"  # oldest, age=2
        "2,10,1,100,200,201,1,\n"  # middle, age=1
        "3,10,0,100,200,201,1,\n"  # youngest, age=0
    ).encode("utf-8")
    daycares = (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,capacity_age3,capacity_age4,capacity_age5\n"
        "200,D1,0,1,1,0,0,0\n"  # D1: no age-0 capacity
        "201,D2,1,0,0,0,0,0\n"  # D2: only age-0 capacity
    ).encode("utf-8")

    result = service.match(
        children_file_bytes=children,
        children_file_format="csv",
        daycares_file_bytes=daycares,
        daycares_file_format="csv",
        mapping=DEFAULT_CONFIG,
    )

    matching = result["matching_result_dict"]
    # Pattern 1 requires all or nothing — no valid same-daycare combo → all unmatched
    assert matching["1"] is None
    assert matching["2"] is None
    assert matching["3"] is None
    assert result["matched_children"]["total"] == 0
