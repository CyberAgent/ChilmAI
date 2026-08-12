# テスト

ChilmAI のテストは `test/` 以下にあり、pytest の**マーカー**によって実行対象を切り替えます。`browser`・`binary` マーカーのいずれも付いていないテスト（以下「non-browser テスト」）が通常のテストスイートで、CI でも中心的に実行されます。

## テストの構成

| ディレクトリ | マーカー | 内容 |
|---|---|---|
| `test/chilmai/generic` | なし | コアライブラリ・アルゴリズムのテスト（ファイル読込、列名マッピング、バリデーション、きょうだい制約、ソルバー、結果整形など） |
| `test/apps` | なし | リファレンス実装（`apps/api`）の API コントラクトテスト。FastAPI の `TestClient` を用い、ブラウザは起動しません |
| `test/docs` | なし | ドキュメントサイト（mkdocs）の設定・メタ情報のテスト |
| `test/validation` | なし | pandas など依存ライブラリの前提を確認するテスト |
| `test/chilmai/browser` | `browser` | リファレンス実装の Web UI に対する Playwright E2E テスト |
| `test/chilmai/binary` | `binary` | Windows 向けにビルドした配布バイナリのテスト |

!!! note "API コントラクトテストとブラウザ E2E の違い"
    API コントラクトテスト（`test/apps`）は Web UI を対象にしますが、HTTP レベルでの検証でブラウザ操作を伴いません。ブラウザ操作を伴う Web UI の E2E は `browser` マーカー側（`test/chilmai/browser`）にまとまっています。

## non-browser テスト

`browser` と `binary` を除いた全テストを実行します。コアライブラリ・アルゴリズムに加え、API コントラクト・docs・validation のテストも含まれます。

```bash
uv run python -m pytest test/ -m 'not (browser or binary)' -n auto
```

## ブラウザ E2E テスト

リファレンス実装の Web UI を実際に起動し、Playwright で操作して検証します。

```bash
uv run python -m pytest test/chilmai/browser -m browser -n 1
```

初回実行時に Chromium がない場合は、Playwright のセットアップが必要です。

```bash
uv run playwright install chromium
```

## バイナリテスト

`binary` マーカーの付いたテストは、Windows 向けにビルドした配布バイナリを対象とします。通常の開発では実行対象外です。
