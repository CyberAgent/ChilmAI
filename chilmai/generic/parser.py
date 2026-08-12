"""CSV/XLSX を読み込み、利用者が設定した列名を ChilmAI 内部列へ対応付ける。"""

from __future__ import annotations

import re
import unicodedata
from io import BytesIO
from typing import IO, Literal

import pandas as pd

from chilmai.generic.error_codes import ChilmError, ErrorCode

FileFormat = Literal["csv", "excel"]


def numbered_pattern(template: str) -> re.Pattern[str]:
    """列名テンプレート内の数字部分を取り出す正規表現を作る。

    小文字 ASCII が直後に続かない大文字 `N` を、数字の位置として扱う。
    該当する `N` がない場合は、テンプレート末尾に数字が続くものとして扱う。
    複数の `N` が該当する場合は、最初の `N` だけを使う。
    `No.` のように `N` の直後が小文字の場合はプレースホルダではなく文字として扱う。
    `NAME_` のように大文字 ASCII と隣接する `N` はプレースホルダ扱いになるため、
    そのようなテンプレートは避ける。

    例:
        "N歳定員"  → ^(\\d+)歳定員$   は 0歳定員, 1歳定員 ... に一致
        "定員N"    → ^定員(\\d+)$      は 定員0, 定員1 ... に一致
        "No."      → ^No\\.(\\d+)$      は No.1, No.2 ... に一致（N は文字扱い）
        "capacity_age" → ^capacity_age(\\d+)$
    """
    m = re.search(r"N(?![a-z])", template)
    if m:
        idx = m.start()
        before = re.escape(template[:idx])
        after = re.escape(template[idx + 1 :])
        return re.compile(rf"^{before}(\d+){after}$", re.ASCII)
    return re.compile(rf"^{re.escape(template)}(\d+)$", re.ASCII)


class InputParser:
    """アップロードされたファイルを正規化済みの `pandas.DataFrame` に変換する。

    CSV と Excel を受け付け、全角を含む列名を NFKC で正規化し、
    利用者が設定した列名を `child_id`, `pref_1`, `capacity_age0` などの
    ChilmAI 内部列名へ変換する。
    """

    @staticmethod
    def _normalize_file_format(file_format: str) -> FileFormat:
        normalized = file_format.lower().strip()
        if normalized == "csv":
            return "csv"
        if normalized in {"excel", "xlsx", "xls", "xlsm", "xlsb"}:
            return "excel"
        raise ChilmError(f"Unsupported file format: {file_format}", code=ErrorCode.UNSUPPORTED_FILE_FORMAT)

    @staticmethod
    def _read_csv(source: IO[bytes] | BytesIO, **kwargs) -> pd.DataFrame:
        """CSV を読み込む。UTF-8 以外の文字コードは分かりやすいエラーへ変換する。

        Excel の既定の「CSV (コンマ区切り)」保存は Shift-JIS になるため、UTF-8 前提の
        `pd.read_csv` が `UnicodeDecodeError` を送出する。この生の英語例外をそのまま画面に
        出すと利用者が原因を特定できないため、エラーコード付きの日本語メッセージ
        （ErrorCode.CSV_ENCODING_ERROR）に変換する。
        """
        try:
            return pd.read_csv(source, **kwargs)
        except UnicodeDecodeError as exc:
            raise ChilmError(
                "ファイルの文字コードが UTF-8 ではないため読み込めませんでした。"
                "Excel の「名前を付けて保存」で「CSV UTF-8 (コンマ区切り)」形式を選んで保存し直すか、"
                "Excel 形式（.xlsx）のままアップロードしてください。",
                code=ErrorCode.CSV_ENCODING_ERROR,
            ) from exc

    @classmethod
    def _read_dataframe(cls, file_bytes: bytes, file_format: str) -> pd.DataFrame:
        normalized = cls._normalize_file_format(file_format)
        buffer = BytesIO(file_bytes)
        if normalized == "csv":
            return cls._read_csv(buffer, dtype=str)
        # calamine (MIT) を明示。pandas は .xlsb の既定エンジンとして LGPLv3 の
        # pyxlsb を選ぶが、これを廃し xlsx/xls/xlsm/xlsb を単一エンジンで読む。
        # engine を省くと pyxlsb 不在時に xlsb で ImportError になる。
        return pd.read_excel(buffer, sheet_name=0, dtype=str, engine="calamine")

    @classmethod
    def read_columns(cls, fileobj: IO[bytes], file_format: str) -> list[str]:
        normalized = cls._normalize_file_format(file_format)
        if normalized == "csv":
            df = cls._read_csv(fileobj, dtype=str, nrows=0)
        else:
            df = pd.read_excel(fileobj, sheet_name=0, dtype=str, nrows=0, engine="calamine")
        return [unicodedata.normalize("NFKC", str(c)) for c in df.columns if c is not None]

    @staticmethod
    def _apply_mapping(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
        _PREFIX_KEYS = {"preference_prefix", "score_prefix", "capacity_prefix"}

        # Normalize column names: full-width digits/letters → half-width (NFKC).
        # str(col) handles non-string columns (numeric, datetime) from Excel files.
        norm_map = {col: unicodedata.normalize("NFKC", str(col)) for col in df.columns}
        seen: set[str] = set()
        duplicates: list[str] = []
        for normalized in norm_map.values():
            if normalized in seen:
                duplicates.append(normalized)
            seen.add(normalized)
        if duplicates:
            raise ChilmError(
                f"正規化後に列名が重複します（全角・半角の混在を確認してください）: {duplicates}",
                code=ErrorCode.DUPLICATE_COLUMN_AFTER_NORM,
            )
        df = df.rename(columns=norm_map)

        rename_map: dict[str, str] = {}
        for internal_name, user_name in mapping.items():
            if internal_name in _PREFIX_KEYS:
                continue
            normalized_user_name = (
                unicodedata.normalize("NFKC", str(user_name)) if user_name is not None else user_name
            )
            if normalized_user_name in df.columns:
                rename_map[normalized_user_name] = internal_name

        mapped = df.rename(columns=rename_map)

        # Convert preference columns (e.g. 希望保育園ID_1) to pref_1, pref_2 ...
        pref_pattern = numbered_pattern(
            unicodedata.normalize("NFKC", mapping.get("preference_prefix", "pref_"))
        )
        for col in list(mapped.columns):
            if not isinstance(col, str):
                continue
            if re.fullmatch(r"pref_\d+", col, re.ASCII):
                continue
            m = pref_pattern.fullmatch(col)
            if m:
                mapped = mapped.rename(columns={col: f"pref_{m.group(1)}"})

        # Convert score columns (e.g. スコア1) to score_1, score_2 ...
        score_pattern = numbered_pattern(
            unicodedata.normalize("NFKC", mapping.get("score_prefix", "score_"))
        )
        for col in list(mapped.columns):
            if not isinstance(col, str):
                continue
            if re.fullmatch(r"score_\d+", col, re.ASCII):
                continue
            m = score_pattern.fullmatch(col)
            if m:
                mapped = mapped.rename(columns={col: f"score_{m.group(1)}"})

        # Allow bare "score" column (no suffix) as an alias for "score_1".
        if "score" in mapped.columns:
            score_numbered = [
                c for c in mapped.columns if isinstance(c, str) and re.fullmatch(r"score_\d+", c)
            ]
            if score_numbered:
                if "score_1" in score_numbered:
                    raise ChilmError(
                        "「score」列と「score_1」列が両方存在します。どちらか一方だけを使用してください。",
                        code=ErrorCode.SCORE_COLUMN_CONFLICT_1,
                    )
                raise ChilmError(
                    f"「score」列と番号付きスコア列（{score_numbered[0]} など）が混在しています。"
                    "「score_1」から始まる列名を使用してください。",
                    code=ErrorCode.SCORE_COLUMN_CONFLICT_2,
                )
            mapped = mapped.rename(columns={"score": "score_1"})

        # 整数を表す '.0' サフィックスを除去する（pandas が float→str 化した値や
        # Excel/CSV の生データに '512200400.0' のような値が含まれるケースを救済）。
        # 整数値以外の小数（'100.5' 等）は validator が後段で弾けるよう手を加えない。
        _DOT_ZERO_RE = re.compile(r"^(-?\d+)\.0+$")
        for col in list(mapped.columns):
            if isinstance(col, str) and re.fullmatch(r"score_\d+", col, re.ASCII):
                mapped[col] = mapped[col].map(
                    lambda v: _DOT_ZERO_RE.sub(r"\1", str(v).strip()) if pd.notna(v) else v
                )

        # Convert capacity columns (e.g. N歳定員, 定員N) to capacity_age0, capacity_age1 ...
        capacity_pattern = numbered_pattern(
            unicodedata.normalize("NFKC", mapping.get("capacity_prefix", "capacity_age"))
        )
        for col in list(mapped.columns):
            if not isinstance(col, str):
                continue
            if re.fullmatch(r"capacity_age\d+", col, re.ASCII):
                continue
            m = capacity_pattern.fullmatch(col)
            if m:
                mapped = mapped.rename(columns={col: f"capacity_age{m.group(1)}"})

        return mapped

    def read_raw(self, *, file_bytes: bytes, file_format: str) -> pd.DataFrame:
        """ChilmAI の列名マッピングを適用せずにファイルを読み込む。"""
        return self._read_dataframe(file_bytes, file_format)

    def parse_children(
        self,
        *,
        file_bytes: bytes,
        file_format: str,
        mapping: dict[str, str],
    ) -> pd.DataFrame:
        """申込者データを読み込み、申込者用の列名マッピングを適用する。"""
        df = self._read_dataframe(file_bytes, file_format)
        return self._apply_mapping(df, mapping)

    def parse_daycares(
        self,
        *,
        file_bytes: bytes,
        file_format: str,
        mapping: dict[str, str],
    ) -> pd.DataFrame:
        """保育所データを読み込み、保育所用の列名マッピングを適用する。"""
        df = self._read_dataframe(file_bytes, file_format)
        return self._apply_mapping(df, mapping)

    def parse_combination(
        self,
        *,
        file_bytes: bytes,
        file_format: str,
        mapping: dict[str, str],
    ) -> pd.DataFrame:
        """組み合わせファイルを読み込み、内部列名へ変換して返す。

        Returns:
            以下の内部列を持つ DataFrame:

                - household_id (str): ファミリーコード
                - rank (str): 総当たり順位
                - child_code_0 (str | float): 宛名コード1（0-indexed）。列が存在しない行は NaN。
                - child_code_1 (str | float): 宛名コード2（0-indexed）、以降同様。列が存在しない行は NaN。
                - facility_0 (str | float): 希望施設1（0-indexed）。列が存在しない行は NaN。
                - facility_1 (str | float): 希望施設2（0-indexed）、以降同様。列が存在しない行は NaN。
        """
        df = self._read_dataframe(file_bytes, file_format)

        # NFKC 正規化
        norm_cols = {col: unicodedata.normalize("NFKC", str(col)) for col in df.columns}
        seen: set[str] = set()
        duplicates: list[str] = []
        for normalized in norm_cols.values():
            if normalized in seen:
                duplicates.append(normalized)
            seen.add(normalized)
        if duplicates:
            raise ChilmError(
                f"正規化後に列名が重複します: {duplicates}",
                code=ErrorCode.DUPLICATE_COLUMN_AFTER_NORM,
            )
        df = df.rename(columns=norm_cols)

        # 単一列のリネーム（household_id, rank）
        rename_map: dict[str, str] = {}
        for internal, user in (
            ("household_id", mapping.get("household_id", "ファミリーコード")),
            ("rank", mapping.get("rank", "総当たり順位")),
        ):
            normalized_user = unicodedata.normalize("NFKC", str(user)) if user else ""
            if normalized_user in df.columns:
                rename_map[normalized_user] = internal
        df = df.rename(columns=rename_map)

        # child_code_prefix → child_code_0, child_code_1, ...
        child_tmpl = unicodedata.normalize("NFKC", mapping.get("child_code_prefix", "宛名コードN"))
        child_pat = numbered_pattern(child_tmpl)
        for col in list(df.columns):
            if not isinstance(col, str):
                continue
            if re.fullmatch(r"child_code_\d+", col, re.ASCII):
                continue
            m = child_pat.fullmatch(col)
            if m:
                num = int(m.group(1))
                if num < 1:
                    continue  # 0始まり列は不正（負の内部列名を生成しない）
                df = df.rename(columns={col: f"child_code_{num - 1}"})

        # facility_prefix → facility_0, facility_1, ...
        facility_tmpl = unicodedata.normalize("NFKC", mapping.get("facility_prefix", "希望施設N"))
        facility_pat = numbered_pattern(facility_tmpl)
        for col in list(df.columns):
            if not isinstance(col, str):
                continue
            if re.fullmatch(r"facility_\d+", col, re.ASCII):
                continue
            m = facility_pat.fullmatch(col)
            if m:
                num = int(m.group(1))
                if num < 1:
                    continue  # 0始まり列は不正（負の内部列名を生成しない）
                df = df.rename(columns={col: f"facility_{num - 1}"})

        return df
