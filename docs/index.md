# ChilmAI

<p align="center">
  <img src="assets/logo_yoko_black.svg" alt="ChilmAI" width="360">
</p>

<p align="center">
  <a href="https://github.com/CyberAgent/ChilmAI/actions/workflows/pytest.yml">
    <img src="https://github.com/CyberAgent/ChilmAI/actions/workflows/pytest.yml/badge.svg?branch=main" alt="pytest">
  </a>
  <a href="https://github.com/CyberAgent/ChilmAI/actions/workflows/pytest_win.yml">
    <img src="https://github.com/CyberAgent/ChilmAI/actions/workflows/pytest_win.yml/badge.svg?branch=main" alt="pytest windows">
  </a>
  <a href="https://github.com/CyberAgent/ChilmAI/tree/python-coverage-comment-action-data">
    <img src="https://github.com/CyberAgent/ChilmAI/raw/python-coverage-comment-action-data/badge.svg" alt="coverage">
  </a>
  <img src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue" alt="Python 3.10-3.12">
  <a href="https://github.com/CyberAgent/ChilmAI/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="Apache-2.0">
  </a>
  <a href="https://arxiv.org/abs/2401.07761">
    <img src="https://img.shields.io/badge/arXiv-2401.07761-b31b1b" alt="arXiv 2401.07761">
  </a>
</p>

ChilmAI は、自治体の保育所利用調整における入所選考処理を支援する Python アプリケーションです。入力データのバリデーション、列名マッピング、きょうだい条件を含むマッチング、結果データの整形を行います。

このサイトでは、ChilmAI を理解・評価・拡張するための情報をまとめています。自治体ごとに異なる業務ルールや帳票の違いに対応できるよう、コアロジックとリファレンス実装を分けて説明しています。

<div class="grid" markdown>

<div class="tile" markdown>
### ダウンロードして試す（プログラミング不要）

[自治体の方へ](reference/web-ui/index.md) では、配布されている ZIP をダウンロードし、プログラミングの知識がなくても Web UI（ブラウザで操作する画面）から入所選考を試す方法を説明しています。
</div>

<div class="tile" markdown>
### Python から利用する

[インストールと実行](getting-started/quickstart.md) では、PyPI またはソースコードから ChilmAI をセットアップし、サンプル CSV でマッチングを実行します。
</div>

<div class="tile" markdown>
### 組み込む

[Python API](api/python.md) では、`MatchingService` を使ったアプリケーションへの組み込み方法を説明します。
</div>

<div class="tile" markdown>
### 拡張する

[カスタマイズ](development/customization.md) では、自治体ごとの差分を前処理クラスで扱う方法を説明します。
</div>
</div>

## リポジトリ内容

[ChilmAI リポジトリ](https://github.com/CyberAgent/ChilmAI)のコアとなるコードベースは `chilmai/` 以下の Python ライブラリです。`apps/` 以下には、HTTP API と Web UI のリファレンス実装があります。

| 領域 | パス | 内容 |
|---|---|---|
| コアライブラリ | `chilmai/generic` | ファイル読込、列名マッピング、バリデーション、マッチング実行、結果整形 |
| ソルバー | `chilmai/algorithm/cp_use_transfer` | OR-Tools CP-SAT を用いたマッチング実装 |
| リファレンス実装 | `apps` | FastAPI による HTTP API と Web UI |
| サンプルデータ | `sample` | 動作確認用の合成データ |
| テストコード | `test` | 単体テスト、API テスト、ブラウザテスト |

## 利用者・コントリビューター

ChilmAI は次のような方を想定しています。

- 自治体で保育所利用調整を担当し、画面操作で ChilmAI を試す方
- ChilmAI を試用・評価する自治体、事業者、研究者
- 自治体ごとのデータ形式や選考ルールに合わせて拡張する開発者
- Issue、Pull Request、ドキュメント改善などでプロジェクトに参加するコントリビューター
