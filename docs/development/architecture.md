# アーキテクチャ

ChilmAI のコアライブラリの構成は次のとおりです。

```text
chilmai/generic
  parser, validator, config, column_mapper, preprocessor,
  service, matcher などの主要モジュール

chilmai/algorithm/cp_use_transfer
  OR-Tools CP-SAT solver implementation
```

## 処理の流れ

1. `InputParser` が CSV または Excel を読み込み、列名マッピングを適用する
2. `BasePreprocessor` が自治体ごとのバリデーションと変換を行う
3. `ValidationService` が ChilmAI 共通の入力バリデーションを行う
4. `CpSatMatcher` が OR-Tools CP-SAT ソルバーでマッチングする
5. `MatchingService` が API と出力ファイル向けに結果を整形する

## レイヤーの役割

| レイヤー | 役割 |
|---|---|
| コアライブラリ | 入力バリデーション、マッチング、結果整形 |
| 前処理 | 自治体ごとの列、点数、きょうだい条件の差分吸収 |

## 背景となる研究 {#research-background}

`chilmai/algorithm/cp_use_transfer` のマッチングアルゴリズムは、AAAI-24 採択論文 [Stable Matchings in Practice: A Constraint Programming Approach](https://arxiv.org/abs/2401.07761)（Sun et al.）の理論を実装しています。きょうだい同時申し込みや転園を含む保育所利用調整を、制約プログラミングによる安定マッチングとして定式化しています。

日本語での解説は、ブログ記事 [【採択論文紹介】制約プログラミングによる新しい保育所マッチング（AAAI2024）](https://cyberagent.ai/blog/research/economics/19145/) を参照してください。
