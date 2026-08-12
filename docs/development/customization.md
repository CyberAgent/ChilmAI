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
