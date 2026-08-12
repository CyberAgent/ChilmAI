from __future__ import annotations

from collections import Counter
from itertools import product


def _effective_combination(
    combination: tuple[int | None, ...],
    current_daycares: list[int | None],
) -> tuple[int | None, ...]:
    """転園元への割り当てをNoneとみなした実効的な組み合わせを返す。"""
    return tuple(
        None if (cp is not None and d == cp) else d for d, cp in zip(combination, current_daycares)
    )


def _calculate_w_s(eff: tuple[int | None, ...]) -> tuple[int, int]:
    """入所人数 W と同一施設最大人数 S を返す。"""
    counter = Counter(d for d in eff if d is not None)
    if not counter:
        return 0, 0
    counts = sorted(counter.values(), reverse=True)
    W = sum(counts)
    S = counts[0]
    return W, S


def _compute_rank_product_and_list(
    eff: tuple[int | None, ...],
    pref_li: list[list[int]],
) -> tuple[int, list[int]]:
    """各子の希望順位と積を計算して返す。None の場合は rank=99。"""
    MAX_RANK = 99
    rank_product = 1
    rank_list = []
    for i, daycare in enumerate(eff):
        if daycare is None:
            rank = MAX_RANK
        elif daycare in pref_li[i]:
            rank = pref_li[i].index(daycare) + 1
        else:
            rank = MAX_RANK
        rank_product *= rank
        rank_list.append(rank)
    return rank_product, rank_list


def _score_standard(
    eff: tuple[int | None, ...],
    pref_li: list[list[int]],
) -> list[int]:
    """パターン1・4・5用スコア: [W, S, -rp, -r0, -r1, ...]"""
    W, S = _calculate_w_s(eff)
    rp, rl = _compute_rank_product_and_list(eff, pref_li)
    return [W, S, -rp] + [-r for r in rl]


def _score_older_priority(
    eff: tuple[int | None, ...],
    pref_li: list[list[int]],
) -> list[int]:
    """パターン2用スコア: [mask_0, mask_1, ..., W, S, -rp, -r0, -r1, ...]"""
    W, S = _calculate_w_s(eff)
    rp, rl = _compute_rank_product_and_list(eff, pref_li)
    mask = [1 if d is not None else 0 for d in eff]
    return mask + [W, S, -rp] + [-r for r in rl]


def _score_younger_priority(
    eff: tuple[int | None, ...],
    pref_li: list[list[int]],
) -> list[int]:
    """パターン3用スコア: [rev_mask_0, ..., W, S, -rp, -rn, ..., -r0]"""
    W, S = _calculate_w_s(eff)
    rp, rl = _compute_rank_product_and_list(eff, pref_li)
    rev_mask = [1 if d is not None else 0 for d in reversed(eff)]
    return rev_mask + [W, S, -rp] + [-r for r in reversed(rl)]


def _score_no_s(
    eff: tuple[int | None, ...],
    pref_li: list[list[int]],
) -> list[int]:
    """パターン6・7用スコア（Sなし）: [W, -rp, -r0, -r1, ...]"""
    W, _ = _calculate_w_s(eff)
    rp, rl = _compute_rank_product_and_list(eff, pref_li)
    return [W, -rp] + [-r for r in rl]


def _append_transfer_return(
    sorted_combinations: list[tuple[int | None, ...]],
    current_daycares: list[int | None],
) -> list[tuple[int | None, ...]]:
    """転園児は転園元に戻る組み合わせ（current_daycares のタプル）をリスト末尾に配置する。"""
    if not any(d is not None for d in current_daycares):
        return sorted_combinations
    return_combo = tuple(current_daycares)
    result = [c for c in sorted_combinations if c != return_combo]
    result.append(return_combo)
    return result


def create_sibling_pref(
    pref_li: list[list[int]],
    ages: list[int],  # noqa: ARG001  (reserved for future tie-breaking)
    current_daycares: list[int | None],
    pattern: int,
) -> list[tuple[int | None, ...]]:
    """きょうだいグループの保育所希望優先順位リストを生成する。

    Args:
        pref_li (list[list[int]]): pref_li[i] = きょうだい i 番目（年長順）の保育所希望リスト（保育所ID の list）。
        ages (list[int]): ages[i] = きょうだい i 番目の年齢（年長順）。現在は未使用で、将来のタイブレーク用に予約済み。
        current_daycares (list[int | None]): current_daycares[i] = きょうだい i 番目が現在在籍する保育所ID。
            転園でない場合は None。
        pattern (int): きょうだいパターン番号。
            1: 同保同時   - 同所・全員同月必須
            2: 同保順次（上） - 同所優先・月バラOK・上の子単独
            3: 同保順次（下） - 同所優先・月バラOK・下の子単独
            4: 別保同時（同） - 同所優先・全員同月必須
            5: 別保順次（同） - 同所優先・月バラOK
            6: 別保同時（希） - 各自希望順・全員同月必須
            7: 別保順次（希） - 各自希望順・月バラOK

    Returns:
        list[tuple[int | None, ...]]: 各タプルは (きょうだい0の施設ID, きょうだい1の施設ID, ...) を表す。
            None は「その月は入所しない」を意味する。
            転園元への戻り組み合わせはリスト末尾に配置される。
    """
    # 転園なし児童の pref に None を追加（待機の選択肢）
    pref_with_none = [
        list(p) + ([None] if current_daycares[i] is None else []) for i, p in enumerate(pref_li)
    ]

    # 全組み合わせ生成（全員 None は除外）
    all_combinations: list[tuple[int | None, ...]] = [
        c for c in product(*pref_with_none) if not all(d is None for d in c)
    ]

    # --- フィルタリング ---
    if pattern == 1:
        # 全員が同一施設（転園元はNone扱い）
        valid = []
        for comb in all_combinations:
            eff = _effective_combination(comb, current_daycares)
            if len(set(eff)) == 1 and eff[0] is not None:
                valid.append(comb)

    elif pattern in (2, 3):
        # 転園元でも None でもない「新しい施設」が最大1つ
        # パターン2: 上の子（index 0）が None になる組み合わせは生成しない
        # パターン3: 下の子（index -1）が None になる組み合わせは生成しない
        valid = []
        for comb in all_combinations:
            new_daycares: set[int] = set()
            for d, cp in zip(comb, current_daycares):
                if d is not None and d != cp:
                    new_daycares.add(d)
            if len(new_daycares) > 1:
                continue
            if pattern == 2:
                # 上の子が実質 None（None or 転園元）かつ新施設が存在する → 無効
                if (comb[0] is None or comb[0] == current_daycares[0]) and new_daycares:
                    continue
            else:
                # パターン3: 下の子が実質 None かつ新施設が存在する → 無効
                if (comb[-1] is None or comb[-1] == current_daycares[-1]) and new_daycares:
                    continue
            valid.append(comb)

    elif pattern in (4, 6):
        # 全員入所必須（実効組み合わせに None なし）
        valid = [c for c in all_combinations if None not in _effective_combination(c, current_daycares)]

    elif pattern in (5, 7):
        # 少なくとも1人入所（実効組み合わせが全員 None でない）
        valid = [
            c
            for c in all_combinations
            if any(d is not None for d in _effective_combination(c, current_daycares))
        ]

    else:
        raise ValueError(f"Unsupported sibling pattern: {pattern}")

    # --- スコア計算 & ソート ---
    if pattern == 2:
        score_fn = _score_older_priority
    elif pattern == 3:
        score_fn = _score_younger_priority
    elif pattern in (6, 7):
        score_fn = _score_no_s
    else:
        score_fn = _score_standard

    scored = [(comb, score_fn(_effective_combination(comb, current_daycares), pref_li)) for comb in valid]
    sorted_combinations = [c for c, _ in sorted(scored, key=lambda x: x[1], reverse=True)]

    # 重複除去（順序維持）
    seen: set[tuple[int | None, ...]] = set()
    deduped = []
    for c in sorted_combinations:
        if c not in seen:
            seen.add(c)
            deduped.append(c)

    # 転園元戻り組み合わせを末尾に移動
    return _append_transfer_return(deduped, current_daycares)
