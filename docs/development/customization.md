# カスタマイズ

自治体ごとのデータ形式や選考ルールの差分は、`BasePreprocessor` を継承して実装します。

## 前処理フック

| メソッド | 用途 |
|---|---|
| `validate()` | 自治体固有の入力チェック |
| `transform_children()` | 点数、希望施設別スコア、きょうだいパターンの生成 |
| `transform_daycares()` | 保育所データの変換 |
| `transform_output()` | 結果 DataFrame の加工 |

## 実装例

```python
import pandas as pd

from chilmai.generic.preprocessor import BasePreprocessor


class MyPreprocessor(BasePreprocessor):
    def transform_children(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["score_1"] = self.rank_by(out, [("指数合計", "desc"), ("優先順位", "asc")])
        out["sibling_pattern"] = out["きょうだい条件"].fillna("").astype(str)
        return out
```

`MatchingService` に渡すと、バリデーションとマッチングの前に実行されます。

```python
from chilmai.generic.service import MatchingService

service = MatchingService(preprocessor=MyPreprocessor())
```

より具体的な例は `examples/sample_preprocessor.py` を参照してください。

## 入力ファイルの読み込み

列名が 1 行目にない、対象のシートが先頭にないといった入力ファイルは、`InputParser` を継承して読み込み方を変えます。対象のシートと列名の行は、クラス属性で指定できます。

```python
from chilmai.generic.parser import InputParser


class MyParser(InputParser):
    SHEET_NAME = "申込一覧"  # シート名、または先頭を 0 とするシートの位置
    HEADER_ROW = 3  # 列名が書かれた行（先頭行を 1 とする）。CSV にも適用される
```

ファイルごとに読み方を変える場合や、独自の形式を読む場合は `read_table()` をオーバーライドします。`kind` には読み込むファイルの種類（`"children"`・`"daycares"`・`"combination"`）が入ります。

```python
import pandas as pd


class MyParser(InputParser):
    @classmethod
    def read_table(cls, source, file_format, *, kind=None, nrows=None) -> pd.DataFrame:
        if kind == "children" and file_format == "excel":
            return pd.read_excel(source, sheet_name="申込一覧", header=2, dtype=str, nrows=nrows, engine="calamine")
        return super().read_table(source, file_format, kind=kind, nrows=nrows)
```

`MatchingService` に渡すと、すべての入力ファイルの読み込みに使われます。

```python
service = MatchingService(preprocessor=MyPreprocessor(), parser=MyParser())
```

## Web UI のカスタマイズ {#web-ui}

リファレンスアプリ（Web UI とサーバ API）では、`apps/` を改変せずに次の 4 か所を差し替えられます。

| 差し替え先 | 方法 |
|---|---|
| 前処理フック | `create_preprocessor()` で `BasePreprocessor` のサブクラスを返す |
| 入力ファイルの読み込み | `create_parser()` で `InputParser` のサブクラスを返す |
| 結果 Excel | `build_result_workbook()` で openpyxl の `Workbook` を返す。`result_filename()` でダウンロード時のファイル名も変えられる |
| 画面の入力項目 | `fields` に `ParamField` を並べる |

`apps.api.customization.WebCustomization` を継承したクラスを `apps/` の外に実装します。必要なメソッドだけをオーバーライドしてください。

```python
from apps.api.customization import ParamField, WebCustomization, build_default_workbook


class MyTownCustomization(WebCustomization):
    fields = (
        ParamField(name="fiscal_year", label="年度", type="number", default="2027", required=True),
        ParamField(name="month", label="入所月", type="select", choices=("4", "5", "6"), default="4"),
    )

    def create_preprocessor(self, params):
        return MyPreprocessor()

    def create_parser(self):
        return MyParser()

    def build_result_workbook(self, result, meta, params):
        wb = build_default_workbook(result, meta, params)  # 標準の result・meta シート
        ws = wb.create_sheet("施設別")
        ws.append([f"{params['fiscal_year']}年度 {params['month']}月入所"])
        ...
        return wb

    def result_filename(self, params):
        return f"選考結果_{params['fiscal_year']}年度{params['month']}月.xlsx"
```

作成したクラスを環境変数 `CHILMAI_WEB_CUSTOMIZATION` に `module:ClassName` の形式で指定して起動します。モジュールは、起動したディレクトリから import できる場所に置くか、パッケージとしてインストールしてください。

```bash
CHILMAI_WEB_CUSTOMIZATION=mytown.web:MyTownCustomization \
  uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8501
```

4 か所すべてを差し替える例は `examples/sample_web_customization.py` にあります。リポジトリのルートで次のように起動すると動作を確認できます。

```bash
CHILMAI_WEB_CUSTOMIZATION=examples.sample_web_customization:SampleWebCustomization \
  uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8501
```

### 追加の入力項目

`fields` に定義した項目は、アップロード画面のファイル選択欄の下に表示されます。入力値は `params`（`{name: 値}` の dict）として `create_preprocessor()`・`build_result_workbook()`・`result_filename()` に渡されます。前処理フックはリクエストごとに作られるため、入力値に応じて処理を切り替えられます。

| 属性 | 内容 |
|---|---|
| `name` | 項目名。英数字と `_` のみ使えます。`params` のキーになります |
| `label` | 画面に表示する項目名 |
| `type` | `"text"`・`"number"`・`"select"`・`"checkbox"` のいずれか |
| `choices` | `select` の選択肢 |
| `default` | 画面の初期値。サーバ API で項目を省略した場合もこの値を使います。`checkbox` では `"true"` か `"false"` |
| `required` | 入力必須かどうか |
| `help_text` | 入力欄の下に表示する説明 |

値はすべて文字列で渡されます。`checkbox` はチェックありで `"true"`、なしで `"false"` です。空欄で送られた値は未入力として扱い、既定値には置き換えません。必須項目が未入力の場合や、選択肢にない値・半角の数値でない値が入力された場合は、エラー（E108）になります。入力値は、標準の結果 Excel の `meta` シートに `param.<name>` として記録されます。

サーバ API の `/validate`・`/match` では、入力値を `params` フィールドに JSON 文字列で渡します（[サーバ API](../api/reference-app.md#server-api)）。

### 配布 ZIP に組み込む {#web-ui-package}

自治体に配布 ZIP（Windows 向けの実行ファイル `ChilmAI.exe`）を渡す場合は、`CHILMAI_WEB_CUSTOMIZATION` を設定して `apps/packager.py` でビルドします。

```powershell
$env:CHILMAI_WEB_CUSTOMIZATION = "mytown.web:MyTownCustomization"
uv run python apps/packager.py
```

指定したモジュールと、そのモジュールが import するライブラリが exe に組み込まれます。どのカスタマイズを使うかも exe に記録されるため、自治体の担当者は環境変数を設定せずに、`ChilmAI.exe` を起動するだけで使えます。

- モジュールは、リポジトリ直下に置くか、ビルドする環境にインストールしてください。指定に誤りがある場合は、exe を作る前にエラーで止まります。
- ビルドは Windows で、`uv sync --extra package` を実行した環境で行ってください（手順は `.github/workflows/pyinstaller_build.yml` と同じです）。
- 組み込まれるのは Python のモジュールだけです。カスタマイズが Excel のひな形などのファイルを読む場合は、コードの中にデータとして持たせるか、PyInstaller の設定を追加してください。
- 同梱物の一覧（`THIRD-PARTY-NOTICES.txt`）とライセンスの検査の対象は ChilmAI 本体の依存ライブラリだけです。カスタマイズのために追加したライブラリのライセンス表示は、配布する事業者が用意してください。

### 注意事項

- 結果 Excel の数式セル（`=` で始まる文字列を含む）は、入力値が数式として実行されないよう、すべて文字列として保存されます。そのため、数式は出力できません。数値などそれ以外のセルはそのまま保存されます。
- カスタマイズのメソッドが例外を出した場合は、画面・API ではエラー（E109）として返し、詳細はサーバのログに出力します。
- 指定したクラスを読み込めない場合、アプリは起動時にエラーで終了します。標準の動作に切り替わることはありません。
- 指定したモジュールはアプリと同じ権限で実行されます。信頼できるコードだけを指定してください。
- 実行中のアプリで環境変数を設定した場合は、配布 ZIP に記録した指定より環境変数を優先します。
