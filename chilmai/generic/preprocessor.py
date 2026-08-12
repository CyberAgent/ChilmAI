"""自治体カスタム前処理の基底クラス。

事業者は ``BasePreprocessor`` を継承し、以下の 4 メソッドを必要に応じて実装する:

- ``validate``: 生データの入力規則チェック（自治体固有）
- ``transform_children``: スコアランキング・兄弟パターンの計算
- ``transform_daycares``: 保育所データの変換（通常は不要）
- ``transform_output``: 出力ファイルの列・行の加工（通常は不要）

実装例は ``examples/sample_preprocessor.py`` を参照。
"""

from __future__ import annotations

from typing import Any

import pandas as pd


class BasePreprocessor:
    """自治体カスタム前処理の基底クラス。デフォルト実装はすべてパススルー。

    ``MatchingService`` のコンストラクタに渡すことで前処理を有効にする::

        from chilmai.generic import MatchingService
        from mytown.preprocessor import MyTownPreprocessor

        service = MatchingService(preprocessor=MyTownPreprocessor())
        result = service.match(...)

    パイプラインの順序:

    1. ``parse`` — ファイル読込・列名マッピング
    2. ``validate`` — 自治体固有バリデーション（ここでエラーがあれば以降はスキップ）
    3. ``transform_children`` / ``transform_daycares`` — score_1〜N・sibling_pattern の計算
    4. ``ValidationService.validate`` — ChilmAI 汎用バリデーション
    5. ``matcher.match`` — マッチング実行
    6. ``transform_output`` — 出力 DataFrame の列・行を加工
    """

    def validate(
        self,
        children_df: pd.DataFrame,
        daycares_df: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        """自治体固有の入力規則チェック。

        列名マッピング適用後の DataFrame を受け取る。元ファイルの全列が残っている
        ため、自治体独自の列（指数合計、優先順位 N など）にアクセスできる。

        Args:
            children_df: 申込者データ（列名マッピング適用済み）。
            daycares_df: 保育所データ（列名マッピング適用済み）。

        Returns:
            エラーがなければ空リスト。エラーがある場合は以下の形式の dict のリスト::

                {"message": "エラー内容", "type": "data"|"config", "code": int|None}

            形式は ``ValidationService`` のエラーと同じ。
        """
        return []

    def transform_children(self, df: pd.DataFrame) -> pd.DataFrame:
        """申込者データを変換し、スコア列と ``sibling_pattern`` 列を追加する。

        ``validate`` でエラーがなかった場合のみ呼ばれる。
        元 DataFrame を変更せず、コピーを返すことを推奨する。

        ``score_N`` はタイブレーカーまで含んだ完全な優先順位スコアでなければならない。
        基礎点が同じ申込者が複数いる場合に同値だとマッチング内での優先順位が不定になる。
        希望施設ごとの点数列が基礎点のみを表す場合は共通タイブレーク列と組み合わせて
        一意なスコアを生成すること
        （``examples/sample_preprocessor.py`` の ``PerPreferenceScorePreprocessor`` 参照）。

        Args:
            df: 申込者データ（列名マッピング適用済み）。

        Returns:
            以下の列を追加した DataFrame:

            - ``score_1``（整数）: 全保育所共通のベーススコア。``score_N`` が存在しない
                希望施設への点数として使われる。全施設で同じ点数ルールの場合は
                この列だけ返せばよい。
            - ``score_2``, ``score_3``, ...（整数・任意）: 第 N 希望施設への個別スコア。
                元データに希望施設ごとの点数列がある場合（例: 第1希望は50点・
                兄弟在籍の第2希望は55点など）に設定する。``pref_N`` 列に対応する
                施設に適用され、``score_N`` がない希望は ``score_1`` にフォールバックする。
            - ``sibling_pattern``（"1"〜"7" または空文字）: きょうだいパターン番号。
        """
        return df

    def transform_daycares(self, df: pd.DataFrame) -> pd.DataFrame:
        """保育所データを変換する。通常は実装不要。

        Args:
            df: 保育所データ（列名マッピング適用済み）。

        Returns:
            変換後の保育所 DataFrame。
        """
        return df

    def transform_output(
        self,
        df: pd.DataFrame,
        result: dict[str, Any],
    ) -> pd.DataFrame:
        """出力ファイルの列・行を加工する。通常は実装不要。

        マッチング結果列（入所選考結果保育所ID・名）が追加された後に呼ばれる。
        列の並べ替え・追加・削除が可能。元 DataFrame を変更せず、コピーを返すことを推奨する。

        Args:
            df: 出力 DataFrame（元の申込ファイル全列 + 結果列）。
            result: マッチング結果 dict。``matching_result_dict``・``daycare_name_dict`` など
                ``MatchingService.match()`` が返すキーを含む。ただし ``output_columns``・
                ``output_rows`` はこのフック呼び出し後にセットされるため、まだ含まれない。

        Returns:
            加工後の出力 DataFrame。
        """
        return df

    @staticmethod
    def rank_by(
        df: pd.DataFrame,
        rules: list[tuple[str, str]],
    ) -> pd.Series:
        """複数列のソートルールから整数ランクを計算する。

        ``transform_children`` 内で ``score_1`` や ``score_N`` を計算する際に使う。
        戻り値の整数は「高いほど優先度が高い」ため、そのままスコア列に代入できる。

        Args:
            df: 申込者 DataFrame。
            rules: ソートルールのリスト。各要素は ``(列名, "asc"|"desc")`` のタプル。
                例: ``[("指数合計", "desc"), ("優先順位2", "asc")]``
                空リストを渡すと入力順のまま n, n-1, ..., 1 を返す。

        Returns:
            df と同じインデックスを持つ ``pd.Series[int]``。
            値は 1〜len(df) の整数で、高いほど優先度が高い。
            NaN 値は最低優先（リスト末尾）として扱われる。
            全キーが同値の行は入力順を維持する（安定ソート）。

        Raises:
            ValueError: direction が ``"asc"`` でも ``"desc"`` でもない場合。
        """
        n = len(df)
        if not rules:
            return pd.Series(range(n, 0, -1), index=df.index)

        cols = []
        ascending = []
        for col, direction in rules:
            if direction not in ("asc", "desc"):
                raise ValueError(f"rank_by の direction は 'asc' か 'desc' のみ有効です: {direction!r}")
            cols.append(col)
            ascending.append(direction == "asc")

        sorted_idx = df.sort_values(by=cols, ascending=ascending, na_position="last", kind="stable").index
        rank_values = pd.Series(range(n, 0, -1), index=sorted_idx)
        return rank_values.reindex(df.index)
