from __future__ import annotations

import pandas as pd

from chilmai.generic.family_pref_builder import FamilyPrefBuilder


def test_build_household_preference_orders_children_by_age_desc_then_child_id():
    children = pd.DataFrame(
        [
            {
                "child_id": 2,
                "household_id": 10,
                "age": 1,
                "score_1": 100,
                "pref_1": 100,
                "pref_2": 101,
                "_input_order": 1,
            },
            {
                "child_id": 1,
                "household_id": 10,
                "age": 2,
                "score_1": 100,
                "pref_1": 100,
                "pref_2": 101,
                "_input_order": 0,
            },
        ]
    )

    households = FamilyPrefBuilder.build(children)
    assert len(households) == 1
    h = households[0]
    assert h.child_ids == [1, 2]
    assert h.ages == [2, 1]
    assert h.family_pref[0] == (100, 100)


def test_build_uses_transfer_combo_when_enrolled_daycare_exists():
    children = pd.DataFrame(
        [
            {
                "child_id": 1,
                "household_id": 10,
                "age": 2,
                "score_1": 100,
                "pref_1": 100,
                "pref_2": 101,
                "enrolled_daycare_id": 101,
                "sibling_pattern": 2,
                "_input_order": 0,
            },
            {
                "child_id": 2,
                "household_id": 10,
                "age": 1,
                "score_1": 100,
                "pref_1": 100,
                "pref_2": 101,
                "enrolled_daycare_id": None,
                "sibling_pattern": 2,
                "_input_order": 1,
            },
        ]
    )

    households = FamilyPrefBuilder.build(children)
    h = households[0]
    # transfer() puts current tuple at the end
    assert h.family_pref[-1] == (101, None)


def test_build_score_map_uses_score_n_per_pref():
    children = pd.DataFrame(
        [
            {
                "child_id": 1,
                "household_id": 10,
                "age": 1,
                "score_1": 100,
                "score_2": 90,
                "pref_1": 200,
                "pref_2": 201,
                "_input_order": 0,
            }
        ]
    )

    households = FamilyPrefBuilder.build(children)
    h = households[0]
    assert h.score_map[(1, 200)] == 100
    assert h.score_map[(1, 201)] == 90


def test_build_score_map_falls_back_to_score_1_when_score_n_missing():
    children = pd.DataFrame(
        [
            {
                "child_id": 1,
                "household_id": 10,
                "age": 1,
                "score_1": 100,
                "pref_1": 200,
                "pref_2": 201,
                "_input_order": 0,
            }
        ]
    )

    households = FamilyPrefBuilder.build(children)
    h = households[0]
    # No score_2 column → both prefs use score_1 as fallback
    assert h.score_map[(1, 200)] == 100
    assert h.score_map[(1, 201)] == 100


def test_build_score_map_falls_back_to_score_1_when_score_n_is_nan():
    children = pd.DataFrame(
        [
            {
                "child_id": 1,
                "household_id": 10,
                "age": 1,
                "score_1": 100,
                "score_2": float("nan"),
                "pref_1": 200,
                "pref_2": 201,
                "_input_order": 0,
            }
        ]
    )

    households = FamilyPrefBuilder.build(children)
    h = households[0]
    assert h.score_map[(1, 200)] == 100
    assert h.score_map[(1, 201)] == 100  # score_2 is NaN → falls back to score_1


def test_to_pref_list_removes_duplicate_daycare_ids():
    """重複した daycare_id は除去され、最初の出現のみが残ること。"""
    row = pd.Series({"pref_1": 101, "pref_2": 101, "pref_3": 102})
    pref_cols = ["pref_1", "pref_2", "pref_3"]

    result = FamilyPrefBuilder._to_pref_list(row, pref_cols)

    assert result == [101, 102]


def test_to_pref_list_preserves_order_after_deduplication():
    """重複除去後も希望順位（最初の出現順）が保持されること。"""
    row = pd.Series({"pref_1": 201, "pref_2": 202, "pref_3": 201, "pref_4": 203})
    pref_cols = ["pref_1", "pref_2", "pref_3", "pref_4"]

    result = FamilyPrefBuilder._to_pref_list(row, pref_cols)

    assert result == [201, 202, 203]


def _sibling_df(
    *,
    older_pref: list[int],
    younger_pref: list[int],
    older_enrolled: int | None = None,
    younger_enrolled: int | None = None,
    pattern: int = 2,
) -> pd.DataFrame:
    """パターン検証用のきょうだい2人 DataFrame を生成するヘルパー。"""
    row_older: dict = {
        "child_id": 1,
        "household_id": 10,
        "age": 3,
        "score_1": 100,
        "enrolled_daycare_id": older_enrolled,
        "sibling_pattern": pattern,
        "_input_order": 0,
    }
    for i, p in enumerate(older_pref, 1):
        row_older[f"pref_{i}"] = p

    row_younger: dict = {
        "child_id": 2,
        "household_id": 10,
        "age": 1,
        "score_1": 100,
        "enrolled_daycare_id": younger_enrolled,
        "sibling_pattern": pattern,
        "_input_order": 1,
    }
    for i, p in enumerate(younger_pref, 1):
        row_younger[f"pref_{i}"] = p

    return pd.DataFrame([row_older, row_younger])


# --- 転園児の enrolled_daycare がきょうだいコンボに含まれるか ---


def test_sibling_pattern2_younger_transfer_generates_cross_combo():
    """パターン2: 下の子が転園児（enrolled が pref にない）の場合、
    「上→新施設・下→転園元」コンボが生成されること。

    修正前は pref_li に enrolled_daycare が含まれず (804, 515) が
    生成できなかったため、上の子が未マッチになるバグがあった。
    """
    h = FamilyPrefBuilder.build(
        _sibling_df(older_pref=[804], younger_pref=[804], younger_enrolled=515, pattern=2)
    )[0]
    assert (804, 515) in h.family_pref


def test_sibling_enrolled_already_in_pref_no_duplicate():
    """enrolled_daycare が既に pref_li に含まれる場合は重複追加されないこと。"""
    # younger の pref=[804, 515]、enrolled=515 → pref_li_with_transfer は変わらない
    h = FamilyPrefBuilder.build(
        _sibling_df(older_pref=[804], younger_pref=[804, 515], younger_enrolled=515, pattern=2)
    )[0]
    assert h.family_pref.count((804, 515)) == 1


def test_sibling_pattern1_younger_transfer_no_cross_combo():
    """パターン1（同保同時）では eff に None が含まれるコンボは無効のため、
    転園元が追加されても「上→新施設・下→転園元」コンボは生成されないこと。

    (804, 515) → eff(804, None): 同一施設条件を満たさない。
    """
    h = FamilyPrefBuilder.build(
        _sibling_df(older_pref=[804], younger_pref=[804], younger_enrolled=515, pattern=1)
    )[0]
    assert (804, 515) not in h.family_pref
    assert (804, 804) in h.family_pref  # 同一施設コンボは有効


def test_sibling_pattern3_younger_transfer_cross_combo_excluded():
    """パターン3（同保順次・下）では「下が転園元かつ新施設あり」は除外されるため、
    「上→新施設・下→転園元」コンボは生成されないこと。

    (804, 515): comb[-1]=515=enrolled かつ new_daycares={804} → 除外ルールに該当。
    """
    h = FamilyPrefBuilder.build(
        _sibling_df(older_pref=[804], younger_pref=[804], younger_enrolled=515, pattern=3)
    )[0]
    assert (804, 515) not in h.family_pref


def test_sibling_pattern5_younger_transfer_generates_cross_combo():
    """パターン5（別保順次）でも「上→新施設・下→転園元」コンボが生成されること。

    eff(804, None): 上の子が新施設 804 に入所（eff[0] ≠ None）するため
    「少なくとも1人入所」条件を満たす。下の子は転園元 515 に戻る（None 扱い）。
    """
    h = FamilyPrefBuilder.build(
        _sibling_df(older_pref=[804], younger_pref=[804], younger_enrolled=515, pattern=5)
    )[0]
    assert (804, 515) in h.family_pref


def test_sibling_pattern4_younger_transfer_no_cross_combo():
    """パターン4（別保同時）では全員入所必須のため、
    「上→新施設・下→転園元」コンボは生成されないこと。

    (804, 515) → eff(804, None): None が含まれるため全員入所条件を満たさない。
    """
    h = FamilyPrefBuilder.build(
        _sibling_df(older_pref=[804], younger_pref=[804], younger_enrolled=515, pattern=4)
    )[0]
    assert (804, 515) not in h.family_pref
    assert (804, 804) in h.family_pref  # 全員入所コンボは有効


def test_sibling_pattern6_younger_transfer_no_cross_combo():
    """パターン6（別保同時（希））でも全員入所必須のため、
    「上→新施設・下→転園元」コンボは生成されないこと。

    パターン4と同じフィルタリング（スコアのみ異なる）。
    """
    h = FamilyPrefBuilder.build(
        _sibling_df(older_pref=[804], younger_pref=[804], younger_enrolled=515, pattern=6)
    )[0]
    assert (804, 515) not in h.family_pref
    assert (804, 804) in h.family_pref  # 全員入所コンボは有効


def test_sibling_pattern7_younger_transfer_generates_cross_combo():
    """パターン7（別保順次（希））では「上→新施設・下→転園元」コンボが生成されること。

    パターン5と同じフィルタリング（少なくとも1人入所）のため、
    eff(804, None): 上が入所しているため有効。
    """
    h = FamilyPrefBuilder.build(
        _sibling_df(older_pref=[804], younger_pref=[804], younger_enrolled=515, pattern=7)
    )[0]
    assert (804, 515) in h.family_pref


def test_resolve_sibling_pattern_defaults_to_1_when_column_absent():
    """sibling_pattern列がない場合のデフォルトは1（同保同時）。"""
    df = pd.DataFrame([{"child_id": 1, "household_id": 10, "age": 2}])
    assert FamilyPrefBuilder._resolve_sibling_pattern(df) == 1


def test_resolve_sibling_pattern_defaults_to_1_when_all_blank():
    """sibling_pattern列があるが全行NaN/空欄の場合のデフォルトは1。"""
    df = pd.DataFrame(
        [
            {"child_id": 1, "household_id": 10, "age": 2, "sibling_pattern": None},
            {"child_id": 2, "household_id": 10, "age": 1, "sibling_pattern": float("nan")},
        ]
    )
    assert FamilyPrefBuilder._resolve_sibling_pattern(df) == 1


def test_resolve_sibling_pattern_defaults_to_1_when_out_of_range():
    """範囲外の値（8など）はバリデーターが弾くが、すり抜けた場合もデフォルト1。"""
    df = pd.DataFrame([{"child_id": 1, "household_id": 10, "age": 2, "sibling_pattern": 8}])
    assert FamilyPrefBuilder._resolve_sibling_pattern(df) == 1


def test_build_score_map_uses_first_occurrence_score_when_pref_duplicated():
    """pref_1 == pref_2 のとき score_map には pref_1 のスコアが使われること。

    pref_1=101 (score_1=100), pref_2=101 (score_2=0) という入力で
    重複除去なしだと score_map[(1, 101)] == 0 になってしまう（後勝ち）。
    earliest-win で score_map[(1, 101)] == 100 でなければならない。
    """
    children = pd.DataFrame(
        [
            {
                "child_id": 1,
                "household_id": 10,
                "age": 1,
                "score_1": 100,
                "score_2": 0,
                "pref_1": 101,
                "pref_2": 101,
                "_input_order": 0,
            }
        ]
    )

    households = FamilyPrefBuilder.build(children)
    h = households[0]
    assert h.score_map[(1, 101)] == 100


# ---------------------------------------------------------------------------
# 任意きょうだい組み合わせ（別ファイル方式 / combination_df）
# ---------------------------------------------------------------------------


def _combo_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_build_from_combination_data_two_children():
    """combination_df があれば family_pref を組み合わせファイルから構築する。"""
    children = pd.DataFrame(
        [
            {
                "child_id": 1,
                "household_id": 10,
                "age": 2,
                "score_1": 100,
                "pref_1": 100,
                "enrolled_daycare_id": None,
                "sibling_pattern": 1,
                "_input_order": 0,
            },
            {
                "child_id": 2,
                "household_id": 10,
                "age": 1,
                "score_1": 100,
                "pref_1": 101,
                "enrolled_daycare_id": None,
                "sibling_pattern": 1,
                "_input_order": 1,
            },
        ]
    )
    combo = _combo_df(
        [
            {
                "household_id": "10",
                "rank": "1",
                "child_code_0": "1",
                "child_code_1": "2",
                "facility_0": "100",
                "facility_1": "101",
            },
            {
                "household_id": "10",
                "rank": "2",
                "child_code_0": "1",
                "child_code_1": "2",
                "facility_0": "101",
                "facility_1": "100",
            },
        ]
    )

    households = FamilyPrefBuilder.build(children, combination_df=combo)
    assert len(households) == 1
    h = households[0]
    assert (100, 101) in h.family_pref
    assert (101, 100) in h.family_pref
    assert h.family_pref.index((100, 101)) < h.family_pref.index((101, 100))


def test_build_from_combination_data_position_mapping():
    """age-sort で並び替えても宛名コードで child_id を照合して正しい位置に割り当てる。"""
    # child_id=1 が age=1（下の子）、child_id=2 が age=2（上の子）
    # age-sort 後: [child_id=2, child_id=1]（pos 0=2, pos 1=1）
    children = pd.DataFrame(
        [
            {
                "child_id": 1,
                "household_id": 10,
                "age": 1,
                "score_1": 100,
                "pref_1": 100,
                "enrolled_daycare_id": None,
                "sibling_pattern": 1,
                "_input_order": 0,
            },
            {
                "child_id": 2,
                "household_id": 10,
                "age": 2,
                "score_1": 100,
                "pref_1": 101,
                "enrolled_daycare_id": None,
                "sibling_pattern": 1,
                "_input_order": 1,
            },
        ]
    )
    # combo: child 1 → 施設200, child 2 → 施設300
    combo = _combo_df(
        [
            {
                "household_id": "10",
                "rank": "1",
                "child_code_0": "1",
                "child_code_1": "2",
                "facility_0": "200",
                "facility_1": "300",
            },
        ]
    )

    households = FamilyPrefBuilder.build(children, combination_df=combo)
    h = households[0]
    # age-sort 後 pos 0=child2(300), pos 1=child1(200) → tuple=(300, 200)
    assert (300, 200) in h.family_pref


def test_build_from_combination_data_empty_facility_is_none():
    """組み合わせファイルの空欄 facility は None になる。"""
    import numpy as np

    children = pd.DataFrame(
        [
            {
                "child_id": 1,
                "household_id": 10,
                "age": 2,
                "score_1": 100,
                "pref_1": 100,
                "enrolled_daycare_id": None,
                "sibling_pattern": 1,
                "_input_order": 0,
            },
            {
                "child_id": 2,
                "household_id": 10,
                "age": 1,
                "score_1": 100,
                "pref_1": 101,
                "enrolled_daycare_id": None,
                "sibling_pattern": 1,
                "_input_order": 1,
            },
        ]
    )
    combo = _combo_df(
        [
            {
                "household_id": "10",
                "rank": "1",
                "child_code_0": "1",
                "child_code_1": "2",
                "facility_0": "100",
                "facility_1": np.nan,
            },
        ]
    )

    households = FamilyPrefBuilder.build(children, combination_df=combo)
    h = households[0]
    assert (100, None) in h.family_pref


def test_build_combination_df_none_fallback_to_sibling_pattern():
    """combination_df=None のとき sibling_pattern 1 の動作が変わらない。"""
    children = pd.DataFrame(
        [
            {
                "child_id": 1,
                "household_id": 10,
                "age": 2,
                "score_1": 100,
                "pref_1": 100,
                "pref_2": 101,
                "enrolled_daycare_id": None,
                "sibling_pattern": 1,
                "_input_order": 0,
            },
            {
                "child_id": 2,
                "household_id": 10,
                "age": 1,
                "score_1": 100,
                "pref_1": 100,
                "pref_2": 101,
                "enrolled_daycare_id": None,
                "sibling_pattern": 1,
                "_input_order": 1,
            },
        ]
    )

    households = FamilyPrefBuilder.build(children, combination_df=None)
    h = households[0]
    assert h.family_pref == [(100, 100), (101, 101)]


def test_build_household_not_in_combo_df_uses_sibling_pattern():
    """combination_df にいない世帯は sibling_pattern 1–7 で生成される。"""
    children = pd.DataFrame(
        [
            {
                "child_id": 1,
                "household_id": 10,
                "age": 2,
                "score_1": 100,
                "pref_1": 100,
                "pref_2": 101,
                "enrolled_daycare_id": None,
                "sibling_pattern": 1,
                "_input_order": 0,
            },
            {
                "child_id": 2,
                "household_id": 10,
                "age": 1,
                "score_1": 100,
                "pref_1": 100,
                "pref_2": 101,
                "enrolled_daycare_id": None,
                "sibling_pattern": 1,
                "_input_order": 1,
            },
        ]
    )
    # combo_df は別の世帯のみ
    combo = _combo_df(
        [
            {
                "household_id": "99",
                "rank": "1",
                "child_code_0": "9",
                "child_code_1": "8",
                "facility_0": "500",
                "facility_1": "501",
            },
        ]
    )

    households = FamilyPrefBuilder.build(children, combination_df=combo)
    h = households[0]
    assert h.family_pref == [(100, 100), (101, 101)]
