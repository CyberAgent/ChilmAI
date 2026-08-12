from __future__ import annotations

import pytest

import apps.api.main as api_main
from chilmai.generic.config import ConfigStore


@pytest.fixture(autouse=True)
def isolated_config_store(tmp_path, monkeypatch):
    """各テストが独立した設定ファイルを使うよう config_store をパッチする。

    data/config.json を直接読み書きするグローバル config_store を、
    tmp_path ベースの ConfigStore に差し替えることで、並列テスト実行時の
    レースコンディションを防ぐ。
    """
    store = ConfigStore(tmp_path / "config.json")
    monkeypatch.setattr(api_main, "config_store", store)
