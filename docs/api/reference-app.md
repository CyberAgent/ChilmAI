# リファレンスアプリ

`apps.api.main:app` は、FastAPI による Web UI とサーバ API を提供するリファレンス実装です。どちらも Python API と共通の `MatchingService` を利用し、ファイル読込、列名マッピング、バリデーション、マッチング、結果整形を実行します。

!!! warning "リファレンス実装の位置づけ"
    本番運用に必要な認証、認可、監査ログ、運用監視、データ保護、インフラ設定、脆弱性対応は含まれていません。業務システムに組み込む場合は、利用環境に合わせて別途設計・実装してください（[セキュリティ](../reference/security.md)）。

## 起動

リファレンス実装（`apps/`）は PyPI のパッケージには含まれないため、リポジトリを取得して利用します（[インストールと実行](../getting-started/quickstart.md)）。依存関係をインストールしたリポジトリのルートで、次のコマンドを実行します。

```bash
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8501
```

## Web UI

Web UI では、申込者データと保育所データの確認から入所選考、結果のダウンロードまでをブラウザで操作できます。入力ファイルには CSV または Excel を利用できます。

| URL | 内容 |
|---|---|
| `http://127.0.0.1:8501/` | 入力ファイルのアップロード、データ確認、入所選考、結果のダウンロード |
| `http://127.0.0.1:8501/settings` | 入力列名、出力列名、きょうだい条件などの項目名設定とプロファイル管理 |

画面を使った準備や操作の詳しい手順は [自治体の方へ](../reference/web-ui/index.md) にまとめています。

## サーバ API {#server-api}

外部システムとの連携やプログラムからのバリデーションには、JSON レスポンスを返す HTTP API を利用できます。API 仕様は、アプリの起動後に FastAPI の自動生成ドキュメントで確認できます。

| URL | 内容 |
|---|---|
| `http://127.0.0.1:8501/docs` | Swagger UI |
| `http://127.0.0.1:8501/openapi.json` | OpenAPI JSON |

### 主なエンドポイント

| メソッド | パス | リクエスト形式 | 内容 |
|---|---|---|---|
| `GET` | `/config` | リクエストボディなし | 現在の列名マッピングを取得 |
| `POST` | `/config` | `application/json` | 列名マッピングを保存 |
| `POST` | `/validate` | `multipart/form-data` | 入力ファイルのバリデーションを実行 |
| `POST` | `/match` | `multipart/form-data` | 入力ファイルをバリデーションしてマッチングを実行 |

`/validate` と `/match` には、`children_file` と `daycares_file` をファイルとして指定します。任意のきょうだい組み合わせを使う場合は `combination_file` も指定できます。`/match` の `solver_config` は、`{"max_time_seconds": 10}` のような JSON 文字列を multipart form のフィールドとして渡します。

`/htmx/*` は Web UI の画面更新に使う HTML コンポーネントを返す内部エンドポイントです。プログラムから連携する場合は、OpenAPI に掲載される HTTP API を利用してください。
