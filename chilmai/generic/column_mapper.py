"""サンプルファイルのヘッダーから列名マッピング候補を提案する。"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal

from chilmai.generic.parser import numbered_pattern

ALIASES_PATH = Path(__file__).resolve().parent / "column_aliases.json"

MATCH_TYPE = Literal["exact", "partial", "fuzzy", "template"]
SECTION = Literal["children", "daycares", "combination"]

PREFIX_KEYS = {
    "score_prefix",
    "preference_prefix",
    "capacity_prefix",
    "child_code_prefix",
    "facility_prefix",
}

FUZZY_THRESHOLD = 0.85
TEMPLATE_MIN_HITS = 1


@dataclass
class Suggestion:
    """ChilmAI 内部項目1つに対して検出されたマッピング候補。"""

    section: str
    internal_key: str
    detected_value: str
    match_type: MATCH_TYPE
    confidence: float
    current_value: str = ""
    alternatives: list[str] = field(default_factory=list)


def _normalize(s: str) -> str:
    return unicodedata.normalize("NFKC", s).strip().lower()


def load_aliases(path: Path | None = None) -> dict:
    """自動マッピング検出で使う列名別名定義を読み込む。"""
    target = path or ALIASES_PATH
    with target.open("r", encoding="utf-8") as f:
        return json.load(f)


def _exact_or_partial(
    norm_column_to_original: dict[str, str],
    aliases: list[str],
) -> tuple[str, MATCH_TYPE, float] | None:
    """完全一致を先に試し、その後に部分一致（双方向の包含）を試す。"""
    norm_aliases = [(_normalize(a), a) for a in aliases]

    for n_alias, _orig_alias in norm_aliases:
        if n_alias in norm_column_to_original:
            return norm_column_to_original[n_alias], "exact", 1.0

    best: tuple[str, float] | None = None
    for n_col, original_col in norm_column_to_original.items():
        for n_alias, _orig_alias in norm_aliases:
            if not n_alias or not n_col:
                continue
            if n_alias in n_col or n_col in n_alias:
                shorter = min(len(n_alias), len(n_col))
                longer = max(len(n_alias), len(n_col))
                score = shorter / longer if longer else 0.0
                score = max(0.7, min(0.9, score))
                if best is None or score > best[1]:
                    best = (original_col, score)
    if best is not None:
        return best[0], "partial", best[1]
    return None


def _fuzzy(
    norm_column_to_original: dict[str, str],
    aliases: list[str],
) -> tuple[str, MATCH_TYPE, float] | None:
    best: tuple[str, float] | None = None
    norm_aliases = [_normalize(a) for a in aliases if a]
    for n_col, original_col in norm_column_to_original.items():
        for n_alias in norm_aliases:
            if not n_col or not n_alias:
                continue
            ratio = SequenceMatcher(None, n_col, n_alias).ratio()
            if ratio >= FUZZY_THRESHOLD and (best is None or ratio > best[1]):
                best = (original_col, ratio)
    if best is not None:
        return best[0], "fuzzy", best[1]
    return None


def _detect_template(
    columns: list[str],
    templates: list[str],
) -> tuple[str, MATCH_TYPE, float] | None:
    """番号付き列が一定数以上ある場合に、テンプレート一致として検出する。"""
    best: tuple[str, int] | None = None
    for template in templates:
        try:
            pattern = numbered_pattern(template)
        except Exception:
            continue
        hits = sum(1 for col in columns if isinstance(col, str) and pattern.fullmatch(_normalize(col)))
        if hits >= TEMPLATE_MIN_HITS and (best is None or hits > best[1]):
            best = (template, hits)
    if best is not None:
        confidence = min(1.0, 0.7 + 0.1 * best[1])
        return best[0], "template", confidence
    return None


def detect_section(
    columns: list[str],
    section: SECTION,
    current_config: dict[str, str],
    aliases: dict | None = None,
) -> list[Suggestion]:
    """単一セクション（children または daycares）のマッピングを検出する。

    一致が見つかり、かつ現在の設定値と検出値が異なるキーだけを候補として返す。
    """
    aliases = aliases if aliases is not None else load_aliases()
    section_aliases = aliases.get(section, {})

    cleaned_columns = [c for c in columns if isinstance(c, str) and c.strip()]
    norm_column_to_original: dict[str, str] = {}
    for col in cleaned_columns:
        n = _normalize(col)
        if n and n not in norm_column_to_original:
            norm_column_to_original[n] = col

    suggestions: list[Suggestion] = []
    for internal_key, entry in section_aliases.items():
        current = current_config.get(internal_key, "")
        if internal_key in PREFIX_KEYS:
            templates = entry.get("templates", [])
            result = _detect_template(cleaned_columns, templates)
        else:
            alias_list = entry.get("aliases", [])
            result = _exact_or_partial(norm_column_to_original, alias_list)
            if result is None:
                result = _fuzzy(norm_column_to_original, alias_list)

        if result is None:
            continue
        detected, match_type, confidence = result
        if _normalize(detected) == _normalize(current):
            continue
        suggestions.append(
            Suggestion(
                section=section,
                internal_key=internal_key,
                detected_value=detected,
                match_type=match_type,
                confidence=round(confidence, 3),
                current_value=current,
            )
        )

    # Suppress bare 'score' suggestion when score_prefix templates already match
    # (numbered columns like スコア1 should not be proposed as single bare score)
    score_prefix_templates = section_aliases.get("score_prefix", {}).get("templates", [])
    if score_prefix_templates and _detect_template(cleaned_columns, score_prefix_templates) is not None:
        suggestions = [s for s in suggestions if s.internal_key != "score"]

    return suggestions
