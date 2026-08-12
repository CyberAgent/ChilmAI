"""列名マッピングと名前付きプロファイルの設定保存を扱う。"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
DEFAULT_PROFILE_NAME = "default"

_DEFAULT_PROFILE_DATA: dict[str, dict[str, str]] = {
    "children": {
        "child_id": "申請者番号",
        "household_id": "世帯番号",
        "age": "年齢",
        "score": "",
        "score_prefix": "点数N",
        "preference_prefix": "希望保育園ID_N",
        "enrolled_daycare_id": "在籍保育所ID",
        "sibling_pattern": "きょうだいパターン",
    },
    "daycares": {
        "daycare_id": "保育所ID",
        "daycare_name": "保育所名",
        "capacity_prefix": "N歳募集人数",
    },
    "output": {
        "result_daycare_id": "入所選考結果保育所ID",
        "result_daycare_name": "入所選考結果保育所名",
        "exclude_transfer_back": "false",
    },
    "combination": {
        "household_id": "ファミリーコード",
        "rank": "総当たり順位",
        "child_code_prefix": "宛名コードN",
        "facility_prefix": "希望施設N",
    },
}

# Public default value of a profile's mapping. Existing call sites that
# import DEFAULT_CONFIG continue to receive the same shape as before (a
# flat mapping with children/daycares/output sections).
DEFAULT_CONFIG: dict[str, dict[str, str]] = _DEFAULT_PROFILE_DATA

_PROFILE_SECTIONS = ("children", "daycares", "output", "combination")

_PROFILE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_\-぀-ヿ㐀-鿿（）() 　]+$")
_MAX_PROFILE_NAME_LENGTH = 50


def _default_store() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "active_profile": DEFAULT_PROFILE_NAME,
        "profiles": {DEFAULT_PROFILE_NAME: deepcopy(_DEFAULT_PROFILE_DATA)},
    }


def _normalize_profile(raw: Any) -> dict[str, dict[str, str]]:
    normalized = deepcopy(_DEFAULT_PROFILE_DATA)
    if not isinstance(raw, dict):
        return normalized
    for section in _PROFILE_SECTIONS:
        section_map = raw.get(section, {})
        if not isinstance(section_map, dict):
            continue
        for key in normalized[section]:
            value = section_map.get(key)
            if isinstance(value, str) and value.strip():
                normalized[section][key] = value.strip()
    return normalized


def _coerce_save_input(config: Any) -> dict[str, dict[str, str]]:
    normalized = deepcopy(_DEFAULT_PROFILE_DATA)
    if not isinstance(config, dict):
        return normalized
    for section in _PROFILE_SECTIONS:
        section_map = config.get(section, {})
        if not isinstance(section_map, dict):
            continue
        for key, value in section_map.items():
            if not isinstance(key, str):
                continue
            if key not in normalized[section]:
                continue
            if isinstance(value, str) and value.strip():
                normalized[section][key] = value.strip()
    return normalized


def _validate_profile_name(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("プロファイル名は文字列で指定してください。")
    stripped = name.strip()
    if not stripped:
        raise ValueError("プロファイル名を入力してください。")
    if len(stripped) > _MAX_PROFILE_NAME_LENGTH:
        raise ValueError(f"プロファイル名は{_MAX_PROFILE_NAME_LENGTH}文字以内で指定してください。")
    if not _PROFILE_NAME_PATTERN.match(stripped):
        raise ValueError(
            "プロファイル名に使用できない文字が含まれています。"
            "英数字・日本語・スペース・ハイフン・アンダースコアのみ使用できます。"
        )
    return stripped


class ConfigStore:
    """ChilmAI の列名マッピングプロファイルを保存・管理する。

    `ConfigStore` は、名前付きプロファイルを含むバージョン付き JSON を保存する。
    後方互換用の `load()` / `save()` は、現在アクティブなプロファイルを対象にする。
    """

    def __init__(self, path: str | Path = "data/config.json") -> None:
        """`path` を保存先としてストアを作成する。"""
        self.path = Path(path)

    # ----- Internal raw I/O ---------------------------------------------------
    def _read_raw(self) -> dict[str, Any]:
        if not self.path.exists():
            return _default_store()
        try:
            with self.path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            return _default_store()
        return self._migrate(raw)

    def _migrate(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            return _default_store()

        # v2 already
        if isinstance(raw.get("profiles"), dict) and raw.get("profiles"):
            profiles_raw = raw["profiles"]
            normalized_profiles: dict[str, dict[str, dict[str, str]]] = {}
            for name, profile_data in profiles_raw.items():
                if not isinstance(name, str):
                    continue
                try:
                    valid_name = _validate_profile_name(name)
                except ValueError:
                    continue
                normalized_profiles[valid_name] = _normalize_profile(profile_data)
            if not normalized_profiles:
                normalized_profiles[DEFAULT_PROFILE_NAME] = deepcopy(_DEFAULT_PROFILE_DATA)
            active = raw.get("active_profile")
            if not isinstance(active, str) or active not in normalized_profiles:
                active = (
                    DEFAULT_PROFILE_NAME
                    if DEFAULT_PROFILE_NAME in normalized_profiles
                    else next(iter(normalized_profiles))
                )
            return {
                "schema_version": SCHEMA_VERSION,
                "active_profile": active,
                "profiles": normalized_profiles,
            }

        # v1: flat mapping with children/daycares/output at the top level
        store = _default_store()
        store["profiles"][DEFAULT_PROFILE_NAME] = _normalize_profile(raw)
        return store

    def _write_raw(self, store: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=2)

    # ----- Backwards-compatible API ------------------------------------------
    def load(self) -> dict[str, dict[str, str]]:
        """アクティブプロファイルのマッピング（children/daycares/output）を返す。"""
        store = self._read_raw()
        active = store["active_profile"]
        return deepcopy(store["profiles"][active])

    def save(self, config: dict[str, Any]) -> dict[str, dict[str, str]]:
        """指定されたマッピングを現在のアクティブプロファイルへ保存する。"""
        normalized = _coerce_save_input(config)
        store = self._read_raw()
        active = store["active_profile"]
        store["profiles"][active] = normalized
        self._write_raw(store)
        return deepcopy(normalized)

    # ----- Profile management -------------------------------------------------
    @staticmethod
    def _ordered_profile_names(names: list[str]) -> list[str]:
        rest = sorted(n for n in names if n != DEFAULT_PROFILE_NAME)
        if DEFAULT_PROFILE_NAME in names:
            return [DEFAULT_PROFILE_NAME] + rest
        return sorted(names)

    def snapshot(self) -> dict[str, Any]:
        """アクティブ設定、アクティブ名、プロファイル名一覧を1回の読み込みで返す。"""
        store = self._read_raw()
        active = store["active_profile"]
        return {
            "active_config": deepcopy(store["profiles"][active]),
            "active_name": active,
            "profile_names": self._ordered_profile_names(list(store["profiles"].keys())),
        }

    def list_profiles(self) -> list[str]:
        """プロファイル名一覧を返す。default がある場合は先頭に置く。"""
        store = self._read_raw()
        return self._ordered_profile_names(list(store["profiles"].keys()))

    def get_active_name(self) -> str:
        """アクティブプロファイル名を返す。"""
        return self._read_raw()["active_profile"]

    def set_active(self, name: str) -> str:
        """アクティブプロファイルを切り替え、正規化済みの名前を返す。"""
        valid_name = _validate_profile_name(name)
        store = self._read_raw()
        if valid_name not in store["profiles"]:
            raise ValueError(f"プロファイル「{valid_name}」は存在しません。")
        store["active_profile"] = valid_name
        self._write_raw(store)
        return valid_name

    def create_profile(self, name: str, *, source: str | None = None) -> str:
        """プロファイルを作成する。必要に応じて別プロファイルの値を複製する。"""
        valid_name = _validate_profile_name(name)
        store = self._read_raw()
        if valid_name in store["profiles"]:
            raise ValueError(f"プロファイル「{valid_name}」は既に存在します。")
        if source is None:
            store["profiles"][valid_name] = deepcopy(_DEFAULT_PROFILE_DATA)
        else:
            valid_source = _validate_profile_name(source)
            if valid_source not in store["profiles"]:
                raise ValueError(f"複製元のプロファイル「{valid_source}」が見つかりません。")
            store["profiles"][valid_name] = deepcopy(store["profiles"][valid_source])
        self._write_raw(store)
        return valid_name

    def duplicate_profile(self, source: str, new_name: str) -> str:
        """`source` を複製して `new_name` を作成する。"""
        return self.create_profile(new_name, source=source)

    def rename_profile(self, old_name: str, new_name: str) -> str:
        """default 以外のプロファイルをリネームし、新しい名前を返す。"""
        valid_old = _validate_profile_name(old_name)
        valid_new = _validate_profile_name(new_name)
        if valid_old == DEFAULT_PROFILE_NAME:
            raise ValueError("デフォルトプロファイルの名前は変更できません。")
        store = self._read_raw()
        if valid_old not in store["profiles"]:
            raise ValueError(f"プロファイル「{valid_old}」は存在しません。")
        if valid_old == valid_new:
            return valid_old
        if valid_new in store["profiles"]:
            raise ValueError(f"プロファイル「{valid_new}」は既に存在します。")
        store["profiles"][valid_new] = store["profiles"].pop(valid_old)
        if store["active_profile"] == valid_old:
            store["active_profile"] = valid_new
        self._write_raw(store)
        return valid_new

    def delete_profile(self, name: str) -> str:
        """default 以外のプロファイルを削除し、削除後のアクティブ名を返す。"""
        valid_name = _validate_profile_name(name)
        if valid_name == DEFAULT_PROFILE_NAME:
            raise ValueError("デフォルトプロファイルは削除できません。")
        store = self._read_raw()
        if valid_name not in store["profiles"]:
            raise ValueError(f"プロファイル「{valid_name}」は存在しません。")
        del store["profiles"][valid_name]
        if store["active_profile"] == valid_name:
            if DEFAULT_PROFILE_NAME in store["profiles"]:
                store["active_profile"] = DEFAULT_PROFILE_NAME
            elif store["profiles"]:
                store["active_profile"] = next(iter(store["profiles"]))
            else:
                store["profiles"][DEFAULT_PROFILE_NAME] = deepcopy(_DEFAULT_PROFILE_DATA)
                store["active_profile"] = DEFAULT_PROFILE_NAME
        self._write_raw(store)
        return store["active_profile"]

    def reset_active(self) -> dict[str, dict[str, str]]:
        """アクティブプロファイルのマッピングをデフォルトに戻す。他プロファイルは維持する。"""
        store = self._read_raw()
        active = store["active_profile"]
        store["profiles"][active] = deepcopy(_DEFAULT_PROFILE_DATA)
        self._write_raw(store)
        return deepcopy(store["profiles"][active])
