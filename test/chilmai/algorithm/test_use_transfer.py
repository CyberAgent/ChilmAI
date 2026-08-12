"""`is_use_transfer` フラグと転園アウト枠の加算が整合することを検証するテスト。

`is_use_transfer[age]` は「在園児が占める枠を転園アウト時に他の児童へ再配分するか」
を年齢別に切り替える。`False` のとき、`update_daycares_attributes` は在園先の
`total_numbers[age]` を加算せず、`CP_Daycare.update_priority_age_dic` /
`update_priority_age_share_dic` は在園児を優先順位辞書から除外する。この 2 つは
対で成立していないと定員が合わなくなるため、まとめて固定する。
"""

from __future__ import annotations

from collections.abc import Sequence

from chilmai.algorithm.cp_use_transfer.CP_agents import CP_Child, CP_Daycare
from chilmai.algorithm.cp_use_transfer.helper_functions import check_bp, create_agents
from chilmai.constants import UNMATCHED_DAYCARE_ID


def _daycare_agent(d_id: int, daycares: list[CP_Daycare]) -> CP_Daycare:
    """daycares から指定 ID の保育所を返す。見つからなければ StopIteration。"""
    return next(d for d in daycares if d.id == d_id)


def _child_agent(c_id: int, children: list[CP_Child]) -> CP_Child:
    """children から指定 ID の児童を返す。見つからなければ StopIteration。"""
    return next(c for c in children if c.id == c_id)


RECRUITING = 2
ENROLLED_CHILD_ID = 1
APPLICANT_CHILD_ID = 2
OTHER_AGE_CHILD_ID = 3
DAYCARE_ID = 100
OTHER_DAYCARE_ID = 101
AGE = 1
OTHER_AGE = 2


def _dicts(
    is_use_transfer: Sequence[object], with_other_age_child: bool = False
) -> tuple[dict, dict, dict]:
    """1 歳児 2 人（うち 1 人は DAYCARE_ID に在園中）の最小構成を組み立てる。

    `with_other_age_child` を True にすると、DAYCARE_ID に在園中の OTHER_AGE 児を
    1 人加える。年齢別の切り替えを検証するテストは、この児童がいないと
    「他年齢は在園児ゼロ同士の比較」になり実装を素通りさせてしまう。
    """
    children_dic = {
        ENROLLED_CHILD_ID: {
            "id": ENROLLED_CHILD_ID,
            "age": AGE,
            "family_id": ENROLLED_CHILD_ID,
            "initial_daycare_id": DAYCARE_ID,
            "preference_list": [OTHER_DAYCARE_ID, DAYCARE_ID],
        },
        APPLICANT_CHILD_ID: {
            "id": APPLICANT_CHILD_ID,
            "age": AGE,
            "family_id": APPLICANT_CHILD_ID,
            "initial_daycare_id": None,
            "preference_list": [DAYCARE_ID],
        },
    }
    if with_other_age_child:
        children_dic[OTHER_AGE_CHILD_ID] = {
            "id": OTHER_AGE_CHILD_ID,
            "age": OTHER_AGE,
            "family_id": OTHER_AGE_CHILD_ID,
            "initial_daycare_id": DAYCARE_ID,
            "preference_list": [OTHER_DAYCARE_ID, DAYCARE_ID],
        }

    def _daycare(d_id: int, priority: list[int]) -> dict:
        return {
            "id": d_id,
            "recruiting_numbers_list": [RECRUITING] * 6,
            "share_ages_list": [],
            "priority_child_id_list": priority,
            "priority_score_list": [10 for _ in priority],
            "is_use_transfer": is_use_transfer,
        }

    extra = [OTHER_AGE_CHILD_ID] if with_other_age_child else []
    daycares_dic = {
        DAYCARE_ID: _daycare(DAYCARE_ID, [ENROLLED_CHILD_ID, APPLICANT_CHILD_ID, *extra]),
        OTHER_DAYCARE_ID: _daycare(OTHER_DAYCARE_ID, [ENROLLED_CHILD_ID, *extra]),
    }

    families_dic = {
        c_id: {
            "id": c_id,
            "children": [c_id],
            "pref": list(c["preference_list"]),
        }
        for c_id, c in children_dic.items()
    }
    return children_dic, daycares_dic, families_dic


def test_use_transfer_true_releases_the_enrolled_seat():
    """True のとき、在園児の枠が定員に加算され、優先順位辞書にも残る。"""
    children, daycares, _ = create_agents(*_dicts([True] * 6))
    d = _daycare_agent(DAYCARE_ID, daycares)

    assert d.recruiting_numbers[AGE] == RECRUITING
    assert d.total_numbers[AGE] == RECRUITING + 1
    assert d.priority_age_dic[AGE] == [ENROLLED_CHILD_ID, APPLICANT_CHILD_ID]
    assert d.priority_age_share_dic[AGE] == [ENROLLED_CHILD_ID, APPLICANT_CHILD_ID]

    # 在園先以外は加算されない
    other = _daycare_agent(OTHER_DAYCARE_ID, daycares)
    assert other.total_numbers[AGE] == RECRUITING

    # 在園していない児童は、どの保育所の定員にも加算しない
    applicant = _child_agent(APPLICANT_CHILD_ID, children)
    assert applicant.initial_daycare == UNMATCHED_DAYCARE_ID


def test_use_transfer_false_keeps_the_enrolled_seat():
    """False のとき、定員が加算されず、在園児が優先順位辞書から除外される。"""
    is_use_transfer = [True] * 6
    is_use_transfer[AGE] = False
    _, daycares, _ = create_agents(*_dicts(is_use_transfer))
    d = _daycare_agent(DAYCARE_ID, daycares)

    assert d.total_numbers[AGE] == RECRUITING
    assert d.priority_age_dic[AGE] == [APPLICANT_CHILD_ID]
    assert d.priority_age_share_dic[AGE] == [APPLICANT_CHILD_ID]

    # 在園先以外では除外されない（除外条件は initial_daycare == 自分自身の id）
    other = _daycare_agent(OTHER_DAYCARE_ID, daycares)
    assert other.priority_age_dic[AGE] == [ENROLLED_CHILD_ID]


def test_use_transfer_false_only_affects_the_specified_age():
    """False にした年齢以外は、加算も在園児の保持もそのまま行われる。"""
    is_use_transfer = [True] * 6
    is_use_transfer[AGE] = False
    _, daycares_false, _ = create_agents(*_dicts(is_use_transfer, with_other_age_child=True))
    _, daycares_true, _ = create_agents(*_dicts([True] * 6, with_other_age_child=True))

    d_false = _daycare_agent(DAYCARE_ID, daycares_false)
    d_true = _daycare_agent(DAYCARE_ID, daycares_true)

    # OTHER_AGE には在園児がいる。ここが空だと以下の比較が素通りしてしまう。
    assert d_false.total_numbers[OTHER_AGE] == RECRUITING + 1
    assert d_false.priority_age_dic[OTHER_AGE] == [OTHER_AGE_CHILD_ID]

    # 指定した年齢だけが変わる
    assert d_false.total_numbers[AGE] == RECRUITING
    assert d_true.total_numbers[AGE] == RECRUITING + 1

    for age in range(6):
        if age == AGE:
            continue
        assert d_false.total_numbers[age] == d_true.total_numbers[age]
        assert d_false.priority_age_dic[age] == d_true.priority_age_dic[age]


def test_use_transfer_normalizes_non_bool_flags():
    """bool 以外の真偽値でも、加算と除外が対で成立する。

    アルゴリズム側は `is True` / `is False` で判定するため、`1` や `0` のような
    リテラル以外の値が渡ると両方の分岐が成立せず、枠を増やさないまま在園児を
    競合に残してしまう。`CP_Daycare.__init__` の bool 正規化がこれを防ぐ。
    """
    truthy: list[object] = [True] * 6
    truthy[AGE] = 1
    _, daycares_truthy, _ = create_agents(*_dicts(truthy))
    d_truthy = _daycare_agent(DAYCARE_ID, daycares_truthy)

    assert d_truthy.use_transfer[AGE] is True
    assert d_truthy.total_numbers[AGE] == RECRUITING + 1
    assert d_truthy.priority_age_dic[AGE] == [ENROLLED_CHILD_ID, APPLICANT_CHILD_ID]

    falsy: list[object] = [True] * 6
    falsy[AGE] = 0
    _, daycares_falsy, _ = create_agents(*_dicts(falsy))
    d_falsy = _daycare_agent(DAYCARE_ID, daycares_falsy)

    assert d_falsy.use_transfer[AGE] is False
    assert d_falsy.total_numbers[AGE] == RECRUITING
    assert d_falsy.priority_age_dic[AGE] == [APPLICANT_CHILD_ID]


# check_bp は転園アウトで空いた枠を含む total_numbers を閾値に使う。
HIGH_PRIORITY_IDS = [10, 11, 12]
LOW_PRIORITY_ID = 13
TRANSFER_OUT_ID = 14


def _bp_dicts() -> tuple[dict, dict, dict]:
    """DAYCARE_ID の 1 歳枠を募集 2 + 転園アウト 1 = 3 とする構成を組み立てる。

    優先順位は HIGH_PRIORITY_IDS の 3 人が LOW_PRIORITY_ID より上位。
    TRANSFER_OUT_ID は DAYCARE_ID に在園中で、OTHER_DAYCARE_ID のみを希望する。
    """
    children_dic = {}
    for c_id in [*HIGH_PRIORITY_IDS, LOW_PRIORITY_ID]:
        children_dic[c_id] = {
            "id": c_id,
            "age": AGE,
            "family_id": c_id,
            "initial_daycare_id": None,
            "preference_list": [DAYCARE_ID],
        }
    children_dic[LOW_PRIORITY_ID]["preference_list"] = [DAYCARE_ID, OTHER_DAYCARE_ID]
    children_dic[TRANSFER_OUT_ID] = {
        "id": TRANSFER_OUT_ID,
        "age": AGE,
        "family_id": TRANSFER_OUT_ID,
        "initial_daycare_id": DAYCARE_ID,
        "preference_list": [OTHER_DAYCARE_ID],
    }

    priority = [*HIGH_PRIORITY_IDS, LOW_PRIORITY_ID]

    def _daycare(d_id: int, priority_ids: list[int]) -> dict:
        return {
            "id": d_id,
            "recruiting_numbers_list": [RECRUITING] * 6,
            "share_ages_list": [],
            "priority_child_id_list": priority_ids,
            "priority_score_list": list(range(len(priority_ids), 0, -1)),
            "is_use_transfer": [True] * 6,
        }

    daycares_dic = {
        DAYCARE_ID: _daycare(DAYCARE_ID, priority),
        OTHER_DAYCARE_ID: _daycare(OTHER_DAYCARE_ID, [LOW_PRIORITY_ID, TRANSFER_OUT_ID]),
    }

    families_dic = {
        c_id: {
            "id": c_id,
            "children": [c_id],
            "pref": list(children_dic[c_id]["preference_list"]),
        }
        for c_id in children_dic
    }
    return children_dic, daycares_dic, families_dic


def _outcome_f(families_dic: dict, matched_position: dict[int, int]) -> dict:
    """{family_id: 割り当てられた希望順位} から outcome_f を組み立てる。"""
    outcome = {}
    for f_id, f in families_dic.items():
        for p in range(len(f["pref"])):
            outcome[f_id, p] = 1 if matched_position.get(f_id) == p else 0
    return outcome


def test_check_bp_counts_the_seat_freed_by_a_transfer_out():
    """上位 2 人しか埋まっていない場合、3 席目が空いているので BP になる。

    閾値が素の定員（2）だと `2 + 1 > 2` が成立して BP を見逃す。
    """
    children_dic, daycares_dic, families_dic = _bp_dicts()
    d = _daycare_agent(DAYCARE_ID, create_agents(children_dic, daycares_dic, families_dic)[1])
    assert d.recruiting_numbers[AGE] == RECRUITING
    assert d.total_numbers[AGE] == RECRUITING + 1

    # 上位 3 人のうち 2 人だけが DAYCARE_ID に入所し、残る 1 人は未割当。
    # LOW_PRIORITY_ID は第 2 希望の OTHER_DAYCARE_ID に回っている。
    matched = {
        HIGH_PRIORITY_IDS[0]: 0,
        HIGH_PRIORITY_IDS[1]: 0,
        LOW_PRIORITY_ID: 1,
        TRANSFER_OUT_ID: 0,
    }
    bp_dic = check_bp(children_dic, daycares_dic, families_dic, _outcome_f(families_dic, matched))

    assert bp_dic[LOW_PRIORITY_ID] == [0]


def test_check_bp_reports_no_bp_when_all_seats_are_filled():
    """上位 3 人で 3 席とも埋まっている場合は BP にならない。"""
    children_dic, daycares_dic, families_dic = _bp_dicts()

    matched = {
        HIGH_PRIORITY_IDS[0]: 0,
        HIGH_PRIORITY_IDS[1]: 0,
        HIGH_PRIORITY_IDS[2]: 0,
        LOW_PRIORITY_ID: 1,
        TRANSFER_OUT_ID: 0,
    }
    bp_dic = check_bp(children_dic, daycares_dic, families_dic, _outcome_f(families_dic, matched))

    assert bp_dic[LOW_PRIORITY_ID] == []
