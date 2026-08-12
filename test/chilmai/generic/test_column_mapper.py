from __future__ import annotations

from chilmai.generic.column_mapper import detect_section, load_aliases


def _by_key(suggestions, key):
    matches = [s for s in suggestions if s.internal_key == key]
    return matches[0] if matches else None


def test_exact_match():
    columns = ["申請者番号", "世帯番号", "年齢", "スコア1", "スコア2", "希望保育園ID_1", "希望保育園ID_2"]
    current = {"child_id": "違う値", "household_id": "違う値"}
    suggestions = detect_section(columns, "children", current)
    s = _by_key(suggestions, "child_id")
    assert s is not None
    assert s.detected_value == "申請者番号"
    assert s.match_type == "exact"
    assert s.confidence == 1.0


def test_full_width_normalization():
    columns = ["申請者ＩＤ"]
    current = {"child_id": ""}
    suggestions = detect_section(columns, "children", current)
    s = _by_key(suggestions, "child_id")
    assert s is not None
    assert s.detected_value == "申請者ＩＤ"
    assert s.match_type == "exact"


def test_partial_match():
    columns = ["児童申請者ID欄"]
    current = {"child_id": ""}
    suggestions = detect_section(columns, "children", current)
    s = _by_key(suggestions, "child_id")
    assert s is not None
    assert s.match_type in ("partial", "fuzzy")
    assert s.detected_value == "児童申請者ID欄"


def test_fuzzy_below_threshold_skipped():
    columns = ["全く関係ない列"]
    current = {"child_id": ""}
    suggestions = detect_section(columns, "children", current)
    assert _by_key(suggestions, "child_id") is None


def test_template_score_prefix_detected():
    columns = ["スコア1", "スコア2", "スコア3"]
    current = {"score_prefix": ""}
    suggestions = detect_section(columns, "children", current)
    s = _by_key(suggestions, "score_prefix")
    assert s is not None
    assert s.detected_value == "スコアN"
    assert s.match_type == "template"


def test_template_single_hit_detected():
    columns = ["スコア1"]
    current = {"score_prefix": ""}
    suggestions = detect_section(columns, "children", current)
    s = _by_key(suggestions, "score_prefix")
    assert s is not None
    assert s.detected_value == "スコアN"
    assert s.match_type == "template"


def test_template_fullwidth_digit_normalized():
    columns = ["スコア１"]
    current = {"score_prefix": ""}
    suggestions = detect_section(columns, "children", current)
    s = _by_key(suggestions, "score_prefix")
    assert s is not None
    assert s.detected_value == "スコアN"
    assert s.match_type == "template"


def test_template_capacity_detected():
    columns = ["0歳募集人数", "1歳募集人数", "2歳募集人数"]
    current = {"capacity_prefix": ""}
    suggestions = detect_section(columns, "daycares", current)
    s = _by_key(suggestions, "capacity_prefix")
    assert s is not None
    assert s.detected_value == "N歳募集人数"


def test_no_suggestion_when_matches_current():
    columns = ["申請者番号"]
    current = {"child_id": "申請者番号"}
    suggestions = detect_section(columns, "children", current)
    assert _by_key(suggestions, "child_id") is None


def test_daycare_section():
    columns = ["園ID", "園名", "0歳定員", "1歳定員"]
    current = {"daycare_id": "", "daycare_name": "", "capacity_prefix": ""}
    suggestions = detect_section(columns, "daycares", current)
    assert _by_key(suggestions, "daycare_id") is not None
    assert _by_key(suggestions, "daycare_id").detected_value == "園ID"
    assert _by_key(suggestions, "daycare_name") is not None
    assert _by_key(suggestions, "capacity_prefix") is not None


def test_unknown_columns_ignored():
    columns = ["備考", "コメント", "メモ"]
    current = {}
    suggestions = detect_section(columns, "children", current)
    assert suggestions == []


def test_aliases_file_loadable():
    aliases = load_aliases()
    assert "children" in aliases
    assert "daycares" in aliases
    assert "child_id" in aliases["children"]


def test_empty_columns():
    suggestions = detect_section([], "children", {})
    assert suggestions == []


def test_non_string_columns_ignored():
    columns = ["申請者番号", None, 123, "  "]
    current = {"child_id": ""}
    suggestions = detect_section(columns, "children", current)
    s = _by_key(suggestions, "child_id")
    assert s is not None
    assert s.detected_value == "申請者番号"
