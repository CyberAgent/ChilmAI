from __future__ import annotations

import json
from pathlib import Path

import pytest

from chilmai.generic.config import (
    DEFAULT_CONFIG,
    DEFAULT_PROFILE_NAME,
    SCHEMA_VERSION,
    ConfigStore,
)


def test_load_returns_default_when_file_not_exists(tmp_path: Path):
    store = ConfigStore(tmp_path / "missing.json")
    loaded = store.load()

    assert loaded == DEFAULT_CONFIG


def test_save_and_load_roundtrip(tmp_path: Path):
    path = tmp_path / "config.json"
    store = ConfigStore(path)

    saved = store.save(
        {
            "children": {
                "child_id": "児童ID",
                "preference_prefix": "希望",
            },
            "daycares": {
                "daycare_id": "園ID",
            },
        }
    )

    loaded = store.load()
    assert saved == loaded
    assert loaded["children"]["child_id"] == "児童ID"
    assert loaded["children"]["preference_prefix"] == "希望"
    assert loaded["daycares"]["daycare_id"] == "園ID"


def test_load_ignores_unknown_keys(tmp_path: Path):
    """旧フォーマットの capacity_age* など未知のキーはロード時に無視する。"""
    path = tmp_path / "config.json"
    path.write_text(
        '{"children": {"child_id": "児童ID", "capacity_age0": "0歳定員"}, "daycares": {"capacity_age0": "0歳募集人数", "capacity_prefix": "N歳定員"}}',
        encoding="utf-8",
    )
    store = ConfigStore(path)
    loaded = store.load()

    assert loaded["children"]["child_id"] == "児童ID"
    assert "capacity_age0" not in loaded["children"]
    assert "capacity_age0" not in loaded["daycares"]
    assert loaded["daycares"]["capacity_prefix"] == "N歳定員"


def test_save_ignores_invalid_values(tmp_path: Path):
    path = tmp_path / "config.json"
    store = ConfigStore(path)

    loaded = store.save(
        {
            "children": {
                "child_id": "",
                "score_prefix": 123,
                "age": "年齢",
            },
            "daycares": {
                "daycare_name": "",
                "capacity_prefix": "N歳枠",
            },
        }
    )

    assert loaded["children"]["child_id"] == DEFAULT_CONFIG["children"]["child_id"]
    assert loaded["children"]["score_prefix"] == DEFAULT_CONFIG["children"]["score_prefix"]
    assert loaded["children"]["age"] == "年齢"
    assert loaded["daycares"]["daycare_name"] == DEFAULT_CONFIG["daycares"]["daycare_name"]
    assert loaded["daycares"]["capacity_prefix"] == "N歳枠"


# ----- v1 -> v2 migration --------------------------------------------------


def test_load_migrates_v1_flat_format(tmp_path: Path):
    """v1 形式（schema_version なし、フラット配置）は default プロファイルへ自動マイグレートされる。"""
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "children": {"child_id": "児童ID"},
                "daycares": {"daycare_id": "園ID"},
                "output": {"result_daycare_id": "結果保育所"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    store = ConfigStore(path)
    loaded = store.load()

    assert loaded["children"]["child_id"] == "児童ID"
    assert loaded["daycares"]["daycare_id"] == "園ID"
    assert loaded["output"]["result_daycare_id"] == "結果保育所"
    assert store.get_active_name() == DEFAULT_PROFILE_NAME
    assert store.list_profiles() == [DEFAULT_PROFILE_NAME]


def test_v1_is_persisted_as_v2_after_save(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"children": {"child_id": "児童ID"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    store = ConfigStore(path)
    store.save(store.load())

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == SCHEMA_VERSION
    assert raw["active_profile"] == DEFAULT_PROFILE_NAME
    assert DEFAULT_PROFILE_NAME in raw["profiles"]
    assert raw["profiles"][DEFAULT_PROFILE_NAME]["children"]["child_id"] == "児童ID"


def test_default_profile_persisted_when_writing(tmp_path: Path):
    path = tmp_path / "config.json"
    store = ConfigStore(path)
    store.save({"children": {"child_id": "ID"}})

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == SCHEMA_VERSION
    assert raw["active_profile"] == DEFAULT_PROFILE_NAME
    assert raw["profiles"][DEFAULT_PROFILE_NAME]["children"]["child_id"] == "ID"


# ----- Profile CRUD --------------------------------------------------------


def test_create_profile_starts_from_defaults(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    store.create_profile("2025年度")

    assert "2025年度" in store.list_profiles()
    assert store.get_active_name() == DEFAULT_PROFILE_NAME  # creating doesn't switch
    store.set_active("2025年度")
    assert store.load()["children"]["child_id"] == DEFAULT_CONFIG["children"]["child_id"]


def test_duplicate_profile_copies_active_values(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    store.save({"children": {"child_id": "申請者ABC"}})
    store.duplicate_profile(DEFAULT_PROFILE_NAME, "コピー")

    store.set_active("コピー")
    assert store.load()["children"]["child_id"] == "申請者ABC"

    # changing one shouldn't affect the other
    store.save({"children": {"child_id": "別の値"}})
    store.set_active(DEFAULT_PROFILE_NAME)
    assert store.load()["children"]["child_id"] == "申請者ABC"


def test_rename_profile_updates_active(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    store.create_profile("旧名")
    store.set_active("旧名")
    store.rename_profile("旧名", "新名")

    assert "新名" in store.list_profiles()
    assert "旧名" not in store.list_profiles()
    assert store.get_active_name() == "新名"


def test_cannot_rename_default(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    with pytest.raises(ValueError):
        store.rename_profile(DEFAULT_PROFILE_NAME, "新規")


def test_cannot_delete_default(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    with pytest.raises(ValueError):
        store.delete_profile(DEFAULT_PROFILE_NAME)


def test_delete_active_falls_back_to_default(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    store.create_profile("A市")
    store.set_active("A市")
    new_active = store.delete_profile("A市")

    assert new_active == DEFAULT_PROFILE_NAME
    assert store.get_active_name() == DEFAULT_PROFILE_NAME
    assert "A市" not in store.list_profiles()


def test_cannot_create_duplicate_profile(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    store.create_profile("X")
    with pytest.raises(ValueError):
        store.create_profile("X")


def test_set_active_unknown_profile_raises(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    with pytest.raises(ValueError):
        store.set_active("存在しない")


def test_profile_name_validation(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    for invalid in ["", "  ", "name/slash", "a" * 51]:
        with pytest.raises(ValueError):
            store.create_profile(invalid)


def test_profile_name_rejects_control_characters(tmp_path: Path):
    """\\s 由来で通り抜けていた改行・タブ・キャリッジリターンを拒否する。"""
    store = ConfigStore(tmp_path / "config.json")
    for invalid in ["with\nnewline", "with\ttab", "with\rcr", "with\vvtab"]:
        with pytest.raises(ValueError):
            store.create_profile(invalid)


def test_profile_name_allows_full_width_space(tmp_path: Path):
    """全角スペースは引き続き許容（業務帳票名で実例あり）。"""
    store = ConfigStore(tmp_path / "config.json")
    store.create_profile("A市　2025")
    assert "A市　2025" in store.list_profiles()


def test_delete_active_when_default_missing_falls_back_to_remaining(tmp_path: Path):
    """default が手動編集等で欠落している v2 ストアでも、アクティブ削除後に未参照プロファイルへ落ちる。"""
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "active_profile": "A市",
                "profiles": {
                    "A市": {"children": {"child_id": "A"}, "daycares": {}, "output": {}},
                    "B市": {"children": {"child_id": "B"}, "daycares": {}, "output": {}},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    store = ConfigStore(path)
    new_active = store.delete_profile("A市")

    assert new_active == "B市"
    assert store.load()["children"]["child_id"] == "B"


def test_delete_active_when_only_one_profile_recreates_default(tmp_path: Path):
    """default を欠いた状態で唯一のアクティブを削除すると、default を再生成して切り替える。"""
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "active_profile": "A市",
                "profiles": {
                    "A市": {"children": {"child_id": "A"}, "daycares": {}, "output": {}},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    store = ConfigStore(path)
    new_active = store.delete_profile("A市")

    assert new_active == DEFAULT_PROFILE_NAME
    assert store.load() == DEFAULT_CONFIG


def test_reset_active_only_resets_current(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    store.save({"children": {"child_id": "AAA"}})
    store.create_profile("別")
    store.set_active("別")
    store.save({"children": {"child_id": "BBB"}})

    store.set_active(DEFAULT_PROFILE_NAME)
    store.reset_active()

    assert store.load()["children"]["child_id"] == DEFAULT_CONFIG["children"]["child_id"]
    store.set_active("別")
    assert store.load()["children"]["child_id"] == "BBB"


def test_list_profiles_default_first(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    store.create_profile("B市")
    store.create_profile("A市")
    profiles = store.list_profiles()
    assert profiles[0] == DEFAULT_PROFILE_NAME
    assert profiles[1:] == ["A市", "B市"]


def test_save_targets_active_profile_only(tmp_path: Path):
    store = ConfigStore(tmp_path / "config.json")
    store.create_profile("別")
    store.set_active("別")
    store.save({"children": {"child_id": "別の値"}})

    store.set_active(DEFAULT_PROFILE_NAME)
    assert store.load()["children"]["child_id"] == DEFAULT_CONFIG["children"]["child_id"]
