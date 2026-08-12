"""正規化済み ChilmAI DataFrame 用の CP-SAT マッチャー。"""

from __future__ import annotations

import re
from collections import Counter
from logging import getLogger
from typing import Any

import pandas as pd
from ortools.sat.python import cp_model

from chilmai.algorithm.cp_use_transfer.CP_algo import CP, OptimizationFailureError
from chilmai.algorithm.cp_use_transfer.helper_functions import check_outcome
from chilmai.constants import UNMATCHED_DAYCARE_ID
from chilmai.generic.dict_builder import DictBuilder
from chilmai.generic.error_codes import ErrorCode
from chilmai.generic.family_pref_builder import FamilyPrefBuilder

_DATA_ISSUE_MSG = (
    "入力データに問題がある可能性があります。以下をご確認ください:\n"
    "  ・申請者の点数設定\n"
    "  ・きょうだいパターンの設定\n"
    "  ・各保育所の募集人数\n"
    "解決しない場合は開発者にお問い合わせください。"
)
_SOLVER_FEASIBLE = cp_model.FEASIBLE  # 実行可能解あり（最適解未達）
_SOLVER_INFEASIBLE = cp_model.INFEASIBLE  # 実行不可能

# 利用者向けメッセージにはソルバーのステータス名を出さず、調査用にログへ残す。
log = getLogger("chilmai.matching")


def norm_id(s: str) -> str:
    """ID文字列を正規化する。pandas が float として読んだ整数 ('11005.0') を '11005' に変換する。
    ゼロパディング ('0000000001') は変換しない。数値以外の ID ('A.0') は変換しない。
    """
    stripped = s.strip()
    if re.fullmatch(r"-?\d+\.0+", stripped):
        return re.sub(r"\.0+$", "", stripped)
    return stripped


class _IdMapper:
    """外部ID（文字列・ゼロパディング・整数）↔ 内部連番整数 の双方向マッピング。

    CPアルゴリズムは整数IDを必要とするため、外部IDを1始まりの連番整数に変換し、
    出力時に元のID文字列へ復元する。
    """

    def __init__(self, original_ids: list[str]) -> None:
        self._orig_to_int: dict[str, int] = {}
        self._int_to_orig: dict[int, str] = {}
        for i, oid in enumerate(dict.fromkeys(norm_id(s) for s in original_ids), start=1):
            self._orig_to_int[oid] = i
            self._int_to_orig[i] = oid

    def to_int(self, original: object) -> int:
        return self._orig_to_int[norm_id(str(original))]

    def to_orig(self, internal: int) -> str:
        return self._int_to_orig[internal]

    def apply_series(self, series: pd.Series) -> pd.Series:
        return series.map(lambda v: self._orig_to_int[norm_id(str(v))])


class CpSatMatcher:
    """OR-Tools CP-SAT ベースの保育所利用調整アルゴリズムを実行する。"""

    @staticmethod
    def _pref_columns(children_df: pd.DataFrame) -> list[str]:
        cols = [c for c in children_df.columns if isinstance(c, str) and re.fullmatch(r"pref_\d+", c)]
        return sorted(cols, key=lambda c: int(c.split("_")[1]))

    @classmethod
    def _normalize_frames(
        cls,
        children_df: pd.DataFrame,
        daycares_df: pd.DataFrame,
    ) -> tuple[
        pd.DataFrame, pd.DataFrame, list[str], dict[int, dict[int, int]], _IdMapper, _IdMapper, _IdMapper
    ]:
        children = children_df.copy().reset_index(drop=False).rename(columns={"index": "_input_order"})
        daycares = daycares_df.copy()

        child_mapper = _IdMapper(children["child_id"].astype(str).tolist())
        household_mapper = _IdMapper(children["household_id"].astype(str).tolist())
        daycare_mapper = _IdMapper(daycares["daycare_id"].astype(str).tolist())

        children["child_id"] = child_mapper.apply_series(children["child_id"])
        children["household_id"] = household_mapper.apply_series(children["household_id"])
        children["age"] = pd.to_numeric(children["age"]).astype(int)
        daycares["daycare_id"] = daycare_mapper.apply_series(daycares["daycare_id"])

        pref_cols = cls._pref_columns(children)
        for col in pref_cols:
            children[col] = children[col].map(
                lambda v: daycare_mapper.to_int(v) if pd.notna(v) and norm_id(str(v)) != "" else None
            )

        if "enrolled_daycare_id" in children.columns:
            children["enrolled_daycare_id"] = children["enrolled_daycare_id"].map(
                lambda v: daycare_mapper.to_int(v) if pd.notna(v) and norm_id(str(v)) != "" else None
            )

        capacities: dict[int, dict[int, int]] = {}
        for _, row in daycares.iterrows():
            daycare_id = int(row["daycare_id"])
            capacities[daycare_id] = {
                age: int(pd.to_numeric(row[f"capacity_age{age}"])) for age in range(6)
            }
        return children, daycares, pref_cols, capacities, child_mapper, household_mapper, daycare_mapper

    @staticmethod
    def _init_child_assignments(children: pd.DataFrame) -> dict[int, int | None]:
        assignments: dict[int, int | None] = {}
        for _, row in children.iterrows():
            assignments[int(row["child_id"])] = None
        return assignments

    @staticmethod
    def _build_result(
        children: pd.DataFrame,
        assignments: dict[int, int | None],
        household_result_dict: dict[int, dict[str, Any]],
    ) -> dict[str, Any]:
        children = children.copy()
        household_counts = Counter(children["household_id"].tolist())
        applied_total = 0
        matched_total = 0
        matched_only = 0
        matched_siblings = 0
        by_age: dict[str, dict[str, int]] = {str(age): {"applied": 0, "matched": 0} for age in range(6)}
        for _, row in children.iterrows():
            cid = int(row["child_id"])
            hid = int(row["household_id"])
            age_key = str(int(row["age"]))
            is_only = household_counts[hid] == 1
            applied_total += 1
            bucket = by_age.setdefault(age_key, {"applied": 0, "matched": 0})
            bucket["applied"] += 1
            if assignments[cid] is not None:
                matched_total += 1
                if is_only:
                    matched_only += 1
                else:
                    matched_siblings += 1
                bucket["matched"] += 1

        return {
            "matching_result_dict": assignments,
            "household_result_dict": household_result_dict,
            "matched_children": {
                "total": matched_total,
                "only_child": matched_only,
                "siblings": matched_siblings,
                "applied_total": applied_total,
                "by_age": by_age,
            },
            "meta": {
                "algorithm": "cp_use_transfer",
            },
        }

    def _match_cp(
        self,
        children_df: pd.DataFrame,
        daycares_df: pd.DataFrame,
        *,
        max_time_seconds: float = 360.0,
        combination_df: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        children, daycares, pref_cols, _, child_mapper, household_mapper, daycare_mapper = (
            self._normalize_frames(children_df, daycares_df)
        )
        score_cols = FamilyPrefBuilder.score_columns(children)

        # combination_df の外部IDを内部連番IDに変換してから FamilyPrefBuilder へ渡す。
        # _normalize_frames() で children/daycares は内部IDに変換済みのため、
        # 変換前の外部IDのまま渡すと世帯照合がすべて失敗する。
        normalized_combo: pd.DataFrame | None = None
        if combination_df is not None:
            normalized_combo = combination_df.copy()
            normalized_combo["household_id"] = normalized_combo["household_id"].map(
                lambda v: household_mapper.to_int(v) if pd.notna(v) and norm_id(str(v)) != "" else None
            )
            for col in [c for c in normalized_combo.columns if re.fullmatch(r"child_code_\d+", c)]:
                normalized_combo[col] = normalized_combo[col].map(
                    lambda v: child_mapper.to_int(v) if pd.notna(v) and norm_id(str(v)) != "" else None
                )
            for col in [c for c in normalized_combo.columns if re.fullmatch(r"facility_\d+", c)]:
                normalized_combo[col] = normalized_combo[col].map(
                    lambda v: daycare_mapper.to_int(v) if pd.notna(v) and norm_id(str(v)) != "" else None
                )
        households = FamilyPrefBuilder.build(children, combination_df=normalized_combo)

        children_dic = DictBuilder.build_children_dic(children, pref_cols)
        base_scores = DictBuilder.build_base_scores(children)
        score_lookup = DictBuilder.build_score_lookup(children, pref_cols, score_cols)
        daycares_dic = DictBuilder.build_daycares_dic(
            daycares,
            score_lookup,
            households,
            base_scores,
        )
        families_dic = DictBuilder.build_families_dic(households)

        bp_num = 0  # ブロッキングペアは自治体ルール上常に0（許容しない）
        solver_time = max_time_seconds
        _retried = False

        while True:
            try:
                outcome_children_dic, outcome_fp, _, _, _, solver_status = CP(
                    children_dic,
                    daycares_dic,
                    families_dic,
                    share_bool=False,
                    bp_num=bp_num,
                    solver_time=solver_time,
                    exclude_bool=True,
                    search_depth=0,
                )
            except OptimizationFailureError as e:
                # CP_algo.py を変更せずにコードを付与するため、動的属性として設定する
                raw_status = e.args[0]
                if raw_status == _SOLVER_INFEASIBLE:
                    err = OptimizationFailureError(
                        f"マッチングが実行不可能です（INFEASIBLE）。{_DATA_ISSUE_MSG}"
                    )
                    err.code = ErrorCode.SOLVER_INFEASIBLE
                    raise err from e
                err = OptimizationFailureError(
                    f"ソルバーが予期しない状態で終了しました（ステータス: {raw_status}）。{_DATA_ISSUE_MSG}"
                )
                err.code = ErrorCode.SOLVER_UNEXPECTED_STATUS
                raise err from e

            if solver_status == _SOLVER_FEASIBLE:
                # 最適解未達（時間切れ）: 制限時間を10倍にして1回だけ再試行する
                if _retried:
                    log.warning(
                        "CP-SAT が制限時間内に最適解へ到達しませんでした"
                        f"（ステータス: FEASIBLE / 制限時間: {solver_time}秒）"
                    )
                    err = OptimizationFailureError(
                        f"制限時間内にマッチング結果が確定しませんでした。{_DATA_ISSUE_MSG}"
                    )
                    err.code = ErrorCode.SOLVER_TIMEOUT
                    raise err  # 起点となる例外がないため from なし
                solver_time = max_time_seconds * 10
                _retried = True
                continue

            # OPTIMAL — 解の妥当性を検証する（個人合理性・定員・ブロッキングペア）
            non_IR_children, infeasible_daycare_ids, bp_dic = check_outcome(
                children_dic,
                daycares_dic,
                families_dic,
                outcome_children_dic,
                outcome_fp,
                share_bool=False,
            )
            num_bp = sum(len(v) for v in bp_dic.values())
            if non_IR_children or infeasible_daycare_ids or num_bp > 0:
                if _retried:
                    err = OptimizationFailureError(
                        "マッチング結果の妥当性検証に失敗しました"
                        f"（IR違反: {len(non_IR_children)}件 / 定員違反: {len(infeasible_daycare_ids)}件 / "
                        f"ブロッキングペア: {num_bp}件）。{_DATA_ISSUE_MSG}"
                    )
                    err.code = ErrorCode.SOLVER_VERIFICATION_FAILED
                    raise err
                solver_time = max_time_seconds * 10
                _retried = True
                continue

            break  # OPTIMAL かつ検証OK

        assignments_internal = self._init_child_assignments(children)
        for c_id, v in outcome_children_dic.items():
            assigned = v["CP"]
            assignments_internal[c_id] = None if assigned == UNMATCHED_DAYCARE_ID else assigned

        household_result_dict_internal: dict[int, dict[str, Any]] = {}
        for h in households:
            f_id = h.household_id
            selected_idx: int | None = None
            for p in range(len(h.family_pref)):
                if outcome_fp.get((f_id, p), 0) == 1:
                    selected_idx = p
                    break

            if selected_idx is not None:
                selected_combo = list(h.family_pref[selected_idx])
            else:
                selected_combo = [None] * len(h.child_ids)

            household_result_dict_internal[f_id] = {
                "household_id": f_id,
                "child_ids": h.child_ids,
                "assigned": selected_combo,
                "selected_combo": selected_combo,
                "combo_rank": (selected_idx + 1) if selected_idx is not None else None,
            }

        result = self._build_result(children, assignments_internal, household_result_dict_internal)
        result["meta"]["is_optimal"] = True

        # 内部整数IDを元のID文字列に復元する
        result["matching_result_dict"] = {
            child_mapper.to_orig(c_id): (None if d_id is None else daycare_mapper.to_orig(d_id))
            for c_id, d_id in assignments_internal.items()
        }
        result["household_result_dict"] = {
            household_mapper.to_orig(f_id): {
                "household_id": household_mapper.to_orig(f_id),
                "child_ids": [child_mapper.to_orig(c) for c in entry["child_ids"]],
                "assigned": [
                    None if d is None else daycare_mapper.to_orig(d) for d in entry["selected_combo"]
                ],
                "selected_combo": [
                    None if d is None else daycare_mapper.to_orig(d) for d in entry["selected_combo"]
                ],
                "combo_rank": entry["combo_rank"],
            }
            for f_id, entry in household_result_dict_internal.items()
        }

        daycare_name_dict: dict[str, str] = {}
        if "daycare_name" in daycares_df.columns:
            for _, row in daycares_df.iterrows():
                did = norm_id(str(row["daycare_id"]))
                name = row["daycare_name"]
                daycare_name_dict[did] = str(name) if pd.notna(name) else ""
        result["daycare_name_dict"] = daycare_name_dict

        return result

    def match(
        self,
        children_df: pd.DataFrame,
        daycares_df: pd.DataFrame,
        *,
        max_time_seconds: float = 360.0,
        combination_df: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        """申込者を保育所へ割り当てる。

        Args:
            children_df: ChilmAI 内部列を持つ検証済み申込者テーブル。
            daycares_df: ChilmAI 内部列を持つ検証済み保育所テーブル。
            max_time_seconds: 制限時間を延長して1回再試行する前のソルバー制限時間。
            combination_df: parse_combination() の出力（任意）。

        Returns:
            割当結果、世帯単位の結果、メタデータを含むマッチング結果 dict。
        """
        return self._match_cp(
            children_df,
            daycares_df,
            max_time_seconds=max_time_seconds,
            combination_df=combination_df,
        )
