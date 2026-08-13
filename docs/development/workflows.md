# リリースフロー

ChilmAI の Windows 向け配布物は、2 つの GitHub Actions ワークフローによって作成され、[GitHub Releases](https://github.com/CyberAgent/ChilmAI/releases) で公開されます。

<!-- TODO(PyPI 公開後に確定): PyPI への公開手順が整備されたら、このページに追記する -->

```text
リリースの準備
  → バージョンの更新とテスト
  → リリースコミットと vX.Y.Z タグの作成
  → Windows 向け配布物のビルド
  → GitHub Release の公開
```

## リリースを準備する

[`release_prepare.yml`](https://github.com/CyberAgent/ChilmAI/blob/main/.github/workflows/release_prepare.yml) は、リリースするバージョンを決定し、プロジェクトのバージョンを更新します。ドキュメントのビルドと自動テストがすべて成功すると、リリースコミットと `vX.Y.Z` 形式のタグを作成し、配布物を作成するワークフローを起動します。

## 配布物を作成して公開する

[`release_tag.yml`](https://github.com/CyberAgent/ChilmAI/blob/main/.github/workflows/release_tag.yml) は、リリースタグとプロジェクトのバージョンが一致することを確認した後、Windows 上で ChilmAI をビルドします。

Windows 版のビルドには Python 3.11 を使用します。ChilmAI の開発環境は Python 3.10 〜 3.12 をサポートしていますが、配布バイナリに同梱される Python ランタイムは 3.11 です。プルリクエストごとにビルドを検証する [`pyinstaller_build.yml`](https://github.com/CyberAgent/ChilmAI/blob/main/.github/workflows/pyinstaller_build.yml) も同じ Python 3.11 を使用します。

ビルドが成功すると、次のファイルを添付した GitHub Release が公開されます。

- `ChilmAI-latest.zip`: `ChilmAI.exe` と実行に必要なファイル一式（ZIP 内のルートフォルダは `ChilmAI-vX.Y.Z`）
- `ChilmAI-latest.zip.sha256`: ZIP ファイルの整合性を確認するための SHA-256 ハッシュ

添付ファイル名は意図的にバージョンを含めない固定名にしています。GitHub の `releases/latest/download/<ファイル名>` はファイル名の完全一致で最新リリースに解決されるため、固定名にすることで、常に最新バージョンを指す次の永続リンクをドキュメントに記載できます。バージョンは、リリースのタグ（`vX.Y.Z`）・ZIP 内のルートフォルダ名・Web UI のヘッダー表示で確認します。

- <https://github.com/CyberAgent/ChilmAI/releases/latest/download/ChilmAI-latest.zip>
- <https://github.com/CyberAgent/ChilmAI/releases/latest/download/ChilmAI-latest.zip.sha256>

リリースノートは、前回のリリース以降の変更内容をもとに自動生成されます。

## リリース版を利用する

最新バージョンの [ChilmAI-latest.zip](https://github.com/CyberAgent/ChilmAI/releases/latest/download/ChilmAI-latest.zip) をダウンロードして展開し、`ChilmAI-vX.Y.Z/ChilmAI.exe` を実行します。詳しい手順は[自治体の方へのクイックスタート](../reference/web-ui/quickstart.md)を参照してください。
