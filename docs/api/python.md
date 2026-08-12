# Python API

Python から利用する場合は、`chilmai.generic.service.MatchingService` を入口にします。このクラスは、ファイル読込、列名マッピング、バリデーション、マッチング、結果整形をまとめて実行します。

パッケージの導入と、リポジトリ同梱のサンプルデータで動かす手順は [インストールと実行](../getting-started/quickstart.md) を参照してください。

## 最小例

申込者データと保育所データのファイル内容をバイト列で渡し、マッチングを実行します。入力ファイルの形式は [入力データと設定](../getting-started/data-format.md) を参照してください。

```python
from pathlib import Path

from chilmai.generic.config import DEFAULT_CONFIG
from chilmai.generic.service import MatchingService

service = MatchingService()
result = service.match(
    children_file_bytes=Path("申込者データ.csv").read_bytes(),
    children_file_format="csv",
    daycares_file_bytes=Path("保育所データ.csv").read_bytes(),
    daycares_file_format="csv",
    mapping=DEFAULT_CONFIG,
    solver_config={"max_time_seconds": 10},
)
```

きょうだい児童の入所パターンを細かく指定する組み合わせファイル（任意、[入力データと設定](../getting-started/data-format.md)を参照）を使う場合は、`combination_file_bytes` と `combination_file_format` も指定します。

## 戻り値

`match()` は、マッチング結果、施設名辞書、成立件数の集計、Excel 出力用の列・行データを含む辞書を返します。HTTP API や Web UI も、このコア処理を利用しています。

## バリデーションだけを実行する

入力データに問題がないかを事前に確認する場合は、`validate()` を呼び出します。引数は `match()` から `solver_config` を除いたものと同じです。

```python
validation = service.validate(
    children_file_bytes=Path("申込者データ.csv").read_bytes(),
    children_file_format="csv",
    daycares_file_bytes=Path("保育所データ.csv").read_bytes(),
    daycares_file_format="csv",
    mapping=DEFAULT_CONFIG,
)
```

戻り値の `is_valid` が `False` の場合、`errors` にバリデーションエラーが入ります。あわせて `warnings`（警告一覧）と `summary`（読み込んだ申込者・保育所の件数）も返されます。

## 主要モジュール

| モジュール | 役割 |
|---|---|
| `chilmai.generic.parser` | CSV、Excel の読込と内部列名への変換 |
| `chilmai.generic.validator` | 必須列、ID、年齢、希望施設、募集人数などのバリデーション |
| `chilmai.generic.config` | 列名マッピングとプロファイル管理 |
| `chilmai.generic.column_mapper` | 入力列名からのマッピング候補のサジェスト |
| `chilmai.generic.service` | 高レベル API |
| `chilmai.generic.matcher` | CP-SAT マッチングの実行 |
| `chilmai.generic.preprocessor` | 自治体ごとの前処理拡張 |

## API リファレンス

::: chilmai.generic.service.MatchingService

::: chilmai.generic.preprocessor.BasePreprocessor
