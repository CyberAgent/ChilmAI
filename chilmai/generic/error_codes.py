"""API、UI、Python 呼び出し元で共有する ChilmAI エラーコード。"""

from __future__ import annotations

from enum import IntEnum


class ErrorCode(IntEnum):
    # 1xx — 設定エラー（列名マッピング・出力列名設定）
    MISSING_CHILDREN_COLUMNS = 101
    MISSING_DAYCARE_COLUMNS = 102
    MISSING_PREF_COLUMNS = 103
    MISSING_SCORE_COLUMN = 104
    CHILD_ID_COL_NOT_FOUND = 105
    DUPLICATE_OUTPUT_COL_NAMES = 106
    OUTPUT_COL_CONFLICTS_INPUT = 107

    # 2xx — データエラー（入力ファイル内容）
    EMPTY_ID_FIELD = 201
    DUPLICATE_CHILD_ID = 202
    NON_INTEGER_AGE = 203
    NON_INTEGER_SCORE = 204
    EMPTY_DAYCARE_ID = 205
    NEGATIVE_CAPACITY = 206
    NON_INTEGER_CAPACITY = 207
    DUPLICATE_DAYCARE_ID = 208
    UNKNOWN_DAYCARE_IN_PREF = 209
    NO_PREFERENCES = 210
    UNKNOWN_ENROLLED_DAYCARE = 211
    ENROLLED_IN_PREF = 212
    INVALID_SIBLING_PATTERN = 213
    SIBLING_PATTERN_MISMATCH = 214
    SIBLING_PATTERN_BLANK_IN_HOUSEHOLD = 215
    INVALID_AGE_RANGE = 216
    EMPTY_SCORE_1 = 217
    COMBINATION_FILE_MISSING_COLUMNS = 218
    COMBINATION_INVALID_RANK = 219
    COMBINATION_UNKNOWN_HOUSEHOLD = 220
    COMBINATION_UNKNOWN_CHILD_CODE = 221
    COMBINATION_UNKNOWN_DAYCARE = 222
    SIBLING_NO_COMMON_PREFERENCE = 223

    # 4xx — ファイル形式エラー（パーサー）
    UNSUPPORTED_FILE_FORMAT = 401
    DUPLICATE_COLUMN_AFTER_NORM = 402
    SCORE_COLUMN_CONFLICT_1 = 403
    SCORE_COLUMN_CONFLICT_2 = 404
    CSV_ENCODING_ERROR = 405

    # 5xx — ソルバーエラー
    SOLVER_INFEASIBLE = 501
    SOLVER_TIMEOUT = 502
    SOLVER_UNEXPECTED_STATUS = 503
    SOLVER_VERIFICATION_FAILED = 504

    # IntEnum の str() は Python 3.10 では "ErrorCode.SOLVER_INFEASIBLE"、
    # 3.11 以降では "501" を返す。テンプレートは str() で描画するため、
    # 全バージョンで数値表示に固定する。
    def __str__(self) -> str:
        return str(self.value)


class ChilmError(ValueError):
    """数値エラーコードを持つ ValueError サブクラス。既存の except ValueError で捕捉可能。"""

    def __init__(self, message: str, *, code: int) -> None:
        super().__init__(message)
        self.code = code
