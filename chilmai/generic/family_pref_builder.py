from __future__ import annotations

import math
import re
from dataclasses import dataclass

import pandas as pd

from chilmai.generic.sibling_pref_patterns import create_sibling_pref

# Allowed integer values for sibling_pattern (1–7 as used in municipality CSV files).
# Semantics: 1=同保同時, 2=同保順次（上）, 3=同保順次（下）,
#            4=別保同時（同）, 5=別保順次（同）, 6=別保同時（希）, 7=別保順次（希）
ALLOWED_SIBLING_PATTERNS: set[int] = {1, 2, 3, 4, 5, 6, 7}


@dataclass
class HouseholdPreference:
    household_id: int
    child_ids: list[int]
    ages: list[int]
    score_map: dict[tuple[int, int], int]
    input_orders: list[int]
    family_pref: list[tuple[int | None, ...]]


class FamilyPrefBuilder:
    @staticmethod
    def score_columns(children_df: pd.DataFrame) -> list[str]:
        cols = [c for c in children_df.columns if isinstance(c, str) and re.fullmatch(r"score_\d+", c)]
        return sorted(cols, key=lambda c: int(c.split("_")[1]))

    @staticmethod
    def pref_columns(children_df: pd.DataFrame) -> list[str]:
        cols = [c for c in children_df.columns if isinstance(c, str) and re.fullmatch(r"pref_\d+", c)]
        return sorted(cols, key=lambda c: int(c.split("_")[1]))

    @staticmethod
    def _to_pref_list(row: pd.Series, pref_cols: list[str]) -> list[int]:
        result: list[int] = []
        seen: set[int] = set()
        for col in pref_cols:
            value = row.get(col)
            if pd.isna(value):
                continue
            daycare_id = int(pd.to_numeric(value))
            if daycare_id in seen:
                continue
            seen.add(daycare_id)
            result.append(daycare_id)
        return result

    @staticmethod
    def _resolve_sibling_pattern(group_df: pd.DataFrame) -> int:
        if "sibling_pattern" not in group_df.columns:
            return 1

        values = [v for v in group_df["sibling_pattern"].tolist() if pd.notna(v) and str(v).strip()]
        if not values:
            return 1
        numeric = pd.to_numeric(str(values[0]).strip(), errors="coerce")
        if (
            pd.notna(numeric)
            and math.isfinite(float(numeric))
            and numeric == int(numeric)
            and int(numeric) in ALLOWED_SIBLING_PATTERNS
        ):
            return int(numeric)
        # Invalid or out-of-range values fall back to 1 (same_simultaneous).
        # Out-of-range values are caught earlier by the validator; this fallback
        # is a safety net when build() is called on already-validated data.
        return 1

    @staticmethod
    def _norm_id(s: str) -> str:
        """Excel が float 化した整数 ID の '.0' サフィックスを除去して正規化する。
        数値以外の ID（例: 'A.0'）は変換しない（matcher.norm_id と同じ挙動）。
        """
        stripped = s.strip()
        if re.fullmatch(r"-?\d+\.0+", stripped):
            return re.sub(r"\.0+$", "", stripped)
        return stripped

    @staticmethod
    def _build_from_combination_data(
        ordered_group: pd.DataFrame,
        combo_df: pd.DataFrame,
        child_count: int,
    ) -> list[tuple[int | None, ...]]:
        """組み合わせ DataFrame から family_pref を組み立てる。

        ordered_group は (age 降順, child_id 昇順) でソート済みであること。
        combo_df は parse_combination() の出力のうち当該世帯分（rank 昇順でソートする）。
        """
        norm_id = FamilyPrefBuilder._norm_id

        # child_id（正規化済み文字列）→ タプル位置 のマップ
        child_id_to_pos: dict[str, int] = {
            norm_id(str(row["child_id"])): i for i, (_, row) in enumerate(ordered_group.iterrows())
        }

        child_code_cols = sorted(
            [c for c in combo_df.columns if isinstance(c, str) and re.fullmatch(r"child_code_\d+", c)],
            key=lambda c: int(c.split("_")[-1]),
        )
        facility_cols = sorted(
            [c for c in combo_df.columns if isinstance(c, str) and re.fullmatch(r"facility_\d+", c)],
            key=lambda c: int(c.split("_")[-1]),
        )

        result: list[tuple[int | None, ...]] = []
        try:
            rank_series = pd.to_numeric(combo_df["rank"], errors="coerce")
            sorted_df = combo_df.assign(_rank_num=rank_series).sort_values("_rank_num")
        except KeyError:
            sorted_df = combo_df

        for _, row in sorted_df.iterrows():
            slot: list[int | None] = [None] * child_count
            for cc_col, fac_col in zip(child_code_cols, facility_cols):
                code_val = row.get(cc_col)
                if pd.isna(code_val) or str(code_val).strip() == "":
                    continue
                normed_code = norm_id(str(code_val).strip())
                pos = child_id_to_pos.get(normed_code)
                if pos is None:
                    continue
                fac_val = row.get(fac_col)
                if pd.isna(fac_val) or str(fac_val).strip() == "":
                    slot[pos] = None
                else:
                    try:
                        slot[pos] = int(pd.to_numeric(fac_val))
                    except (ValueError, TypeError):
                        slot[pos] = None
            result.append(tuple(slot))
        return result

    @staticmethod
    def _build_single(
        pref_li: list[list[int]],
        current_daycare: int | None = None,
    ) -> list[tuple[int | None, ...]]:
        if not pref_li:
            return []
        combos = [(daycare_id,) for daycare_id in pref_li[0]]
        if current_daycare is not None and (current_daycare,) not in combos:
            combos.append((current_daycare,))
        return combos

    @classmethod
    def build(
        cls,
        children_df: pd.DataFrame,
        combination_df: pd.DataFrame | None = None,
    ) -> list[HouseholdPreference]:
        pref_cols = cls.pref_columns(children_df)
        score_cols = cls.score_columns(children_df)
        households: list[HouseholdPreference] = []

        for household_id, group in children_df.groupby("household_id", sort=False):
            ordered = group.sort_values(by=["age", "child_id"], ascending=[False, True], kind="stable")
            child_ids = [int(v) for v in ordered["child_id"].tolist()]
            ages = [int(v) for v in ordered["age"].tolist()]
            input_orders = [int(v) for v in ordered["_input_order"].tolist()]
            pref_li = [cls._to_pref_list(row, pref_cols) for _, row in ordered.iterrows()]

            score_map: dict[tuple[int, int], int] = {}
            for (_, row), child_id in zip(ordered.iterrows(), child_ids):
                score_1_raw = row.get("score_1")
                try:
                    base_score = (
                        int(score_1_raw.strip() if isinstance(score_1_raw, str) else score_1_raw)
                        if pd.notna(score_1_raw)
                        else 0
                    )
                except (ValueError, AttributeError):
                    base_score = 0
                seen_daycares: set[int] = set()
                for pref_col in pref_cols:
                    daycare_val = row.get(pref_col)
                    if pd.isna(daycare_val):
                        continue
                    daycare_id = int(pd.to_numeric(daycare_val))
                    if daycare_id in seen_daycares:
                        continue
                    seen_daycares.add(daycare_id)
                    n = pref_col.split("_")[1]
                    score_col = f"score_{n}"
                    if score_col in score_cols:
                        score_val = row.get(score_col)
                        try:
                            score = (
                                int(score_val.strip() if isinstance(score_val, str) else score_val)
                                if pd.notna(score_val)
                                else base_score
                            )
                        except (ValueError, AttributeError):
                            score = base_score
                    else:
                        score = base_score
                    score_map[(child_id, daycare_id)] = score

            if "enrolled_daycare_id" in ordered.columns:
                current_daycares = [
                    int(pd.to_numeric(v)) if pd.notna(v) else None
                    for v in ordered["enrolled_daycare_id"].tolist()
                ]
            else:
                current_daycares = [None] * len(child_ids)

            sibling_pattern = cls._resolve_sibling_pattern(ordered)

            if len(child_ids) == 1:
                family_pref = cls._build_single(pref_li, current_daycares[0])
            elif combination_df is not None:
                norm_id = cls._norm_id
                hh_id_normed = norm_id(str(household_id))
                hh_combo = combination_df[
                    combination_df["household_id"].astype(str).map(norm_id) == hh_id_normed
                ]
                if not hh_combo.empty:
                    # 組み合わせファイルに記載のある世帯 → 直接セット
                    family_pref = cls._build_from_combination_data(ordered, hh_combo, len(child_ids))
                else:
                    # 組み合わせファイルに記載なし → 従来の sibling_pattern で生成
                    pref_li_with_transfer = [
                        (list(p) + [cd]) if (cd is not None and cd not in p) else list(p)
                        for p, cd in zip(pref_li, current_daycares)
                    ]
                    family_pref = create_sibling_pref(
                        pref_li_with_transfer, ages, current_daycares, sibling_pattern
                    )
            else:
                # 転園児の enrolled_daycare を pref_li に追加（単独児と同様の扱い）
                pref_li_with_transfer = [
                    (list(p) + [cd]) if (cd is not None and cd not in p) else list(p)
                    for p, cd in zip(pref_li, current_daycares)
                ]
                family_pref = create_sibling_pref(
                    pref_li_with_transfer, ages, current_daycares, sibling_pattern
                )

            households.append(
                HouseholdPreference(
                    household_id=int(pd.to_numeric(household_id)),
                    child_ids=child_ids,
                    ages=ages,
                    score_map=score_map,
                    input_orders=input_orders,
                    family_pref=family_pref,
                )
            )

        return households
