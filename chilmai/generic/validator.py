"""マッチング前に正規化済み ChilmAI 入力テーブルを検証する。"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

import pandas as pd

from chilmai.generic.error_codes import ErrorCode
from chilmai.generic.family_pref_builder import ALLOWED_SIBLING_PATTERNS
from chilmai.generic.matcher import norm_id


CHILDREN_REQUIRED = {"child_id", "household_id", "age", "enrolled_daycare_id", "sibling_pattern"}
DAYCARES_REQUIRED = {
    "daycare_id",
    "daycare_name",
    "capacity_age0",
    "capacity_age1",
    "capacity_age2",
    "capacity_age3",
    "capacity_age4",
    "capacity_age5",
}


class ValidationService:
    """申込者 DataFrame と保育所 DataFrame を検証する。

    入力は `InputParser` のマッピング適用後の ChilmAI 内部列名を使う想定。
    通常の検証失敗では例外を投げず、config/data/format に分類した構造化エラーを返す。
    """

    @staticmethod
    def _pref_columns(children_df: pd.DataFrame) -> list[str]:
        cols = [c for c in children_df.columns if isinstance(c, str) and re.fullmatch(r"pref_\d+", c)]
        return sorted(cols, key=lambda c: int(c.split("_")[1]))

    @staticmethod
    def _prefix_display_name(prefix_template: str, n: str) -> str:
        """'N'（小文字が続かない）をプレースホルダとして数字に置換。"""
        m = re.search(r"N(?![a-z])", prefix_template)
        if m:
            return prefix_template[: m.start()] + n + prefix_template[m.start() + 1 :]
        return f"{prefix_template}{n}"

    @staticmethod
    def _display_col(internal: str, mapping: dict[str, str]) -> str:
        """内部列名 → ユーザー設定の表示名。見つからなければ内部名をそのまま返す。"""
        if internal in mapping:
            return mapping[internal]
        m = re.fullmatch(r"pref_(\d+)", internal)
        if m and "preference_prefix" in mapping:
            return ValidationService._prefix_display_name(mapping["preference_prefix"], m.group(1))
        m = re.fullmatch(r"score_(\d+)", internal)
        if m:
            if m.group(1) == "1" and mapping.get("score"):
                return mapping["score"]
            if "score_prefix" in mapping:
                return ValidationService._prefix_display_name(mapping["score_prefix"], m.group(1))
        m = re.fullmatch(r"capacity_age(\d+)", internal)
        if m and "capacity_prefix" in mapping:
            return ValidationService._prefix_display_name(mapping["capacity_prefix"], m.group(1))
        return internal

    def validate(
        self,
        children_df: pd.DataFrame,
        daycares_df: pd.DataFrame,
        children_mapping: dict[str, str] | None = None,
        daycares_mapping: dict[str, str] | None = None,
        combination_df: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        """申込者データと保育所データを検証する。

        Args:
            children_df: ChilmAI 内部列名を使う申込者データ。
            daycares_df: ChilmAI 内部列名を使う保育所データ。
            children_mapping: 表示用の申込者列名マッピング。省略可。
            daycares_mapping: 表示用の保育所列名マッピング。省略可。

        Returns:
            `is_valid`, `errors`, `warnings`, `summary` を持つ dict。
        """
        c_map = children_mapping or {}
        d_map = daycares_mapping or {}
        errors: list[dict[str, Any]] = []
        warnings: list[str] = []

        child_missing = sorted(CHILDREN_REQUIRED - set(children_df.columns))
        if child_missing:
            display_missing = ", ".join(self._display_col(c, c_map) for c in child_missing)
            errors.append(
                {
                    "message": f"子どもファイルに必要な列が見つかりません（{display_missing}）。「項目名の設定」で列名を確認してください。",
                    "type": "config",
                    "code": ErrorCode.MISSING_CHILDREN_COLUMNS,
                }
            )
        else:
            for id_col in ("child_id", "household_id"):
                empty_mask = children_df[id_col].isna() | (
                    children_df[id_col].astype(str).str.strip() == ""
                )
                if empty_mask.any():
                    errors.append(
                        {
                            "message": f"「{self._display_col(id_col, c_map)}」列に空の値があります。子どもファイルの全行に値を入力してください。",
                            "type": "data",
                            "code": ErrorCode.EMPTY_ID_FIELD,
                        }
                    )
            normed_child_ids = [norm_id(v) for v in children_df["child_id"].astype(str).tolist()]
            counts = Counter(normed_child_ids)
            duplicate_child_ids = sorted(v for v, n in counts.items() if n > 1 and v != "")
            if duplicate_child_ids:
                errors.append(
                    {
                        "message": f"「{self._display_col('child_id', c_map)}」列に重複した値があります（例：'{duplicate_child_ids[0]}'）。各申請者に一意の値を設定してください。",
                        "type": "data",
                        "code": ErrorCode.DUPLICATE_CHILD_ID,
                    }
                )

        daycare_missing = sorted(DAYCARES_REQUIRED - set(daycares_df.columns))
        if daycare_missing:
            display_missing = ", ".join(self._display_col(c, d_map) for c in daycare_missing)
            errors.append(
                {
                    "message": f"保育所ファイルに必要な列が見つかりません（{display_missing}）。「項目名の設定」で列名を確認してください。",
                    "type": "config",
                    "code": ErrorCode.MISSING_DAYCARE_COLUMNS,
                }
            )

        pref_cols = self._pref_columns(children_df)
        if not pref_cols:
            errors.append(
                {
                    "message": f"子どもファイルに希望列が見つかりません。「項目名の設定」で希望列のプレフィックスを確認してください（例：{self._display_col('pref_1', c_map)}）。",
                    "type": "config",
                    "code": ErrorCode.MISSING_PREF_COLUMNS,
                }
            )

        if "score_1" not in children_df.columns:
            errors.append(
                {
                    "message": f"子どもファイルに「{self._display_col('score_1', c_map)}」列が見つかりません。「項目名の設定」で列名を確認してください。",
                    "type": "config",
                    "code": ErrorCode.MISSING_SCORE_COLUMN,
                }
            )
        else:
            empty_score_mask = children_df["score_1"].isna() | (
                children_df["score_1"].astype(str).str.strip() == ""
            )
            if empty_score_mask.any():
                errors.append(
                    {
                        "message": f"「{self._display_col('score_1', c_map)}」列に空の値があります。第1希望に対応する点数は全行に入力してください。",
                        "type": "data",
                        "code": ErrorCode.EMPTY_SCORE_1,
                    }
                )

        if not errors:
            try:
                children_df["age"] = pd.to_numeric(children_df["age"], errors="raise").astype(int)
            except Exception:
                errors.append(
                    {
                        "message": f"「{self._display_col('age', c_map)}」列に数値以外の値が含まれています。整数で入力してください。",
                        "type": "data",
                        "code": ErrorCode.NON_INTEGER_AGE,
                    }
                )
            else:
                out_of_range = children_df[~children_df["age"].between(0, 5)]
                if not out_of_range.empty:
                    sample_age = int(out_of_range["age"].iloc[0])
                    errors.append(
                        {
                            "message": f"「{self._display_col('age', c_map)}」列に 0〜5 以外の値があります（例：{sample_age}）。0歳〜5歳の整数で入力してください。",
                            "type": "data",
                            "code": ErrorCode.INVALID_AGE_RANGE,
                        }
                    )

        score_cols = [
            c for c in children_df.columns if isinstance(c, str) and re.fullmatch(r"score_\d+", c)
        ]
        if score_cols and not errors:
            # parser が '.0' サフィックスを除去するため、ここでは厳密な整数 regex で判定する。
            # float() ベースの判定は大桁の小数（例：'1e16.5'）で精度欠落により誤受理する恐れがある。
            try:
                for sc in score_cols:
                    non_null = children_df[sc].dropna()
                    if not non_null.empty:
                        for val in non_null:
                            s = str(val).strip()
                            if not re.fullmatch(r"-?\d+", s):
                                raise ValueError(f"{sc} contains non-integer value: {s!r}")
            except Exception:
                errors.append(
                    {
                        "message": f"点数列（{self._display_col('score_1', c_map)} など）に整数以外の値が含まれています。整数で入力してください。",
                        "type": "data",
                        "code": ErrorCode.NON_INTEGER_SCORE,
                    }
                )

            daycare_id_col = daycares_df["daycare_id"]
            empty_daycare_id_mask = daycare_id_col.isna() | (daycare_id_col.astype(str).str.strip() == "")
            if empty_daycare_id_mask.any():
                errors.append(
                    {
                        "message": f"保育所ファイルの「{self._display_col('daycare_id', d_map)}」列に空の値があります。全行に値を入力してください。",
                        "type": "data",
                        "code": ErrorCode.EMPTY_DAYCARE_ID,
                    }
                )
            try:
                for age in range(6):
                    col = f"capacity_age{age}"
                    daycares_df[col] = pd.to_numeric(daycares_df[col], errors="raise").astype(int)
                    if (daycares_df[col] < 0).any():
                        errors.append(
                            {
                                "message": f"保育所ファイルの「{self._display_col(col, d_map)}」列に0未満の値があります。定員は0以上の整数を入力してください。",
                                "type": "data",
                                "code": ErrorCode.NEGATIVE_CAPACITY,
                            }
                        )
            except Exception:
                errors.append(
                    {
                        "message": f"保育所ファイルの定員列（{self._display_col('capacity_age0', d_map)} など）に数値以外の値が含まれています。定員は整数で入力してください。",
                        "type": "data",
                        "code": ErrorCode.NON_INTEGER_CAPACITY,
                    }
                )

        if not errors:
            normed_daycare_ids = [norm_id(v) for v in daycares_df["daycare_id"].dropna().astype(str)]
            normed_non_empty = [v for v in normed_daycare_ids if v != ""]
            id_counts = Counter(normed_non_empty)
            duplicate_daycare_ids = sorted(v for v, n in id_counts.items() if n > 1)
            if duplicate_daycare_ids:
                errors.append(
                    {
                        "message": f"保育所ファイルの「{self._display_col('daycare_id', d_map)}」列に重複した値があります（例：'{duplicate_daycare_ids[0]}'）。各保育所に一意の値を設定してください。",
                        "type": "data",
                        "code": ErrorCode.DUPLICATE_DAYCARE_ID,
                    }
                )
            daycare_ids = set(normed_non_empty)
            for pref_col in pref_cols:
                pref_series = children_df[pref_col].dropna().astype(str).map(norm_id)
                pref_series = pref_series[pref_series != ""]
                if pref_series.empty:
                    continue
                unknown = sorted(set(pref_series.tolist()) - daycare_ids)
                if unknown:
                    disp = self._display_col(pref_col, c_map)
                    errors.append(
                        {
                            "message": f"希望列「{disp}」に、保育所ファイルに存在しない保育所ID（例：'{unknown[0]}'）が含まれています。\n子どもファイルの「{disp}」列を確認し、保育所ファイルに登録されているIDに修正してください。",
                            "type": "data",
                            "code": ErrorCode.UNKNOWN_DAYCARE_IN_PREF,
                        }
                    )

            children_with_all_empty_prefs = children_df[pref_cols].apply(
                lambda row: all(pd.isna(v) or norm_id(str(v)) == "" for v in row),
                axis=1,
            )
            if children_with_all_empty_prefs.any():
                empty_ids = children_df.loc[children_with_all_empty_prefs, "child_id"].astype(str).tolist()
                errors.append(
                    {
                        "message": f"希望保育所が1件も登録されていない申請者がいます（例：{self._display_col('child_id', c_map)}='{empty_ids[0]}'）。\n子どもファイルの希望列（{self._display_col('pref_1', c_map)} など）に少なくとも1件の保育所IDを入力してください。",
                        "type": "data",
                        "code": ErrorCode.NO_PREFERENCES,
                    }
                )

            enrolled_series = children_df["enrolled_daycare_id"].dropna().astype(str).map(norm_id)
            enrolled_series = enrolled_series[enrolled_series != ""]
            if not enrolled_series.empty:
                unknown_enrolled = sorted(set(enrolled_series.tolist()) - daycare_ids)
                if unknown_enrolled:
                    disp_enr = self._display_col("enrolled_daycare_id", c_map)
                    errors.append(
                        {
                            "message": f"「{disp_enr}」列に、保育所ファイルに存在しない保育所ID（例：'{unknown_enrolled[0]}'）が含まれています。\n子どもファイルの「{disp_enr}」列を確認し、保育所ファイルに登録されているIDに修正してください。",
                            "type": "data",
                            "code": ErrorCode.UNKNOWN_ENROLLED_DAYCARE,
                        }
                    )

            enrolled_normed = children_df["enrolled_daycare_id"].apply(
                lambda v: norm_id(str(v)) if pd.notna(v) else ""
            )
            pref_normed_df = children_df[pref_cols].apply(
                lambda col: col.apply(lambda v: norm_id(str(v)) if pd.notna(v) else "")
            )
            match_df = pref_normed_df.eq(enrolled_normed, axis=0) & pref_normed_df.ne("")
            enrolled_in_pref_mask = (enrolled_normed != "") & match_df.any(axis=1)
            if enrolled_in_pref_mask.any():
                conflict_ids = children_df.loc[enrolled_in_pref_mask, "child_id"].astype(str).tolist()
                disp_cid = self._display_col("child_id", c_map)
                disp_enr = self._display_col("enrolled_daycare_id", c_map)
                errors.append(
                    {
                        "message": f"「{disp_enr}」が希望列に含まれている申請者がいます（例：{disp_cid}='{conflict_ids[0]}'）。\n子どもファイルの希望列から「{disp_enr}」を削除してください。",
                        "type": "data",
                        "code": ErrorCode.ENROLLED_IN_PREF,
                    }
                )

            pattern_series = children_df["sibling_pattern"]
            non_empty_str = pattern_series.dropna().astype(str).str.strip()
            non_empty_str = non_empty_str[non_empty_str != ""]

            if not non_empty_str.empty:
                numeric = pd.to_numeric(non_empty_str, errors="coerce")
                non_parseable = non_empty_str[numeric.isna()].tolist()
                parseable = numeric.dropna()
                is_finite = parseable.map(lambda x: math.isfinite(float(x)))
                non_finite_strs = non_empty_str[parseable[~is_finite].index].tolist()
                parseable_finite = parseable[is_finite]
                is_whole = parseable_finite % 1 == 0
                non_integer_floats = non_empty_str[parseable_finite[~is_whole].index].tolist()
                parsed_ints = parseable_finite[is_whole].astype(int).tolist()
                invalid = sorted(
                    set(non_parseable)
                    | set(non_finite_strs)
                    | set(non_integer_floats)
                    | {str(v) for v in set(parsed_ints) - ALLOWED_SIBLING_PATTERNS}
                )
                if invalid:
                    errors.append(
                        {
                            "message": f"「{self._display_col('sibling_pattern', c_map)}」列に無効な値があります（例：'{invalid[0]}'）。使用できる値は 1〜7 の整数のみです。",
                            "type": "data",
                            "code": ErrorCode.INVALID_SIBLING_PATTERN,
                        }
                    )

            # 組み合わせファイルに登場する世帯IDのセット（sibling_pattern チェックを免除）
            combo_household_ids: set[str] = set()
            if combination_df is not None and "household_id" in combination_df.columns:
                combo_household_ids = {
                    norm_id(str(v)) for v in combination_df["household_id"].dropna().astype(str)
                }

            for household_id, grp in children_df.groupby("household_id", sort=False):
                # 組み合わせファイルに記載のある世帯は sibling_pattern 不要
                if norm_id(str(household_id)) in combo_household_ids:
                    continue

                raw = [v for v in grp["sibling_pattern"].dropna().astype(str).str.strip().tolist() if v]

                if len(grp) >= 2 and not raw:
                    errors.append(
                        {
                            "message": f"「{self._display_col('sibling_pattern', c_map)}」が空欄の世帯があります（{self._display_col('household_id', c_map)}：{household_id}）。\nきょうだい申請の世帯には 1〜7 の整数を入力してください。",
                            "type": "data",
                            "code": ErrorCode.SIBLING_PATTERN_BLANK_IN_HOUSEHOLD,
                        }
                    )
                    break
                if not raw:
                    continue
                num = pd.to_numeric(pd.Series(raw, dtype=object), errors="coerce")
                normalized = [
                    int(n) if pd.notna(n) and math.isfinite(float(n)) and n % 1 == 0 else v
                    for v, n in zip(raw, num)
                ]
                if len(set(normalized)) > 1:
                    errors.append(
                        {
                            "message": f"「{self._display_col('sibling_pattern', c_map)}」が同一世帯内で一致しません（{self._display_col('household_id', c_map)}：{household_id}）。\n同じ世帯の申請者には同じ値を設定してください。",
                            "type": "data",
                            "code": ErrorCode.SIBLING_PATTERN_MISMATCH,
                        }
                    )
                    break

            errors.extend(
                self._validate_sibling_common_preferences(
                    children_df, pref_cols, combo_household_ids, c_map
                )
            )

        summary = {
            "children_count": int(len(children_df.index)),
            "daycares_count": int(len(daycares_df.index)),
        }
        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "summary": summary,
        }

    # 同保系パターンで共通希望施設が必須となるパターン番号。
    _SAME_DAYCARE_PATTERNS = (1, 2, 3)

    @staticmethod
    def _normalized_pref_set(row: pd.Series, pref_cols: list[str]) -> set[str]:
        """行の希望列を norm_id で正規化した施設ID（文字列）の集合にする。

        family_pref 生成側の `_to_pref_list` は `int(pd.to_numeric(...))` で数値変換するため、
        非数値の希望ID（例：'ABC'）があると ValueError で validate() ごと落ちる。
        共通希望施設の有無は ID を文字列で正規化して突き合わせれば判定でき、
        '.0' サフィックスの揺れも norm_id が吸収するため、ここでは数値変換しない。
        不正な希望IDは UNKNOWN_DAYCARE_IN_PREF として別途報告される。
        """
        result: set[str] = set()
        for col in pref_cols:
            value = row.get(col)
            if pd.isna(value):
                continue
            normed = norm_id(str(value))
            if normed:
                result.add(normed)
        return result

    def _validate_sibling_common_preferences(
        self,
        children_df: pd.DataFrame,
        pref_cols: list[str],
        combo_household_ids: set[str],
        c_map: dict[str, str],
    ) -> list[dict[str, Any]]:
        """きょうだい世帯のきょうだい条件と共通希望施設の整合性を検証する。

        有効パターンが 1/2/3（同保系）の世帯できょうだい間に共通する希望施設が
        存在しない場合はエラーにする。共通施設がないと、family_pref 生成時に
        転園元への戻り等にフォールバックし、いずれかの児童が入所選考の対象外と
        なるため。

        - パターン1（同保同時）: 共通施設なしで全員入所不可。
        - パターン2（同保・上の子優先）: 共通施設なしで年下のお子様が対象外。
        - パターン3（同保・下の子優先）: 共通施設なしで年上のお子様が対象外。

        空欄・不一致（Rule 1 / mismatch）の世帯と、family_pref を直接生成する
        組み合わせファイル掲載世帯は対象外（既存チェックに委譲）。
        """
        errors: list[dict[str, Any]] = []
        hh_disp = self._display_col("household_id", c_map)
        cid_disp = self._display_col("child_id", c_map)
        sib_disp = self._display_col("sibling_pattern", c_map)
        pref_disp = self._display_col("pref_1", c_map)

        reason_map = {
            1: "パターン1（同保同時）ですが、きょうだい間に共通する希望施設が存在しません。共通施設がないと全員が入所できません。",
            2: "パターン2（同保・上の子優先）ですが、きょうだい間に共通する希望施設が存在しません。共通施設がないと年下のお子様が入所選考の対象外になります。",
            3: "パターン3（同保・下の子優先）ですが、きょうだい間に共通する希望施設が存在しません。共通施設がないと年上のお子様が入所選考の対象外になります。",
        }

        for household_id, grp in children_df.groupby("household_id", sort=False):
            if len(grp) < 2:
                continue
            if norm_id(str(household_id)) in combo_household_ids:
                continue

            raw = [v for v in grp["sibling_pattern"].dropna().astype(str).str.strip().tolist() if v]
            # 空欄（Rule 1）・不一致（mismatch）は既存チェックが報告するため二重報告しない。
            if not raw:
                continue
            num = pd.to_numeric(pd.Series(raw, dtype=object), errors="coerce")
            normalized = [
                int(n) if pd.notna(n) and math.isfinite(float(n)) and n % 1 == 0 else v
                for v, n in zip(raw, num)
            ]
            if len(set(normalized)) > 1:
                continue

            # `FamilyPrefBuilder._resolve_sibling_pattern` は範囲外の値（例: 8）を
            # パターン1 にフォールバックするため、INVALID_SIBLING_PATTERN として
            # 既に報告済みの世帯に対し誤った SIBLING_NO_COMMON_PREFERENCE を出してしまう。
            # ここではフォールバックせず、明示された有効値（1〜7 の整数）だけを見る。
            pattern = normalized[0]
            if pattern not in self._SAME_DAYCARE_PATTERNS:
                continue

            pref_sets = [self._normalized_pref_set(row, pref_cols) for _, row in grp.iterrows()]
            common = set.intersection(*pref_sets) if pref_sets else set()
            if common:
                continue

            child_ids_str = "、".join(str(v) for v in grp["child_id"].tolist())
            errors.append(
                {
                    "message": (
                        f"きょうだい申請の世帯（{hh_disp}：{household_id}、{cid_disp}：{child_ids_str}）は"
                        f"{reason_map[pattern]}\n"
                        f"希望列（{pref_disp} など）またはきょうだい条件（{sib_disp}）を見直してください。"
                    ),
                    "type": "data",
                    "code": ErrorCode.SIBLING_NO_COMMON_PREFERENCE,
                }
            )

        return errors

    def validate_combination(
        self,
        combination_df: pd.DataFrame,
        children_df: pd.DataFrame,
        daycares_df: pd.DataFrame,
        combination_mapping: dict[str, str] | None = None,
        children_mapping: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """組み合わせ DataFrame を検証してエラーリストを返す。"""
        errors: list[dict[str, Any]] = []
        combo_map = combination_mapping or {}

        # 必須列の確認
        required = {"household_id", "rank"}
        missing = required - set(combination_df.columns)
        child_indices = {
            int(c.split("_")[-1]) for c in combination_df.columns if re.fullmatch(r"child_code_\d+", c)
        }
        facility_indices = {
            int(c.split("_")[-1]) for c in combination_df.columns if re.fullmatch(r"facility_\d+", c)
        }
        if missing or not child_indices or not facility_indices:
            errors.append(
                {
                    "message": "組み合わせファイルに必要な列が見つかりません。「項目名の設定」で組み合わせデータの列名を確認してください。",
                    "type": "config",
                    "code": ErrorCode.COMBINATION_FILE_MISSING_COLUMNS,
                }
            )
            return errors
        if child_indices != facility_indices:
            errors.append(
                {
                    "message": f"組み合わせファイルの宛名コード列と希望施設列の番号が一致しません（宛名コード: {sorted(child_indices)}、希望施設: {sorted(facility_indices)}）。各番号に対応するペアを揃えてください。",
                    "type": "config",
                    "code": ErrorCode.COMBINATION_FILE_MISSING_COLUMNS,
                }
            )
            return errors

        # rank が正の整数であること
        rank_series = pd.to_numeric(combination_df["rank"], errors="coerce")
        invalid_rank_mask = rank_series.isna() | (rank_series % 1 != 0) | (rank_series < 1)
        if invalid_rank_mask.any():
            bad_val = combination_df.loc[invalid_rank_mask, "rank"].iloc[0]
            rank_label = combo_map.get("rank", "総当たり順位")
            errors.append(
                {
                    "message": f"組み合わせファイルの「{rank_label}」列に無効な値があります（例：'{bad_val}'）。1以上の整数を入力してください。",
                    "type": "data",
                    "code": ErrorCode.COMBINATION_INVALID_RANK,
                }
            )

        # household_id の照合（dropna で NaN → "nan" 文字列化を防ぐ）
        known_hh = set(children_df["household_id"].dropna().astype(str).map(norm_id))
        combo_hh = combination_df["household_id"].dropna().astype(str).map(norm_id)
        unknown_hh = sorted(set(combo_hh) - known_hh - {""})
        if unknown_hh:
            hh_label = combo_map.get("household_id", "ファミリーコード")
            errors.append(
                {
                    "message": f"組み合わせファイルの「{hh_label}」列に、申込者ファイルに存在しない世帯IDがあります（例：'{unknown_hh[0]}'）。",
                    "type": "data",
                    "code": ErrorCode.COMBINATION_UNKNOWN_HOUSEHOLD,
                }
            )

        # child_code の照合（全体存在チェック）
        known_child = set(children_df["child_id"].astype(str).map(norm_id))
        child_code_cols = [c for c in combination_df.columns if re.fullmatch(r"child_code_\d+", c)]
        unknown_child: list[str] = []
        for col in child_code_cols:
            vals = combination_df[col].dropna().astype(str).map(norm_id)
            vals = vals[vals != ""]
            unk = sorted(set(vals) - known_child)
            unknown_child.extend(unk)
        unknown_child = sorted(set(unknown_child))
        if unknown_child:
            child_label = combo_map.get("child_code_prefix", "宛名コード")
            errors.append(
                {
                    "message": f"組み合わせファイルの「{child_label}」列に、申込者ファイルに存在しない申請者IDがあります（例：'{unknown_child[0]}'）。",
                    "type": "data",
                    "code": ErrorCode.COMBINATION_UNKNOWN_CHILD_CODE,
                }
            )

        # child_code の世帯帰属チェック（別世帯の child_id が混入していないか）
        if not unknown_child:
            hh_to_children: dict[str, set[str]] = {}
            for _, row in children_df.iterrows():
                hh = norm_id(str(row["household_id"]))
                cid = norm_id(str(row["child_id"]))
                hh_to_children.setdefault(hh, set()).add(cid)
            cross_hh: list[str] = []
            for _, row in combination_df.iterrows():
                hh_val = row.get("household_id")
                if pd.isna(hh_val):
                    continue
                hh = norm_id(str(hh_val))
                expected = hh_to_children.get(hh, set())
                for col in child_code_cols:
                    val = row.get(col)
                    if pd.isna(val) or norm_id(str(val)) == "":
                        continue
                    cid = norm_id(str(val))
                    if cid not in expected:
                        cross_hh.append(cid)
            if cross_hh:
                child_label = combo_map.get("child_code_prefix", "宛名コード")
                errors.append(
                    {
                        "message": f"組み合わせファイルの「{child_label}」列に、当該世帯に属さない申請者IDがあります（例：'{cross_hh[0]}'）。組み合わせ行の世帯IDと申請者IDが一致しているか確認してください。",
                        "type": "data",
                        "code": ErrorCode.COMBINATION_UNKNOWN_CHILD_CODE,
                    }
                )

        # facility の照合
        known_daycare = set(daycares_df["daycare_id"].astype(str).map(norm_id))
        facility_cols = [c for c in combination_df.columns if re.fullmatch(r"facility_\d+", c)]
        unknown_daycare: list[str] = []
        for col in facility_cols:
            vals = combination_df[col].dropna().astype(str).map(norm_id)
            vals = vals[vals != ""]
            unk = sorted(set(vals) - known_daycare)
            unknown_daycare.extend(unk)
        unknown_daycare = sorted(set(unknown_daycare))
        if unknown_daycare:
            fac_label = combo_map.get("facility_prefix", "希望施設")
            errors.append(
                {
                    "message": f"組み合わせファイルの「{fac_label}」列に、保育所ファイルに存在しない保育所IDがあります（例：'{unknown_daycare[0]}'）。",
                    "type": "data",
                    "code": ErrorCode.COMBINATION_UNKNOWN_DAYCARE,
                }
            )

        return errors
