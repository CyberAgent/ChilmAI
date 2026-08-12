"""DictBuilder の CP 入力辞書生成に関するテスト。

過去に発生した不具合の回帰テスト。
きょうだい児について `daycares_dic[d]["priority_child_id_list"]` に入る
(児童, 施設) ペアが、必ず `families_dic[f]["pref"]` の該当児童列にも存在する
という不変条件を OSS の汎用データモデルで検証する。

OSS の `DictBuilder` は priority list を family_pref のコンボ集合
（`_projected_daycare_set`）から構築しており、移植元の実装にあった
`child.pref` への fallback が存在しないため、この不変条件は構造的に保たれる。
本テストはその性質を固定し、`skip_validation` 等のバリデーション非経由パスでも
CP 側で KeyError が起きないことを担保する。
"""

from __future__ import annotations

import pandas as pd

from chilmai.constants import UNMATCHED_DAYCARE_ID
from chilmai.generic.dict_builder import DictBuilder
from chilmai.generic.family_pref_builder import FamilyPrefBuilder


def _children_df(rows: list[dict]) -> pd.DataFrame:
    """行 dict のリストから children_df を組み立て、_input_order を付与する。"""
    df = pd.DataFrame(rows)
    df["_input_order"] = range(len(df))
    return df


def _daycares_df() -> pd.DataFrame:
    ids = [100, 101, 102, 200]
    return pd.DataFrame(
        {
            "daycare_id": ids,
            "daycare_name": [f"daycare_{i}" for i in ids],
            "capacity_age0": [5] * len(ids),
            "capacity_age1": [5] * len(ids),
            "capacity_age2": [5] * len(ids),
            "capacity_age3": [5] * len(ids),
            "capacity_age4": [5] * len(ids),
            "capacity_age5": [5] * len(ids),
        }
    )


def _build_dicts(children_df: pd.DataFrame, daycares_df: pd.DataFrame) -> tuple[dict, dict]:
    pref_cols = FamilyPrefBuilder.pref_columns(children_df)
    score_cols = FamilyPrefBuilder.score_columns(children_df)
    households = FamilyPrefBuilder.build(children_df)
    base_scores = DictBuilder.build_base_scores(children_df)
    score_lookup = DictBuilder.build_score_lookup(children_df, pref_cols, score_cols)
    families_dic = DictBuilder.build_families_dic(households)
    daycares_dic = DictBuilder.build_daycares_dic(daycares_df, score_lookup, households, base_scores)
    return families_dic, daycares_dic


def _assert_priority_pref_invariant(families_dic: dict, daycares_dic: dict) -> None:
    """きょうだい児の (児童, 施設) priority ペアが families_dic.pref に存在することを確認。"""
    # child_id -> (family_id, タプル位置, きょうだいか)
    child_pos: dict[int, tuple[int, int, bool]] = {}
    for f_id, fam in families_dic.items():
        is_sibling = len(fam["children"]) > 1
        for i, c_id in enumerate(fam["children"]):
            child_pos[c_id] = (f_id, i, is_sibling)

    for d_id, daycare in daycares_dic.items():
        for c_id in daycare["priority_child_id_list"]:
            f_id, pos, is_sibling = child_pos[c_id]
            if not is_sibling:
                continue
            allowed = {combo[pos] for combo in families_dic[f_id]["pref"]}
            assert d_id in allowed, (
                f"児童 {c_id} が daycare {d_id} の priority に入っているが、"
                f"families_dic[{f_id}].pref の位置 {pos} に {d_id} が無い（allowed={allowed}）"
            )


def test_sibling_priority_invariant_holds_without_common_preference():
    """きょうだいに共通希望施設が無い（転園あり）場合でも不変条件が保たれ、
    family_pref に現れない児童・施設ペアが priority に混入しないこと。"""
    children_df = _children_df(
        [
            {
                "child_id": 1,
                "household_id": 10,
                "age": 2,
                "enrolled_daycare_id": 200,
                "sibling_pattern": 1,
                "score_1": 100,
                "pref_1": 100,
                "pref_2": None,
            },
            {
                "child_id": 2,
                "household_id": 10,
                "age": 0,
                "enrolled_daycare_id": None,
                "sibling_pattern": 1,
                "score_1": 100,
                "pref_1": 101,
                "pref_2": 102,
            },
        ]
    )
    families_dic, daycares_dic = _build_dicts(children_df, _daycares_df())

    _assert_priority_pref_invariant(families_dic, daycares_dic)

    # 共通希望が無いため child 2 はどの保育所 priority にも入らない
    # （main の child.pref fallback バグがあれば 101/102 に混入していた）。
    for d_id in (100, 101, 102):
        assert 2 not in daycares_dic[d_id]["priority_child_id_list"]


def test_sibling_priority_invariant_holds_normal_case():
    """共通希望施設がある通常のきょうだいケースでも不変条件が保たれること。"""
    children_df = _children_df(
        [
            {
                "child_id": 1,
                "household_id": 10,
                "age": 2,
                "enrolled_daycare_id": None,
                "sibling_pattern": 1,
                "score_1": 100,
                "pref_1": 100,
                "pref_2": 101,
            },
            {
                "child_id": 2,
                "household_id": 10,
                "age": 0,
                "enrolled_daycare_id": None,
                "sibling_pattern": 1,
                "score_1": 100,
                "pref_1": 100,
                "pref_2": 101,
            },
        ]
    )
    families_dic, daycares_dic = _build_dicts(children_df, _daycares_df())

    _assert_priority_pref_invariant(families_dic, daycares_dic)

    # 共通希望（100, 101）には両児が priority に入る。
    assert {1, 2}.issubset(set(daycares_dic[100]["priority_child_id_list"]))
    assert families_dic[10]["pref"][0][0] != UNMATCHED_DAYCARE_ID


def test_single_child_priority_built_from_preferences():
    """一人っ子は希望列から priority が構築され、変更の影響を受けないこと。"""
    children_df = _children_df(
        [
            {
                "child_id": 1,
                "household_id": 20,
                "age": 1,
                "enrolled_daycare_id": None,
                "sibling_pattern": None,
                "score_1": 100,
                "pref_1": 100,
                "pref_2": 101,
            },
        ]
    )
    families_dic, daycares_dic = _build_dicts(children_df, _daycares_df())

    assert len(families_dic[20]["children"]) == 1
    assert 1 in daycares_dic[100]["priority_child_id_list"]
    assert 1 in daycares_dic[101]["priority_child_id_list"]
    # 希望外の施設には入らない。
    assert 1 not in daycares_dic[102]["priority_child_id_list"]
