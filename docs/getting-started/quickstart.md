# インストールと実行

ChilmAI を開発者として使い始める手順です。ライブラリとして自分のアプリケーションに組み込む場合は PyPI から、サンプルデータでの試用・Web UI や HTTP API の起動・開発への参加はソースコードから始めます。

!!! tip "プログラミング不要で使いたい方へ"
    ブラウザの画面操作だけで入所選考を試したい場合、**Windows 11（64-bit）の PC** であれば配布されている ZIP をダウンロードするだけで使えます（Python のインストールも不要です）。詳しくは [自治体の方へ](../reference/web-ui/index.md) をご覧ください。

## インストール

=== "PyPI から（ライブラリとして使う）"

    Python 3.10 〜 3.12 を用意して、インストールします。

    <!-- TODO(PyPI 公開後に確定): 公開を確認のうえ、プロジェクトページ（例: https://pypi.org/project/chilmai/）へのリンクをここに追加する -->

    ```bash
    pip install chilmai
    ```

    [uv](https://docs.astral.sh/uv/) でプロジェクトに追加する場合は次のとおりです。

    ```bash
    uv add chilmai
    ```

    PyPI のパッケージに含まれるのはコアライブラリ（`chilmai`）のみです。Web UI と HTTP API のリファレンス実装（`apps/`）、およびサンプルデータは含まれないため、これらを使う場合はソースコードから始めてください。

=== "ソースコードから（Web UI・開発）"

    Git、Python 3.10 〜 3.12、[uv](https://docs.astral.sh/uv/) を用意してください。Web UI を利用する場合は、Microsoft Edge や Google Chrome などのモダンブラウザも必要です。

    ```bash
    git clone https://github.com/CyberAgent/ChilmAI.git
    cd ChilmAI
    uv sync
    ```

    開発に参加する場合のセットアップ（テスト・ドキュメント用の依存関係や pre-commit フック）は [コントリビューション](../development/contributing.md) を参照してください。

## サンプルデータで実行する

動作確認用の合成データとして、次の 2 ファイルを用意しています。

| ファイル | 内容 |
|---|---|
| [`申込者データ_デモ.csv`](https://github.com/CyberAgent/ChilmAI/blob/main/sample/申込者データ_デモ.csv) | 申請児童 5 名（うち、きょうだい 1 組・転園希望 1 名） |
| [`保育所データ_デモ.csv`](https://github.com/CyberAgent/ChilmAI/blob/main/sample/保育所データ_デモ.csv) | 保育所 3 園（3 歳枠のみ・合計 5 枠） |

### サンプルデータを用意する {#prepare-sample-data}

=== "ソースコードから始めた場合"

    2 ファイルはリポジトリの `sample/` に含まれています。追加の準備は不要です。以下ではリポジトリ直下を作業ディレクトリとして進めます。

=== "PyPI から始めた場合"

    サンプルデータは PyPI のパッケージに含まれません。上の表のリンク先（GitHub）でファイルを開き、「Download raw file」から 2 ファイルをダウンロードしてください。

    以下では、作業ディレクトリに `sample/` を作成して 2 ファイルを保存した状態を前提とします。別の場所に保存した場合は、次のコードのパスをその保存先に合わせて書き換えてください。

### マッチングを実行する {#run-matching}

Python API からマッチングを実行します。

```python
from pathlib import Path

from chilmai.generic.config import DEFAULT_CONFIG
from chilmai.generic.service import MatchingService

# CSV の保存先に合わせて書き換えてください
children_file = Path("sample/申込者データ_デモ.csv")
daycares_file = Path("sample/保育所データ_デモ.csv")

service = MatchingService()

result = service.match(
    children_file_bytes=children_file.read_bytes(),
    children_file_format="csv",
    daycares_file_bytes=daycares_file.read_bytes(),
    daycares_file_format="csv",
    mapping=DEFAULT_CONFIG,
    solver_config={"max_time_seconds": 10},
)

print(result["matched_children"])
```

作業ディレクトリにスクリプトとして保存し、`uv run python <ファイル名>`（PyPI からインストールした場合は、その環境で `python <ファイル名>`）で実行します。

`match()` はマッチング結果を含む辞書を返します。戻り値の構造の詳細と、入力データに問題がないか事前に確認する `validate()` については [Python API](../api/python.md) を参照してください。

## 次のステップ

- [入力データと設定](data-format.md) — 自分のデータを読み込ませるための形式と列名マッピング
- [Python API](../api/python.md) — アプリケーションへの組み込み
- [リファレンスアプリ](../api/reference-app.md) — Web UI と HTTP API の起動
- [カスタマイズ](../development/customization.md) — 自治体ごとの差分の実装
