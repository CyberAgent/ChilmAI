"""検証とマッチングを扱う上位 Python API。"""

from __future__ import annotations

import unicodedata
from typing import Any

import pandas as pd

from chilmai.generic.error_codes import ChilmError, ErrorCode
from chilmai.generic.matcher import CpSatMatcher, norm_id
from chilmai.generic.parser import InputParser
from chilmai.generic.preprocessor import BasePreprocessor
from chilmai.generic.validator import ValidationService


def _resolve_original_col(col: str, df: pd.DataFrame) -> str:
    """NFKC 正規化後に `col` と一致する、df 上の実際の列名を返す。

    設定には read_columns() が表示した NFKC 正規化済みの列名が保存される一方、
    read_raw() は元ファイルの全角文字を保持するため、この解決が必要になる。
    """
    if col in df.columns:
        return col
    norm_col = unicodedata.normalize("NFKC", col)
    for actual in df.columns:
        if unicodedata.normalize("NFKC", str(actual)) == norm_col:
            return actual
    return col


class MatchingService:
    """パース、検証、マッチング、結果整形をまとめて扱う。

    FastAPI の HTTP レイヤーを経由せずに ChilmAI を実行したいアプリケーション向けの
    推奨 Python API エントリポイント。
    """

    def __init__(self, preprocessor: BasePreprocessor | None = None) -> None:
        self.preprocessor = preprocessor or BasePreprocessor()
        self.parser = InputParser()
        self.validator = ValidationService()
        self.matcher = CpSatMatcher()

    def _parse_combination(
        self,
        combination_file_bytes: bytes,
        combination_file_format: str,
        mapping: dict[str, dict[str, str]],
        children_df: pd.DataFrame,
        daycares_df: pd.DataFrame,
    ) -> tuple[pd.DataFrame | None, list[dict[str, Any]]]:
        """組み合わせファイルをパースして検証する。成功時は (DataFrame, [])、失敗時は (None, errors)。"""
        try:
            combination_df = self.parser.parse_combination(
                file_bytes=combination_file_bytes,
                file_format=combination_file_format,
                mapping=mapping.get("combination", {}),
            )
        except ChilmError as e:
            return None, [{"message": str(e), "type": "format", "code": e.code}]
        combo_errors = self.validator.validate_combination(
            combination_df,
            children_df,
            daycares_df,
            combination_mapping=mapping.get("combination", {}),
            children_mapping=mapping.get("children", {}),
        )
        if combo_errors:
            return None, combo_errors
        return combination_df, []

    def validate(
        self,
        *,
        children_file_bytes: bytes,
        children_file_format: str,
        daycares_file_bytes: bytes,
        daycares_file_format: str,
        mapping: dict[str, dict[str, str]],
        combination_file_bytes: bytes | None = None,
        combination_file_format: str | None = None,
    ) -> dict[str, Any]:
        """アップロードされた申込者ファイルと保育所ファイルを検証する。

        公開 `/validate` HTTP エンドポイントと同じ構造を返す。
        """
        children_df = self.parser.parse_children(
            file_bytes=children_file_bytes,
            file_format=children_file_format,
            mapping=mapping.get("children", {}),
        )
        daycares_df = self.parser.parse_daycares(
            file_bytes=daycares_file_bytes,
            file_format=daycares_file_format,
            mapping=mapping.get("daycares", {}),
        )
        custom_errors = self.preprocessor.validate(children_df, daycares_df)
        if custom_errors:
            return {
                "is_valid": False,
                "errors": custom_errors,
                "warnings": [],
                "summary": {
                    "children_count": int(len(children_df)),
                    "daycares_count": int(len(daycares_df)),
                },
            }
        children_df = self.preprocessor.transform_children(children_df)
        daycares_df = self.preprocessor.transform_daycares(daycares_df)

        combination_df: pd.DataFrame | None = None
        if combination_file_bytes and combination_file_format:
            combination_df, combo_errors = self._parse_combination(
                combination_file_bytes,
                combination_file_format,
                mapping,
                children_df,
                daycares_df,
            )
            if combo_errors:
                return {
                    "is_valid": False,
                    "errors": combo_errors,
                    "warnings": [],
                    "summary": {
                        "children_count": int(len(children_df)),
                        "daycares_count": int(len(daycares_df)),
                    },
                }

        return self.validator.validate(
            children_df,
            daycares_df,
            children_mapping=mapping.get("children", {}),
            daycares_mapping=mapping.get("daycares", {}),
            combination_df=combination_df,
        )

    def match(
        self,
        *,
        children_file_bytes: bytes,
        children_file_format: str,
        daycares_file_bytes: bytes,
        daycares_file_format: str,
        mapping: dict[str, dict[str, str]],
        solver_config: dict[str, Any] | None = None,
        combination_file_bytes: bytes | None = None,
        combination_file_format: str | None = None,
    ) -> dict[str, Any]:
        """アップロードされたファイルを検証し、CP-SAT マッチングを実行する。

        公開 `/match` HTTP エンドポイントと同じ中核結果に加え、
        Web UI の Excel 出力で使う出力列・行データを返す。
        """
        children_df = self.parser.parse_children(
            file_bytes=children_file_bytes,
            file_format=children_file_format,
            mapping=mapping.get("children", {}),
        )
        daycares_df = self.parser.parse_daycares(
            file_bytes=daycares_file_bytes,
            file_format=daycares_file_format,
            mapping=mapping.get("daycares", {}),
        )
        custom_errors = self.preprocessor.validate(children_df, daycares_df)
        if custom_errors:
            raise ValueError(
                "Validation failed",
                {
                    "is_valid": False,
                    "errors": custom_errors,
                    "warnings": [],
                    "summary": {
                        "children_count": int(len(children_df)),
                        "daycares_count": int(len(daycares_df)),
                    },
                },
            )
        children_df = self.preprocessor.transform_children(children_df)
        daycares_df = self.preprocessor.transform_daycares(daycares_df)

        combination_df: pd.DataFrame | None = None
        if combination_file_bytes and combination_file_format:
            combination_df, combo_errors = self._parse_combination(
                combination_file_bytes,
                combination_file_format,
                mapping,
                children_df,
                daycares_df,
            )
            if combo_errors:
                raise ValueError(
                    "Validation failed",
                    {
                        "is_valid": False,
                        "errors": combo_errors,
                        "warnings": [],
                        "summary": {
                            "children_count": int(len(children_df)),
                            "daycares_count": int(len(daycares_df)),
                        },
                    },
                )

        validation = self.validator.validate(
            children_df,
            daycares_df,
            children_mapping=mapping.get("children", {}),
            daycares_mapping=mapping.get("daycares", {}),
            combination_df=combination_df,
        )
        if not validation["is_valid"]:
            raise ValueError("Validation failed", validation)
        config = solver_config or {}
        max_time_seconds = float(config.get("max_time_seconds", 10.0))
        result = self.matcher.match(
            children_df,
            daycares_df,
            max_time_seconds=max_time_seconds,
            combination_df=combination_df,
        )

        original_df = self.parser.read_raw(file_bytes=children_file_bytes, file_format=children_file_format)
        child_id_col = mapping.get("children", {}).get("child_id", "child_id")
        output_config = mapping.get("output", {})
        result_id_col = output_config.get("result_daycare_id", "入所選考結果保育所ID")
        result_name_col = output_config.get("result_daycare_name", "入所選考結果保育所名")

        child_id_col = _resolve_original_col(child_id_col, original_df)
        if child_id_col not in original_df.columns:
            if "child_id" in original_df.columns:
                child_id_col = "child_id"
            else:
                raise ChilmError(
                    f"申込者ファイルに「{child_id_col}」列が見つかりません。"
                    "設定画面で「申請者ID」の列名を確認してください。",
                    code=ErrorCode.CHILD_ID_COL_NOT_FOUND,
                )

        if result_id_col == result_name_col:
            raise ChilmError(
                f"出力列名の設定が重複しています: '{result_id_col}'"
                "「入所選考結果保育所ID」と「入所選考結果保育所名」に別々の列名を設定してください。",
                code=ErrorCode.DUPLICATE_OUTPUT_COL_NAMES,
            )
        norm_original_cols = {unicodedata.normalize("NFKC", str(c)) for c in original_df.columns}
        conflicts = [
            col
            for col in (result_id_col, result_name_col)
            if unicodedata.normalize("NFKC", col) in norm_original_cols
        ]
        if conflicts:
            raise ChilmError(
                f"出力列名が申込者ファイルの既存列と重複しています: {conflicts}"
                "設定画面で別の列名に変更してください。",
                code=ErrorCode.OUTPUT_COL_CONFLICTS_INPUT,
            )

        matching_result_dict: dict[str, str | None] = result["matching_result_dict"]
        daycare_name_dict: dict[str, str] = result.get("daycare_name_dict", {})

        child_id_series = original_df[child_id_col].map(lambda v: norm_id(str(v)))
        result_id_series = child_id_series.map(matching_result_dict).fillna("")
        result_name_series = result_id_series.map(daycare_name_dict).fillna("")

        enrolled_id_col = mapping.get("children", {}).get("enrolled_daycare_id", "在籍保育所ID")
        enrolled_id_col = _resolve_original_col(enrolled_id_col, original_df)
        if enrolled_id_col not in original_df.columns and "enrolled_daycare_id" in original_df.columns:
            enrolled_id_col = "enrolled_daycare_id"
        if enrolled_id_col in original_df.columns:
            enrolled_id_series = original_df[enrolled_id_col].map(
                lambda v: "" if pd.isna(v) else norm_id(str(v))
            )
            same_daycare_mask = (result_id_series != "") & (result_id_series == enrolled_id_series)
            blanked_count = int(same_daycare_mask.sum())
            if blanked_count > 0:
                blanked_ids = set(child_id_series[same_daycare_mask].tolist())

                blanked_only = 0
                blanked_siblings = 0
                for hh in result.get("household_result_dict", {}).values():
                    hh_children = hh.get("child_ids", [])
                    blanked_in_hh = sum(1 for cid in hh_children if cid in blanked_ids)
                    if blanked_in_hh == 0:
                        continue
                    # matcher は世帯人数でバケットを決めるので、
                    # きょうだい世帯で一部の子だけブランクされる場合も siblings として補正する。
                    if len(hh_children) == 1:
                        blanked_only += blanked_in_hh
                    else:
                        blanked_siblings += blanked_in_hh

                age_lookup = dict(
                    zip(
                        children_df["child_id"].map(lambda v: norm_id(str(v))),
                        children_df["age"].map(lambda v: str(int(v))),
                    )
                )
                blanked_by_age: dict[str, int] = {}
                for cid in blanked_ids:
                    age_key = age_lookup.get(cid)
                    if age_key is not None:
                        blanked_by_age[age_key] = blanked_by_age.get(age_key, 0) + 1

                mc = result.get("matched_children", {})
                by_age = {age: {**bucket} for age, bucket in mc.get("by_age", {}).items()}
                for age_key, blanked in blanked_by_age.items():
                    if age_key in by_age:
                        by_age[age_key]["matched"] = max(
                            0,
                            by_age[age_key].get("matched", 0) - blanked,
                        )
                result["matched_children"] = {
                    **mc,
                    "total": mc.get("total", 0) - blanked_count,
                    "only_child": mc.get("only_child", 0) - blanked_only,
                    "siblings": mc.get("siblings", 0) - blanked_siblings,
                    "by_age": by_age,
                }
                result["transfer_back_count"] = blanked_count

                if output_config.get("exclude_transfer_back", "false") == "true":
                    result_id_series = result_id_series.where(~same_daycare_mask, other="")
                    result_name_series = result_name_series.where(~same_daycare_mask, other="")
                    result["matching_result_dict"] = {
                        cid: (None if cid in blanked_ids else did)
                        for cid, did in result["matching_result_dict"].items()
                    }
                    result["household_result_dict"] = {
                        hh_id: {
                            **hh,
                            "assigned": [
                                None if cid in blanked_ids else d
                                for cid, d in zip(hh.get("child_ids", []), hh.get("assigned", []))
                            ],
                            "selected_combo": [
                                None if cid in blanked_ids else d
                                for cid, d in zip(hh.get("child_ids", []), hh.get("selected_combo", []))
                            ],
                        }
                        for hh_id, hh in result.get("household_result_dict", {}).items()
                    }

        output_df = original_df.copy()
        output_df[result_id_col] = result_id_series
        output_df[result_name_col] = result_name_series

        output_df = self.preprocessor.transform_output(output_df, result)

        result["output_columns"] = list(output_df.columns)
        result["output_rows"] = output_df.fillna("").to_dict(orient="records")

        return result
