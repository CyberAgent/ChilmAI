# ライセンス

ChilmAI は Apache License 2.0 で公開されています。詳細はリポジトリの [LICENSE](https://github.com/CyberAgent/ChilmAI/blob/main/LICENSE) を参照してください。

## 商標

名称やロゴの扱いは、リポジトリの [TRADEMARK.md](https://github.com/CyberAgent/ChilmAI/blob/main/TRADEMARK.md) を参照してください。

## 依存ライブラリ

ChilmAI が利用する Pandas、OR-Tools、FastAPI などの依存ライブラリは、それぞれのライセンスに従います。配布や組み込みの際は、依存ライブラリのライセンスも確認してください。

## Windows 配布物に含まれるライセンス

ソースコードから利用する場合、依存関係は利用者自身がインストールします。一方 [GitHub Releases](https://github.com/CyberAgent/ChilmAI/releases) の `ChilmAI-vX.Y.Z.zip` は依存パッケージとネイティブコードそのものを再配布するため、`ChilmAI.exe` と並べて以下を同梱しています。

| 同梱物 | 内容 |
| --- | --- |
| `LICENSE` / `NOTICE` / `TRADEMARK.md` | ChilmAI 自身のもの |
| `THIRD-PARTY-NOTICES.txt` | 同梱物の一覧（名前・版・ライセンス・ソースの入手先・条文の場所） |
| `licenses/` | 上流のライセンス / NOTICE ファイルの原文コピー |

一覧には、Python パッケージだけでなく、パッケージ（wheel）の内部に含まれるコンポーネントも記載しています。例えば、OR-Tools に静的リンクされている Coin-OR（EPL-2.0）と Eigen（MPL-2.0）、Rust 製拡張モジュールが利用するライブラリ（クレート）、PyInstaller のブートローダなどです。`ChilmAI.exe` に同梱される CPython のランタイム一式（インタプリタ本体と標準ライブラリ、およびそれらがリンクする OpenSSL・SQLite・libffi・MSVC ランタイム）も同じ一覧に記載しています。これらのバージョンはビルド環境によって変わるため、実際に同梱されたものから読み取った値を記載しています。クレートの一覧は取得元により精度が異なります。`pydantic-core` については、実際にリンクされるものより範囲の広い一覧を記載し、その旨を一覧にも併記しています。各コンポーネントの取得元も一覧に記載し、ビルド時にパッチを適用したものについてはパッチの URL も記載しています。

同梱内容の詳細は配布物内の `THIRD-PARTY-NOTICES.txt` を、生成と検査の仕組みは [`apps/licenses/README.md`](https://github.com/CyberAgent/ChilmAI/blob/main/apps/licenses/README.md) を参照してください。
