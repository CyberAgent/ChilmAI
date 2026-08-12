"""ChilmAI が利用する OR-Tools ベースの保育所利用調整ソルバー。

この package は低レイヤーの CP-SAT 実装を含む。
通常の呼び出し元は、これらの module を直接 import せず、
`chilmai.generic.service.MatchingService` を利用する。
"""
