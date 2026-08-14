# ChilmAI

<p align="center">
  <img src="https://cyberagent.github.io/ChilmAI/assets/logo_yoko_black.svg" alt="ChilmAI" width="360">
</p>

<p align="center">
  <a href="https://github.com/CyberAgent/ChilmAI/actions/workflows/pytest.yml">
    <img src="https://github.com/CyberAgent/ChilmAI/actions/workflows/pytest.yml/badge.svg" alt="pytest">
  </a>
  <a href="https://github.com/CyberAgent/ChilmAI/actions/workflows/pytest_win.yml">
    <img src="https://github.com/CyberAgent/ChilmAI/actions/workflows/pytest_win.yml/badge.svg" alt="pytest windows">
  </a>
  <a href="https://github.com/CyberAgent/ChilmAI/tree/python-coverage-comment-action-data">
    <img src="https://github.com/CyberAgent/ChilmAI/raw/python-coverage-comment-action-data/badge.svg" alt="coverage">
  </a>
  <br>
  <a href="https://pypi.org/project/chilmai/">
    <img src="https://img.shields.io/pypi/v/chilmai" alt="PyPI">
  </a>
  <img src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue" alt="Python 3.10-3.12">
  <a href="https://cyberagent.github.io/ChilmAI/reference/license/">
    <img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="Apache-2.0">
  </a>
  <a href="https://arxiv.org/abs/2401.07761">
    <img src="https://img.shields.io/badge/arXiv-2401.07761-b31b1b" alt="arXiv 2401.07761">
  </a>
</p>

ChilmAI は、自治体の保育所利用調整における入所選考処理を支援する Python アプリケーションです。入力データのバリデーション、列名マッピング、きょうだい条件を含むマッチング、結果データの整形を行います。

利用方法や仕様の詳細は [ChilmAI ドキュメント](https://cyberagent.github.io/ChilmAI/) を参照してください。

## 主な構成

| 領域 | パス | 内容 |
|---|---|---|
| コアライブラリ | `chilmai/generic` | ファイル読込、列名マッピング、バリデーション、マッチング実行、結果整形 |
| ソルバー | `chilmai/algorithm/cp_use_transfer` | OR-Tools CP-SAT を用いたマッチング実装 |
| リファレンス実装 | `apps` | FastAPI による HTTP API と Web UI |
| サンプルデータ | `sample` | 動作確認用の合成データ |
| テストコード | `test` | 単体テスト、API テスト、ブラウザテスト |

> [!WARNING]
> `apps/` 以下の Web UI と HTTP API はリファレンス実装です。本番運用に必要な認証、認可、監査ログ、運用監視、データ保護、インフラ設定、脆弱性対応は、利用環境に合わせて別途設計・実装してください。

## 使い方

### Windows で Web UI を試す

Windows 11（64-bit）では、最新リリースの [ChilmAI-latest.zip](https://github.com/CyberAgent/ChilmAI/releases/latest/download/ChilmAI-latest.zip) をダウンロードして展開し、`ChilmAI.exe` を実行すると Web UI を利用できます。インストールや起動時の注意点は[自治体の方へのクイックスタート](https://cyberagent.github.io/ChilmAI/reference/web-ui/quickstart/)を参照してください。

### ライブラリとして利用する

Python 3.10 〜 3.12 の環境に、[PyPI](https://pypi.org/project/chilmai/) からインストールします。パッケージに含まれるのはコアライブラリ（`chilmai`）のみで、Web UI・HTTP API のリファレンス実装（`apps/`）とサンプルデータは含まれません。

```bash
pip install chilmai
```

[uv](https://docs.astral.sh/uv/) でプロジェクトに追加する場合は次のとおりです。

```bash
uv add chilmai
```

### ソースコードから利用する

Git、Python 3.10 〜 3.12、[uv](https://docs.astral.sh/uv/) を用意して、依存関係をインストールします。Web UI を利用する場合は、Microsoft Edge や Google Chrome などのモダンブラウザも必要です。

```bash
git clone https://github.com/CyberAgent/ChilmAI.git
cd ChilmAI
uv sync
```

Python API のサンプルは [インストールと実行](https://cyberagent.github.io/ChilmAI/getting-started/quickstart/)、Web UI と HTTP API の起動方法は [リファレンスアプリ](https://cyberagent.github.io/ChilmAI/api/reference-app/) を参照してください。

## ドキュメント

- [インストールと実行](https://cyberagent.github.io/ChilmAI/getting-started/quickstart/)
- [入力データと設定](https://cyberagent.github.io/ChilmAI/getting-started/data-format/)
- [Web UI 利用ガイド](https://cyberagent.github.io/ChilmAI/reference/web-ui/)
- [Python API](https://cyberagent.github.io/ChilmAI/api/python/)
- [アーキテクチャ](https://cyberagent.github.io/ChilmAI/development/architecture/)
- [セキュリティ](https://cyberagent.github.io/ChilmAI/reference/security/)

## コントリビューション

バグ報告、機能提案、ドキュメント改善、Pull Request を歓迎します。参加方法は [コントリビューション](https://cyberagent.github.io/ChilmAI/development/contributing/) を参照してください。コミュニティでのやり取りには [行動規範](CODE_OF_CONDUCT.md)（[日本語訳](https://cyberagent.github.io/ChilmAI/development/code-of-conduct/)）が適用されます。セキュリティ上の懸念は公開 Issue に投稿せず、[セキュリティ](https://cyberagent.github.io/ChilmAI/reference/security/) に記載された方法で報告してください。

## ライセンス

[Apache License 2.0](https://cyberagent.github.io/ChilmAI/reference/license/)
