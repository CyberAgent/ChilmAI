"""カスタム前処理の実装サンプル。

``BasePreprocessor`` を継承して自治体固有の前処理を実装する例を示す。

想定する申込ファイルの追加列:
    - 指数合計:      主要な優先指数（高いほど優先）
    - 優先順位2:     認可保育所等に未入所かどうか（1=優先, 20=非優先）
    - 優先順位3:     優先類型（1〜10、小さいほど優先）
    - 優先順位4:     指数に減算なし（1=優先, 9=非優先）
    - 保護者１－基本: 保護者1の基本指数
    - 保護者２－基本: 保護者2の基本指数
    - 優先順位6:     在住歴（数値が小さいほど古く、優先）
    - 優先順位8:     最終タイブレーク（数値が小さいほど優先）
    - 申込備考:      きょうだいパターン（"/" → 1、"2/" → 2、... ）

使い方:
    from examples.sample_preprocessor import SamplePreprocessor
    from chilmai.generic import MatchingService

    service = MatchingService(preprocessor=SamplePreprocessor())
    result = service.match(
        children_file_bytes=...,
        children_file_format="excel",
        daycares_file_bytes=...,
        daycares_file_format="excel",
        mapping=config_store.load(),
    )
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

import pandas as pd

from chilmai.generic.preprocessor import BasePreprocessor


class SamplePreprocessor(BasePreprocessor):
    """カスタム前処理のサンプル実装。

    申込ファイルに含まれる優先順位列・指数列から一意なランキングを計算し
    ``score_1`` 列に格納する。また「申込備考」列からきょうだいパターン（1〜7）を
    読み取り ``sibling_pattern`` 列に格納する。
    """

    REQUIRED_COLS: ClassVar[list[str]] = [
        "指数合計",
        "優先順位2",
        "優先順位3",
        "申込備考",
    ]

    NUMERIC_COLS: ClassVar[list[str]] = [
        "指数合計",
        "優先順位2",
        "優先順位3",
        "優先順位4",
        "優先順位6",
        "優先順位8",
    ]

    RANKING_RULES: ClassVar[list[tuple[str, str]]] = [
        ("指数合計", "desc"),  # 主要指数：高いほど優先
        ("優先順位2", "asc"),  # 未入所優先：1 > 20
        ("優先順位3", "asc"),  # 優先類型：1 が最優先
        ("優先順位4", "asc"),  # 減算なし優先：1 > 9
        ("_parent_score", "desc"),  # 両親の基本指数合計：高いほど優先
        ("優先順位6", "asc"),  # 在住歴：数値が小さいほど古く優先
        ("優先順位8", "asc"),  # 最終タイブレーク
    ]

    def validate(
        self,
        children_df: pd.DataFrame,
        daycares_df: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        """申込ファイルに必須列が揃っているか確認する。"""
        errors: list[dict[str, Any]] = []

        missing = [c for c in self.REQUIRED_COLS if c not in children_df.columns]
        if missing:
            errors.append(
                {
                    "message": (
                        f"申込データに必要な列が不足しています: {missing}。"
                        "「項目名の設定」で列名を確認してください。"
                    ),
                    "type": "config",
                    "code": None,
                }
            )
            return errors

        for col in [c for c in self.NUMERIC_COLS if c in children_df.columns]:
            non_numeric = pd.to_numeric(children_df[col], errors="coerce").isna()
            if non_numeric.any():
                sample = children_df.loc[non_numeric, col].iloc[0]
                errors.append(
                    {
                        "message": f"「{col}」列に数値以外の値があります（例: {sample!r}）。整数で入力してください。",
                        "type": "data",
                        "code": None,
                    }
                )

        return errors

    def transform_children(self, df: pd.DataFrame) -> pd.DataFrame:
        """優先順位列からランキングを計算し、きょうだいパターンを解析する。"""
        df = df.copy()

        df["_parent_score"] = pd.to_numeric(
            df.get("保護者１－基本", pd.Series(0, index=df.index)), errors="coerce"
        ).fillna(0) + pd.to_numeric(
            df.get("保護者２－基本", pd.Series(0, index=df.index)), errors="coerce"
        ).fillna(0)

        for col in ["指数合計", "優先順位2", "優先順位3", "優先順位4", "優先順位6", "優先順位8"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        active_rules = [(col, d) for col, d in self.RANKING_RULES if col in df.columns]
        df["score_1"] = self.rank_by(df, active_rules)

        df["sibling_pattern"] = df["申込備考"].map(_parse_sibling_pattern)

        df = df.drop(columns=["_parent_score"], errors="ignore")
        return df

    def transform_output(self, df: pd.DataFrame, result: dict[str, Any]) -> pd.DataFrame:
        """出力ファイルの列順を調整する。

        結果列（入所選考結果保育所ID・名）を左端に移動し、
        score_N・sibling_pattern など内部計算列を除外する。
        """
        df = df.copy()
        result_cols = [c for c in df.columns if "入所選考結果" in str(c)]
        internal_cols = {
            c for c in df.columns if re.fullmatch(r"score_\d+", str(c)) or c == "sibling_pattern"
        }
        other_cols = [c for c in df.columns if c not in result_cols and c not in internal_cols]
        return df[result_cols + other_cols]


class PerPreferenceScorePreprocessor(BasePreprocessor):
    """希望施設ごとに異なる点数列がある場合のサンプル実装。

    元データに「第1希望点数」「第2希望点数」などの列がある自治体向け。
    各希望の基礎点は希望施設によって異なることがある（例: 兄弟在籍施設への加点）が、
    ``score_N`` はタイブレーカーまで含んだ完全なスコアでなければならない。

    そのため、基礎点列と共通タイブレーク列を組み合わせて一意なスコアを生成する::

        score_N = 第N希望点数 × (len(df) + 1) + tiebreak_rank

    乗数に ``len(df) + 1`` を使うことで、``tiebreak_rank`` の最大値（= ``len(df)``）でも
    基礎点の大小関係を崩さない。

    想定する申込ファイルの追加列:
        - 第1希望点数: 第1希望施設に対する入所優先点（高いほど優先）
        - 第2希望点数: 第2希望施設に対する入所優先点（例: 兄弟在籍加点あり）
        - 第3希望点数: 第3希望施設に対する入所優先点
        - 優先順位2:   タイブレーク条件（1=優先, 20=非優先）
        - 優先順位3:   タイブレーク条件（小さいほど優先）
        - 申込備考:   きょうだいパターン（"/" → 1、"2/" → 2、...）
    """

    SCORE_COL_MAP: ClassVar[dict[str, str]] = {
        "第1希望点数": "score_1",
        "第2希望点数": "score_2",
        "第3希望点数": "score_3",
    }

    TIEBREAK_RULES: ClassVar[list[tuple[str, str]]] = [
        ("優先順位2", "asc"),
        ("優先順位3", "asc"),
    ]

    REQUIRED_COLS: ClassVar[list[str]] = ["第1希望点数", "申込備考"]

    def validate(
        self,
        children_df: pd.DataFrame,
        daycares_df: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        """申込ファイルに必須列が揃っているか、点数列・タイブレーク列が数値かを確認する。"""
        errors: list[dict[str, Any]] = []
        missing = [c for c in self.REQUIRED_COLS if c not in children_df.columns]
        if missing:
            errors.append(
                {
                    "message": (
                        f"申込データに必要な列が不足しています: {missing}。"
                        "「項目名の設定」で列名を確認してください。"
                    ),
                    "type": "config",
                    "code": None,
                }
            )
            return errors

        numeric_cols = [c for c in self.SCORE_COL_MAP if c in children_df.columns] + [
            col for col, _ in self.TIEBREAK_RULES if col in children_df.columns
        ]
        for col in numeric_cols:
            non_numeric = pd.to_numeric(children_df[col], errors="coerce").isna()
            if non_numeric.any():
                sample = children_df.loc[non_numeric, col].iloc[0]
                errors.append(
                    {
                        "message": f"「{col}」列に数値以外の値があります（例: {sample!r}）。整数で入力してください。",
                        "type": "data",
                        "code": None,
                    }
                )

        return errors

    def transform_children(self, df: pd.DataFrame) -> pd.DataFrame:
        """希望施設ごとの点数列をタイブレークと組み合わせて score_N に格納する。"""
        df = df.copy()

        for col, _ in self.TIEBREAK_RULES:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        active_rules = [(col, d) for col, d in self.TIEBREAK_RULES if col in df.columns]
        tiebreak_rank = self.rank_by(df, active_rules)
        tiebreak_base = len(df) + 1  # rank の最大値（= len(df)）を超える乗数で基礎点の順序を保証する

        for src_col, dst_col in self.SCORE_COL_MAP.items():
            if src_col in df.columns:
                base = pd.to_numeric(df[src_col], errors="coerce").fillna(0).astype(int)
                df[dst_col] = base * tiebreak_base + tiebreak_rank

        df["sibling_pattern"] = df["申込備考"].map(_parse_sibling_pattern)
        return df

    def transform_output(self, df: pd.DataFrame, result: dict[str, Any]) -> pd.DataFrame:
        """結果列を左端に移動し、score_N・sibling_pattern など内部計算列を除外する。"""
        df = df.copy()
        result_cols = [c for c in df.columns if "入所選考結果" in str(c)]
        internal_cols = {
            c for c in df.columns if re.fullmatch(r"score_\d+", str(c)) or c == "sibling_pattern"
        }
        other_cols = [c for c in df.columns if c not in result_cols and c not in internal_cols]
        return df[result_cols + other_cols]


def _parse_sibling_pattern(value: Any) -> str:
    """「申込備考」の値をきょうだいパターン番号（文字列）に変換する。

    Args:
        value: "/"（パターン1）、"2/"（パターン2）、... のいずれか、または空欄。

    Returns:
        "1"〜"7" の文字列、またはきょうだい申請なしを表す空文字。
    """
    if pd.isna(value):
        return ""
    s = str(value).strip()
    if s == "" or s == "/":
        return "1" if s == "/" else ""
    stripped = s.rstrip("/")
    return stripped if stripped.isdigit() else ""
