# コントリビューションガイド

ChilmAI へのコントリビューションに興味を持っていただき、ありがとうございます。

## 始める前に

### 対象範囲

ChilmAI の主な開発対象は以下です。

- マッチングアルゴリズム: `chilmai/algorithm/`
- 入力データバリデーション・列名マッピングなどのコアロジック: `chilmai/generic/`
- Web UI / サーバ API: `apps/api/`
- テスト: `test/`
- ドキュメント: `docs/`

### セキュリティ報告との切り分け

脆弱性の可能性がある内容は、公開 Issue や Pull Request には投稿しないでください。セキュリティ上の懸念は [SECURITY.md](SECURITY.md) の方針に従って報告してください。

### 個人情報・機密データの取り扱い

Issue、Pull Request、コメント、コードには以下を含めないでください。

- 実在する個人情報
- 自治体データ、本番入力ファイル、マッチング結果、設定ファイル
- 秘密情報、認証情報、その他の機密情報

再現例が必要な場合は、実在する個人や組織を特定できない合成データを使ってください。

## Issue を作成する

[Issues](https://github.com/CyberAgent/ChilmAI/issues) から Issue を作成してください。用途に応じたテンプレートを選んでください。

- **Bug report**: 不具合の報告
- **Documentation improvement**: ドキュメントの改善提案
- **Feature request**: 新機能の提案

既存の Issue を検索して重複がないか確認してから作成してください。

## 開発環境のセットアップ

### 必要環境

- Python 3.10 〜 3.12
- [uv](https://docs.astral.sh/uv/)

### セットアップ手順

```bash
git clone https://github.com/CyberAgent/ChilmAI.git
cd ChilmAI
uv sync --extra test --extra docs --extra format
```

続けて、コミット時に自動でフォーマット・lint を実行する pre-commit フックを有効化してください。`pre-commit` は `uvx` で実行できるため、依存関係としてインストールする必要はありません。

```bash
uvx pre-commit install
```

これ以降、`git commit` のたびに `ruff` によるフォーマット・lint が変更ファイルへ自動で適用されます（ruff のバージョンは `.pre-commit-config.yaml` で固定しています）。フックはローカルの補助であり、`--no-verify` で回避できます。マージ可否の最終判定は CI(`.github/workflows/lint.yml`) が行います。

## テストの実行

コードを変更した場合は、Pull Request を送る前に以下の 2 種類のテストが両方パスすることを確認してください。

### non-browser テスト

コアライブラリ・アルゴリズムに加え、リファレンス実装の API コントラクトテストや docs・validation のテストも含みます。

```bash
uv run python -m pytest test/ -m 'not (browser or binary)' -n auto
```

### browser テスト

browser テストを初めて実行する場合は、事前に Playwright の Chromium をインストールしてください。

    uv run playwright install chromium

その後、以下を実行します。

    uv run python -m pytest test/chilmai/browser -m browser -n 1

ドキュメントのみを変更した場合は、上記の自動テストを省略できます。代わりに、リンク切れや設定ミスを確認するため、ドキュメントを strict モードでビルドしてください。

```bash
uv run --extra docs mkdocs build --strict -f mkdocs.yml
```

テストの詳細は [テスト](docs/development/testing.md) を参照してください。

## Pull Request を送る

1. このリポジトリをフォークし、変更用のブランチを作成してください。
2. 変更内容に対応するテストを追加・更新してください。
3. コード変更では上記 2 種類のテスト、ドキュメントのみの変更では strict ビルドがパスすることを確認してください。
4. Pull Request を作成し、テンプレートのチェックリストに記入してください。

Pull Request は関連する Issue と紐づけてください。Issue がない場合は先に Issue を作成することを推奨します。

## コードスタイル

フォーマット・lint は `ruff` を使います。設定は `pyproject.toml` の `[tool.ruff]` に集約されています。

pre-commit フックを有効化していれば、コミット時に自動で適用されます。手動で全ファイルに適用する場合は、フックと同じ内容を次のコマンドで実行できます。

```bash
uvx pre-commit run --all-files
```

CI でも下記コマンドと同じチェックが実行され、その結果がマージ可否の判定に使われます。

```bash
uv run ruff check .
uv run ruff format --check .
```

なお、ruff のバージョンは pre-commit(`.pre-commit-config.yaml`)と CI(`pyproject.toml` の `format` extra)で揃えています。

docstring は原則として日本語で記述します。

## ドキュメント執筆方針

`docs/` のドキュメントは「知識の呪い」に陥りやすい領域です。書き手が当然と思っている前提を、読者は持っていません。以下の方針に従って、想定読者が前提知識ゼロでも読み進められるように書いてください。

### 想定読者

本ドキュメントサイトには2種類の読者が混在します。全ページ共通のペルソナではなく、セクションごとに読者を意識してください。

- **`docs/reference/web-ui/`(自治体の方へ)**: 初めて ChilmAI に触れる自治体の保育所利用調整担当者。プログラミング知識はなく、GitHub・ZIP 展開・CSV の扱いに不慣れな場合がある。専門用語・業務用語・操作の前提を省略しない。
- **`docs/getting-started/`・`docs/api/`・`docs/development/` など**: 開発者向け。ただし非技術者が検索や外部リンクから直接着地する可能性があるため、入口となるページには Web UI ガイドへの誘導リンクを置く(各ページへの反映は別イシューで進める)。

### 執筆ルール

1. **操作の「前」に目的と結果を書く。** 操作を指示するときは、その操作の前に「何が起こるか」「何のためにやるのか」を書く。
2. **用語は UI の表示文言と完全一致させる。** 同一概念に複数の語を使わない(例:「選択」と「アップロード」を混在させない)。
3. **専門用語・業務用語は初出時に言い換えを併記する。** または用語集にリンクする(例:「点数(自治体によっては『利用調整指数』とも呼ばれます)」)。
4. **環境依存で出たり出なかったりする画面は条件付きで書く。** 「表示された場合は」のように書く。
5. **記述順を実際の操作順に一致させる。** ドキュメントを上から読めばそのまま操作できる順序にする。
6. **重要な情報を折りたたみ(collapsible)に隠さない。** 読み飛ばされて困る情報は本文に出す。
7. **読者に推論させない。** データや画面から読み取れる結論を明示的に書く。
8. **誤った一般化を避ける。** 具体的な因果関係のみを書く。

### プロセス

- ドキュメントの大きな更新時は「初見ユーザーによる通しテスト」を行い、詰まった箇所をイシュー化する。
- LLM でドキュメントを生成・修正する際は、上記の想定読者を明示的にプロンプトへ含める。
