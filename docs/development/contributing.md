# コントリビューション

ChilmAI へのバグ報告、ドキュメント改善、機能提案、Pull Request を歓迎します。

開発環境のセットアップ、テストの実行、コードスタイル、Pull Request の手順といった開発参加の具体的な手順は、リポジトリルートの [CONTRIBUTING.md](https://github.com/CyberAgent/ChilmAI/blob/main/CONTRIBUTING.md) にまとめています。Issue や Pull Request を作成する前に一読してください。

## 貢献の種類

- **バグ報告・機能提案**: [GitHub Issues](https://github.com/CyberAgent/ChilmAI/issues) から、内容に合うテンプレートを選んで作成してください。既存 Issue と重複していないか事前に確認してください。
- **コードの変更**: [CONTRIBUTING.md](https://github.com/CyberAgent/ChilmAI/blob/main/CONTRIBUTING.md) の手順で開発環境をセットアップし、[テスト](testing.md) に記載の 2 種類のテストがパスすることを確認してください。
- **ドキュメントの改善**: [CONTRIBUTING.md](https://github.com/CyberAgent/ChilmAI/blob/main/CONTRIBUTING.md) の「ドキュメント執筆方針」に従ってください。ドキュメントのみの変更では、自動テストの代わりに strict ビルドがパスすることを確認します。

## 注意事項

セキュリティ上の懸念は公開 Issue に投稿せず、[SECURITY.md](https://github.com/CyberAgent/ChilmAI/blob/main/SECURITY.md) に記載された方法で報告してください。

Issue、Pull Request、コメント、テストデータには、実在する個人情報、自治体の本番データ、認証情報、秘密情報を含めないでください。再現例には人工的な合成データを利用してください。

## 関連ページ

- [テスト](testing.md) — テストの構成と実行コマンド
- [カスタマイズ](customization.md) — 自治体ごとの差分を扱う拡張方法
- [リリースフロー](workflows.md) — リリースと配布物のビルド
