from __future__ import annotations

import pandas as pd

from chilmai.constants import UNMATCHED_DAYCARE_ID
from chilmai.generic.family_pref_builder import HouseholdPreference


class DictBuilder:
    @staticmethod
    def build_children_dic(
        children_df: pd.DataFrame,
        pref_cols: list[str],
    ) -> dict:
        result: dict = {}
        for _, row in children_df.iterrows():
            c_id = int(row["child_id"])
            age = int(row["age"])
            family_id = int(row["household_id"])

            enrolled = row.get("enrolled_daycare_id")
            if enrolled is not None and pd.notna(enrolled):
                initial_daycare_id = int(enrolled)
            else:
                initial_daycare_id = UNMATCHED_DAYCARE_ID

            preference_list: list[int] = []
            seen_prefs: set[int] = set()
            for col in pref_cols:
                val = row.get(col)
                if pd.notna(val):
                    daycare_id = int(pd.to_numeric(val))
                    if daycare_id in seen_prefs:
                        continue
                    seen_prefs.add(daycare_id)
                    preference_list.append(daycare_id)

            result[c_id] = {
                "id": c_id,
                "age": age,
                "family_id": family_id,
                "initial_daycare_id": initial_daycare_id,
                "preference_list": preference_list,
            }
        return result

    @staticmethod
    def build_base_scores(children_df: pd.DataFrame) -> dict[int, int]:
        result: dict[int, int] = {}
        for _, row in children_df.iterrows():
            c_id = int(row["child_id"])
            score_raw = row.get("score_1")
            try:
                result[c_id] = (
                    int(score_raw.strip() if isinstance(score_raw, str) else score_raw)
                    if pd.notna(score_raw)
                    else 0
                )
            except (ValueError, AttributeError):
                result[c_id] = 0
        return result

    @staticmethod
    def build_score_lookup(
        children_df: pd.DataFrame,
        pref_cols: list[str],
        score_cols: list[str],
    ) -> dict[tuple[int, int], int]:
        lookup: dict[tuple[int, int], int] = {}
        max_score: int = 0
        for _, row in children_df.iterrows():
            c_id = int(row["child_id"])
            base_score_raw = row.get("score_1")
            base_score = (
                int(base_score_raw.strip() if isinstance(base_score_raw, str) else base_score_raw)
                if pd.notna(base_score_raw)
                else 0
            )
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
                lookup[(c_id, daycare_id)] = score
                if score > max_score:
                    max_score = score

        # 転園元保育所には最優先スコアを設定し、戻り先を保証する
        transfer_return_score = max_score * 10 if max_score > 0 else 1
        for _, row in children_df.iterrows():
            enrolled = row.get("enrolled_daycare_id")
            if pd.notna(enrolled):
                c_id = int(row["child_id"])
                enrolled_id = int(pd.to_numeric(enrolled))
                lookup[(c_id, enrolled_id)] = transfer_return_score

        return lookup

    @staticmethod
    def _projected_daycare_set(households: list[HouseholdPreference]) -> dict[int, set[int]]:
        """各児童が世帯コンボ内で取りうる保育所 ID 集合を返す。

        戻り値は `{child_id: set[daycare_id]}` 形式。
        CP アルゴリズムは世帯コンボ由来の projected preference に含まれる保育所だけに
        xcd 変数を作る。gamma 制約構築時の KeyError を避けるため、優先順位リストも
        同じ集合に限定する必要がある。
        """
        result: dict[int, set[int]] = {}
        for h in households:
            for combo in h.family_pref:
                for child_id, d in zip(h.child_ids, combo):
                    if d is not None:
                        result.setdefault(child_id, set()).add(d)
        return result

    @staticmethod
    def build_daycares_dic(
        daycares_df: pd.DataFrame,
        score_lookup: dict[tuple[int, int], int],
        households: list[HouseholdPreference],
        base_scores: dict[int, int],
        transfer_counts: dict[int, dict[int, int]] | None = None,
    ) -> dict:
        # Build priority lists from the projected daycare set (family combos), not individual pref
        # columns. In sibling cases a child may appear in a combo for a daycare they did not
        # individually list; those children still need an entry in the priority list (with their
        # base score as fallback) so that xcd variables are always resolvable.
        projected = DictBuilder._projected_daycare_set(households)

        daycare_children: dict[int, list[tuple[int, int]]] = {}
        for c_id, daycare_set in projected.items():
            for d_id in daycare_set:
                score = score_lookup.get((c_id, d_id), base_scores.get(c_id, 0))
                daycare_children.setdefault(d_id, []).append((c_id, score))
        for d_id in daycare_children:
            daycare_children[d_id].sort(key=lambda x: (-x[1], x[0]))

        result: dict = {}
        for _, row in daycares_df.iterrows():
            d_id = int(row["daycare_id"])
            recruiting = [int(pd.to_numeric(row[f"capacity_age{age}"])) for age in range(6)]
            # 転園児が退所すると枠が空くため、転園アウト数を加算して実効定員とする。
            if transfer_counts and d_id in transfer_counts:
                for age, count in transfer_counts[d_id].items():
                    recruiting[age] += count

            children_for_d = daycare_children.get(d_id, [])
            priority_child_id_list = [c_id for c_id, _ in children_for_d]
            priority_score_list = [score for _, score in children_for_d]

            result[d_id] = {
                "id": d_id,
                "recruiting_numbers_list": recruiting,
                "share_ages_list": [],
                "priority_child_id_list": priority_child_id_list,
                "priority_score_list": priority_score_list,
                # True: CP容量制約に転園児を含める（update_daycares_attributes内の
                # total_numbers加算は削除済み。転園アウト分はrecruiting側で加算済み）
                "is_use_transfer": [True] * 6,
            }
        return result

    @staticmethod
    def build_families_dic(households: list[HouseholdPreference]) -> dict:
        result: dict = {}
        for h in households:
            is_siblings = len(h.child_ids) > 1
            if is_siblings:
                # family_pref is list[tuple[int | None, ...]] — keep as tuples, replace None with UNMATCHED_DAYCARE_ID
                pref: list = [
                    tuple(UNMATCHED_DAYCARE_ID if d is None else d for d in combo)
                    for combo in h.family_pref
                ]
            else:
                # single child: unwrap 1-tuples to list[int] so update_families_attributes works correctly
                pref = [UNMATCHED_DAYCARE_ID if combo[0] is None else combo[0] for combo in h.family_pref]

            result[h.household_id] = {
                "id": h.household_id,
                "children": h.child_ids,
                "pref": pref,
            }
        return result
