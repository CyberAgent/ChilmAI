from __future__ import annotations

import pandas as pd
import pytest

from chilmai.generic import BasePreprocessor, MatchingService
from chilmai.generic.config import DEFAULT_CONFIG


# ---------------------------------------------------------------------------
# テスト用ヘルパー
# ---------------------------------------------------------------------------


def _children_csv() -> bytes:
    return (
        "child_id,household_id,age,score_1,pref_1,pref_2,sibling_pattern,enrolled_daycare_id\n"
        "1,10,1,100,100,101,,\n"
        "2,11,2,80,100,101,2,\n"
        "3,11,1,80,101,100,2,\n"
    ).encode("utf-8")


def _children_csv_no_score() -> bytes:
    """score_1 と sibling_pattern を持たない CSV。preprocessor が補完することを想定。

    きょうだい世帯バリデーションを回避するため全員単独世帯（household_id が一意）。
    """
    return (
        "child_id,household_id,age,pref_1,pref_2,enrolled_daycare_id\n"
        "1,10,1,100,101,\n"
        "2,11,2,100,101,\n"
        "3,12,1,101,100,\n"
    ).encode("utf-8")


def _daycares_csv() -> bytes:
    return (
        "daycare_id,daycare_name,capacity_age0,capacity_age1,capacity_age2,"
        "capacity_age3,capacity_age4,capacity_age5\n"
        "100,A,0,2,0,0,0,0\n"
        "101,B,0,2,0,0,0,0\n"
    ).encode("utf-8")


def _small_df(**kwargs) -> pd.DataFrame:
    base = {"col_a": [3, 1, 2], "col_b": [10, 30, 20]}
    base.update(kwargs)
    return pd.DataFrame(base)


# ---------------------------------------------------------------------------
# BasePreprocessor: デフォルト動作（パススルー）
# ---------------------------------------------------------------------------


class TestBasePreprocessorDefaults:
    def test_validate_returns_empty(self):
        p = BasePreprocessor()
        assert p.validate(pd.DataFrame(), pd.DataFrame()) == []

    def test_transform_children_passthrough(self):
        p = BasePreprocessor()
        df = pd.DataFrame({"a": [1, 2]})
        result = p.transform_children(df)
        pd.testing.assert_frame_equal(result, df)

    def test_transform_daycares_passthrough(self):
        p = BasePreprocessor()
        df = pd.DataFrame({"x": [5]})
        result = p.transform_daycares(df)
        pd.testing.assert_frame_equal(result, df)

    def test_transform_output_passthrough(self):
        p = BasePreprocessor()
        df = pd.DataFrame({"col_a": [1], "col_b": [2]})
        result = p.transform_output(df, {})
        pd.testing.assert_frame_equal(result, df)


# ---------------------------------------------------------------------------
# BasePreprocessor.rank_by
# ---------------------------------------------------------------------------


class TestRankBy:
    def test_single_rule_desc(self):
        df = _small_df()
        ranks = BasePreprocessor.rank_by(df, [("col_a", "desc")])
        # col_a: 3,1,2 → 降順 → index 0 が最高優先 → rank=3
        assert ranks[0] == 3
        assert ranks[1] == 1
        assert ranks[2] == 2

    def test_single_rule_asc(self):
        df = _small_df()
        ranks = BasePreprocessor.rank_by(df, [("col_a", "asc")])
        # col_a: 3,1,2 → 昇順 → index 1 が最高優先 → rank=3
        assert ranks[1] == 3
        assert ranks[0] == 1
        assert ranks[2] == 2

    def test_two_rules_tiebreak(self):
        df = pd.DataFrame({"a": [1, 1, 2], "b": [10, 5, 99]})
        # a 降順 → index2 が最優先。a が同値のとき b 昇順 → index1 > index0
        ranks = BasePreprocessor.rank_by(df, [("a", "desc"), ("b", "asc")])
        assert ranks[2] == 3  # a=2、最優先
        assert ranks[1] == 2  # a=1, b=5
        assert ranks[0] == 1  # a=1, b=10

    def test_returns_series_with_same_index(self):
        df = _small_df().iloc[1:]  # index が 1,2 になる
        ranks = BasePreprocessor.rank_by(df, [("col_a", "desc")])
        assert list(ranks.index) == [1, 2]

    def test_all_unique_ranks(self):
        df = pd.DataFrame({"v": [4, 2, 3, 1]})
        ranks = BasePreprocessor.rank_by(df, [("v", "desc")])
        assert sorted(ranks.tolist()) == [1, 2, 3, 4]

    def test_empty_rules_returns_input_order(self):
        df = _small_df()
        ranks = BasePreprocessor.rank_by(df, [])
        assert list(ranks) == [3, 2, 1]

    def test_invalid_direction_raises(self):
        df = _small_df()
        with pytest.raises(ValueError, match="direction"):
            BasePreprocessor.rank_by(df, [("col_a", "ascending")])

    def test_stable_sort_preserves_input_order_for_ties(self):
        df = pd.DataFrame({"a": [1, 1, 1]})
        ranks = BasePreprocessor.rank_by(df, [("a", "desc")])
        # 全行同値のとき入力順が維持され、先頭行が最高ランク
        assert ranks[0] == 3
        assert ranks[1] == 2
        assert ranks[2] == 1


# ---------------------------------------------------------------------------
# MatchingService: カスタム preprocessor の統合テスト
# ---------------------------------------------------------------------------


class _AlwaysErrorPreprocessor(BasePreprocessor):
    """validate が常にエラーを返すスタブ。"""

    def validate(self, children_df, daycares_df):
        return [{"message": "custom error", "type": "data", "code": None}]

    def transform_children(self, df):
        pytest.fail("transform_children は validate 失敗後に呼ばれてはならない")


class _OutputTransformPreprocessor(BasePreprocessor):
    """transform_output が呼ばれたことを記録し、列を追加するスタブ。"""

    def __init__(self):
        self.called = False

    def transform_children(self, df):
        df = df.copy()
        df["score_1"] = list(range(len(df), 0, -1))
        df["sibling_pattern"] = ""
        return df

    def transform_output(self, df, result):
        self.called = True
        df = df.copy()
        df["カスタム列"] = "ok"
        return df


class _TransformTracker(BasePreprocessor):
    """transform_children が呼ばれたことを記録するスタブ。"""

    def __init__(self):
        self.called = False

    def transform_children(self, df):
        self.called = True
        return df


class _ScoreInjectingPreprocessor(BasePreprocessor):
    """score_1 と sibling_pattern を付与するスタブ。

    score_1 / sibling_pattern を持たない生 CSV に対して match() が成功することを
    検証するために使う。
    """

    def transform_children(self, df):
        df = df.copy()
        df["score_1"] = list(range(len(df), 0, -1))
        df["sibling_pattern"] = ""
        return df


class TestMatchingServiceWithPreprocessor:
    def test_default_preprocessor_validate_success(self):
        service = MatchingService()
        result = service.validate(
            children_file_bytes=_children_csv(),
            children_file_format="csv",
            daycares_file_bytes=_daycares_csv(),
            daycares_file_format="csv",
            mapping=DEFAULT_CONFIG,
        )
        assert result["is_valid"] is True

    def test_custom_validate_error_is_returned(self):
        service = MatchingService(preprocessor=_AlwaysErrorPreprocessor())
        result = service.validate(
            children_file_bytes=_children_csv(),
            children_file_format="csv",
            daycares_file_bytes=_daycares_csv(),
            daycares_file_format="csv",
            mapping=DEFAULT_CONFIG,
        )
        assert result["is_valid"] is False
        assert any(e["message"] == "custom error" for e in result["errors"])

    def test_transform_not_called_when_validate_fails(self):
        # _AlwaysErrorPreprocessor.transform_children は AssertionError を投げる仕様
        service = MatchingService(preprocessor=_AlwaysErrorPreprocessor())
        result = service.validate(
            children_file_bytes=_children_csv(),
            children_file_format="csv",
            daycares_file_bytes=_daycares_csv(),
            daycares_file_format="csv",
            mapping=DEFAULT_CONFIG,
        )
        assert result["is_valid"] is False

    def test_transform_called_when_validate_passes(self):
        tracker = _TransformTracker()
        service = MatchingService(preprocessor=tracker)
        service.validate(
            children_file_bytes=_children_csv(),
            children_file_format="csv",
            daycares_file_bytes=_daycares_csv(),
            daycares_file_format="csv",
            mapping=DEFAULT_CONFIG,
        )
        assert tracker.called is True

    def test_custom_validate_error_raises_in_match(self):
        service = MatchingService(preprocessor=_AlwaysErrorPreprocessor())
        with pytest.raises(ValueError) as exc_info:
            service.match(
                children_file_bytes=_children_csv(),
                children_file_format="csv",
                daycares_file_bytes=_daycares_csv(),
                daycares_file_format="csv",
                mapping=DEFAULT_CONFIG,
            )
        _msg, detail = exc_info.value.args
        assert detail["is_valid"] is False
        assert any(e["message"] == "custom error" for e in detail["errors"])

    def test_summary_included_in_custom_error_response(self):
        service = MatchingService(preprocessor=_AlwaysErrorPreprocessor())
        result = service.validate(
            children_file_bytes=_children_csv(),
            children_file_format="csv",
            daycares_file_bytes=_daycares_csv(),
            daycares_file_format="csv",
            mapping=DEFAULT_CONFIG,
        )
        assert "children_count" in result["summary"]
        assert "daycares_count" in result["summary"]

    def test_match_succeeds_with_custom_transform(self):
        """preprocessor の transform 結果が matcher に渡り match() が成功することを確認。

        score_1 / sibling_pattern を持たない CSV でも、_ScoreInjectingPreprocessor が
        補完することで GenericValidator を通過し、マッチング結果が返る。
        """
        service = MatchingService(preprocessor=_ScoreInjectingPreprocessor())
        result = service.match(
            children_file_bytes=_children_csv_no_score(),
            children_file_format="csv",
            daycares_file_bytes=_daycares_csv(),
            daycares_file_format="csv",
            mapping=DEFAULT_CONFIG,
        )
        assert "matching_result_dict" in result
        assert len(result["matching_result_dict"]) == 3

    def test_transform_output_is_called_and_applied(self):
        """transform_output が match() 後に呼ばれ、output_rows に反映されることを確認。"""
        preprocessor = _OutputTransformPreprocessor()
        service = MatchingService(preprocessor=preprocessor)
        result = service.match(
            children_file_bytes=_children_csv_no_score(),
            children_file_format="csv",
            daycares_file_bytes=_daycares_csv(),
            daycares_file_format="csv",
            mapping=DEFAULT_CONFIG,
        )
        assert preprocessor.called
        assert "カスタム列" in result["output_columns"]
        assert all(row["カスタム列"] == "ok" for row in result["output_rows"])


# ---------------------------------------------------------------------------
# SamplePreprocessor
# ---------------------------------------------------------------------------


class TestSamplePreprocessor:
    def _make_children(self, **extra) -> pd.DataFrame:
        base = {
            "child_id": ["1", "2", "3"],
            "household_id": ["10", "11", "11"],
            "age": ["1", "2", "1"],
            "pref_1": ["100", "101", "100"],
            "sibling_pattern": ["", "", ""],
            "enrolled_daycare_id": ["", "", ""],
            "指数合計": ["80", "100", "90"],
            "優先順位2": ["1", "20", "1"],
            "優先順位3": ["2", "1", "3"],
            "申込備考": [None, "/", "2/"],
        }
        base.update(extra)
        return pd.DataFrame(base)

    def test_validate_passes_when_required_cols_present(self):
        from examples.sample_preprocessor import SamplePreprocessor

        p = SamplePreprocessor()
        df = self._make_children()
        errors = p.validate(df, pd.DataFrame())
        assert errors == []

    def test_validate_fails_when_required_col_missing(self):
        from examples.sample_preprocessor import SamplePreprocessor

        p = SamplePreprocessor()
        df = self._make_children().drop(columns=["指数合計"])
        errors = p.validate(df, pd.DataFrame())
        assert len(errors) == 1
        assert errors[0]["type"] == "config"
        assert "指数合計" in errors[0]["message"]

    def test_transform_adds_score_1(self):
        from examples.sample_preprocessor import SamplePreprocessor

        p = SamplePreprocessor()
        df = self._make_children()
        result = p.transform_children(df)
        assert "score_1" in result.columns
        assert result["score_1"].dtype in (int, "int64", "int32")

    def test_score_1_order_matches_priority(self):
        from examples.sample_preprocessor import SamplePreprocessor

        p = SamplePreprocessor()
        df = self._make_children()
        result = p.transform_children(df)
        # child_id=2 (指数合計=100) > child_id=3 (90) > child_id=1 (80)
        s = result.set_index("child_id")["score_1"]
        assert s["2"] > s["3"] > s["1"]

    def test_transform_parses_sibling_pattern(self):
        from examples.sample_preprocessor import SamplePreprocessor

        p = SamplePreprocessor()
        df = self._make_children()
        result = p.transform_children(df)
        patterns = result["sibling_pattern"].tolist()
        assert patterns[0] == ""  # None → 単独児
        assert patterns[1] == "1"  # "/" → パターン1
        assert patterns[2] == "2"  # "2/" → パターン2

    def test_transform_does_not_mutate_input(self):
        from examples.sample_preprocessor import SamplePreprocessor

        p = SamplePreprocessor()
        df = self._make_children()
        original_cols = list(df.columns)
        p.transform_children(df)
        assert list(df.columns) == original_cols

    def test_validate_fails_on_non_numeric_required_ranking_col(self):
        from examples.sample_preprocessor import SamplePreprocessor

        p = SamplePreprocessor()
        df = self._make_children(**{"優先順位2": ["1", "abc", "1"]})
        errors = p.validate(df, pd.DataFrame())
        assert len(errors) == 1
        assert errors[0]["type"] == "data"
        assert "優先順位2" in errors[0]["message"]

    def test_validate_fails_on_non_numeric_optional_ranking_col(self):
        from examples.sample_preprocessor import SamplePreprocessor

        p = SamplePreprocessor()
        df = self._make_children(**{"優先順位4": ["1", "xyz", "1"]})
        errors = p.validate(df, pd.DataFrame())
        assert len(errors) == 1
        assert errors[0]["type"] == "data"
        assert "優先順位4" in errors[0]["message"]

    def test_validate_accumulates_errors_for_multiple_bad_cols(self):
        from examples.sample_preprocessor import SamplePreprocessor

        p = SamplePreprocessor()
        df = self._make_children(**{"指数合計": ["80", "bad", "90"], "優先順位2": ["1", "1", "??"]})
        errors = p.validate(df, pd.DataFrame())
        cols_with_errors = [e["message"] for e in errors]
        assert any("指数合計" in m for m in cols_with_errors)
        assert any("優先順位2" in m for m in cols_with_errors)

    def test_validate_skips_optional_col_when_absent(self):
        from examples.sample_preprocessor import SamplePreprocessor

        p = SamplePreprocessor()
        df = self._make_children()  # 優先順位4/6/8 は含まない
        errors = p.validate(df, pd.DataFrame())
        assert errors == []
