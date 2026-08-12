#!/usr/bin/env python3
"""Generate docs/reference/web-ui/images/05_flow_overview.png via Playwright SVG render.

Usage (from repo root):
    uv run python scripts/gen_flow_overview.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "docs" / "reference" / "web-ui" / "images" / "05_flow_overview.png"

SVG_WIDTH = 600
SVG_HEIGHT = 960

HTML = """\
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<style>
  body {{ margin: 0; background: #fff; font-family: "Noto Sans JP", "Hiragino Sans", "Yu Gothic", sans-serif; }}
  svg text {{ font-family: inherit; }}
</style>
</head>
<body>
<svg xmlns="http://www.w3.org/2000/svg"
     width="{W}" height="{H}" viewBox="0 0 {W} {H}">

  <defs>
    <marker id="arr" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
      <path d="M0,0 L0,6 L8,3 z" fill="#6b7280"/>
    </marker>
  </defs>

  <!-- ===== 申込データ入力ファイル (top left) ===== -->
  <ellipse cx="160" cy="40" rx="100" ry="22" fill="#fef08a" stroke="#ca8a04" stroke-width="1.5"/>
  <text x="160" y="45" text-anchor="middle" font-size="12" fill="#713f12">申込データ.xlsx</text>

  <!-- connector from input to section -->
  <line x1="160" y1="62" x2="160" y2="95" stroke="#6b7280" stroke-width="1.5" marker-end="url(#arr)"/>

  <!-- ===== 6.2 申込データの変換 section ===== -->
  <rect x="22" y="95" width="276" height="668" rx="10"
        fill="#eff6ff" stroke="#93c5fd" stroke-width="1.5"
        stroke-dasharray="6 3"/>
  <text x="160" y="114" text-anchor="middle" font-size="12" font-weight="bold" fill="#1d4ed8">6.2　申込データの変換</text>

  <!-- Step 1 -->
  <rect x="60" y="122" width="200" height="38" rx="6" fill="#fff" stroke="#93c5fd" stroke-width="1.5"/>
  <text x="160" y="137" text-anchor="middle" font-size="11" fill="#1e293b">ステップ1</text>
  <text x="160" y="152" text-anchor="middle" font-size="11" fill="#1e293b">ファイルをコピー</text>
  <line x1="160" y1="160" x2="160" y2="180" stroke="#6b7280" stroke-width="1.5" marker-end="url(#arr)"/>

  <!-- Step 2 -->
  <rect x="60" y="180" width="200" height="38" rx="6" fill="#fff" stroke="#93c5fd" stroke-width="1.5"/>
  <text x="160" y="195" text-anchor="middle" font-size="11" fill="#1e293b">ステップ2</text>
  <text x="160" y="210" text-anchor="middle" font-size="11" fill="#1e293b">列名の確認・対応把握</text>
  <line x1="160" y1="218" x2="160" y2="238" stroke="#6b7280" stroke-width="1.5" marker-end="url(#arr)"/>

  <!-- Step 3 -->
  <rect x="60" y="238" width="200" height="38" rx="6" fill="#fff" stroke="#93c5fd" stroke-width="1.5"/>
  <text x="160" y="253" text-anchor="middle" font-size="11" fill="#1e293b">ステップ3</text>
  <text x="160" y="268" text-anchor="middle" font-size="11" fill="#1e293b">タイブレーク列の空欄補完</text>
  <line x1="160" y1="276" x2="160" y2="296" stroke="#6b7280" stroke-width="1.5" marker-end="url(#arr)"/>

  <!-- Step 4 diamond -->
  <polygon points="160,296 222,326 160,356 98,326"
           fill="#fff" stroke="#93c5fd" stroke-width="1.5"/>
  <text x="160" y="321" text-anchor="middle" font-size="11" fill="#1e293b">ステップ4</text>
  <text x="160" y="338" text-anchor="middle" font-size="11" fill="#1e293b">スコア計算</text>

  <!-- branch labels -->
  <text x="72" y="376" text-anchor="middle" font-size="9" fill="#6b7280">施設ごとに</text>
  <text x="72" y="387" text-anchor="middle" font-size="9" fill="#6b7280">スコアが異なる</text>
  <text x="72" y="398" text-anchor="middle" font-size="9" fill="#6b7280">または汎用</text>
  <text x="248" y="376" text-anchor="middle" font-size="9" fill="#6b7280">全施設で</text>
  <text x="248" y="387" text-anchor="middle" font-size="9" fill="#6b7280">スコアが同一</text>

  <!-- left branch line to Approach A -->
  <line x1="98" y1="326" x2="72" y2="326" stroke="#6b7280" stroke-width="1.5"/>
  <line x1="72" y1="326" x2="72" y2="400" stroke="#6b7280" stroke-width="1.5" marker-end="url(#arr)"/>

  <!-- right branch line to Approach B -->
  <line x1="222" y1="326" x2="248" y2="326" stroke="#6b7280" stroke-width="1.5"/>
  <line x1="248" y1="326" x2="248" y2="400" stroke="#6b7280" stroke-width="1.5" marker-end="url(#arr)"/>

  <!-- Approach A -->
  <rect x="30" y="400" width="84" height="50" rx="6" fill="#dbeafe" stroke="#93c5fd" stroke-width="1.5"/>
  <text x="72" y="416" text-anchor="middle" font-size="10" fill="#1e293b">アプローチA</text>
  <text x="72" y="430" text-anchor="middle" font-size="10" fill="#1e293b">スコア文字列</text>
  <text x="72" y="444" text-anchor="middle" font-size="10" fill="#1e293b">連結</text>

  <!-- Approach B -->
  <rect x="206" y="400" width="84" height="50" rx="6" fill="#dbeafe" stroke="#93c5fd" stroke-width="1.5"/>
  <text x="248" y="416" text-anchor="middle" font-size="10" fill="#1e293b">アプローチB</text>
  <text x="248" y="430" text-anchor="middle" font-size="10" fill="#1e293b">繰り返し</text>
  <text x="248" y="444" text-anchor="middle" font-size="10" fill="#1e293b">ソート</text>

  <!-- merge back to step 5 -->
  <line x1="72" y1="450" x2="72" y2="474" stroke="#6b7280" stroke-width="1.5"/>
  <line x1="72" y1="474" x2="160" y2="474" stroke="#6b7280" stroke-width="1.5"/>
  <line x1="248" y1="450" x2="248" y2="474" stroke="#6b7280" stroke-width="1.5"/>
  <line x1="248" y1="474" x2="160" y2="474" stroke="#6b7280" stroke-width="1.5"/>
  <line x1="160" y1="474" x2="160" y2="490" stroke="#6b7280" stroke-width="1.5" marker-end="url(#arr)"/>

  <!-- Step 5 -->
  <rect x="60" y="490" width="200" height="38" rx="6" fill="#fff" stroke="#93c5fd" stroke-width="1.5"/>
  <text x="160" y="505" text-anchor="middle" font-size="11" fill="#1e293b">ステップ5</text>
  <text x="160" y="520" text-anchor="middle" font-size="11" fill="#1e293b">希望施設コードの整形</text>
  <line x1="160" y1="528" x2="160" y2="548" stroke="#6b7280" stroke-width="1.5" marker-end="url(#arr)"/>

  <!-- Step 6 -->
  <rect x="60" y="548" width="200" height="50" rx="6" fill="#fff" stroke="#93c5fd" stroke-width="1.5"/>
  <text x="160" y="563" text-anchor="middle" font-size="11" fill="#1e293b">ステップ6</text>
  <text x="160" y="578" text-anchor="middle" font-size="11" fill="#1e293b">転所元・きょうだい条件の</text>
  <text x="160" y="592" text-anchor="middle" font-size="11" fill="#1e293b">整形</text>
  <line x1="160" y1="598" x2="160" y2="618" stroke="#6b7280" stroke-width="1.5" marker-end="url(#arr)"/>

  <!-- Step 7 -->
  <rect x="60" y="618" width="200" height="38" rx="6" fill="#fff" stroke="#93c5fd" stroke-width="1.5"/>
  <text x="160" y="633" text-anchor="middle" font-size="11" fill="#1e293b">ステップ7</text>
  <text x="160" y="648" text-anchor="middle" font-size="11" fill="#1e293b">ファイルを保存</text>
  <line x1="160" y1="656" x2="160" y2="680" stroke="#6b7280" stroke-width="1.5" marker-end="url(#arr)"/>

  <!-- 変換後申込データ output -->
  <ellipse cx="160" cy="700" rx="110" ry="22" fill="#bbf7d0" stroke="#15803d" stroke-width="1.5"/>
  <text x="160" y="705" text-anchor="middle" font-size="11" fill="#14532d">変換後申込データ.xlsx</text>

  <!-- ===== 6.3 募集人数データの変換 section (right column) ===== -->
  <rect x="312" y="270" width="270" height="392" rx="10"
        fill="#f5f3ff" stroke="#c4b5fd" stroke-width="1.5"
        stroke-dasharray="6 3"/>
  <text x="447" y="289" text-anchor="middle" font-size="12" font-weight="bold" fill="#6d28d9">6.3　募集人数データの変換</text>

  <!-- 募集人数データ input -->
  <ellipse cx="447" cy="230" rx="110" ry="22" fill="#fef08a" stroke="#ca8a04" stroke-width="1.5"/>
  <text x="447" y="235" text-anchor="middle" font-size="12" fill="#713f12">募集人数データ.xlsx</text>
  <line x1="447" y1="252" x2="447" y2="296" stroke="#6b7280" stroke-width="1.5" marker-end="url(#arr)"/>

  <!-- R Step 1 -->
  <rect x="357" y="300" width="180" height="38" rx="6" fill="#fff" stroke="#c4b5fd" stroke-width="1.5"/>
  <text x="447" y="315" text-anchor="middle" font-size="11" fill="#1e293b">ステップ1</text>
  <text x="447" y="330" text-anchor="middle" font-size="11" fill="#1e293b">ファイルを開く</text>
  <line x1="447" y1="338" x2="447" y2="358" stroke="#6b7280" stroke-width="1.5" marker-end="url(#arr)"/>

  <!-- R Step 2 -->
  <rect x="357" y="358" width="180" height="38" rx="6" fill="#fff" stroke="#c4b5fd" stroke-width="1.5"/>
  <text x="447" y="373" text-anchor="middle" font-size="11" fill="#1e293b">ステップ2</text>
  <text x="447" y="388" text-anchor="middle" font-size="11" fill="#1e293b">定員を整数化</text>
  <line x1="447" y1="396" x2="447" y2="416" stroke="#6b7280" stroke-width="1.5" marker-end="url(#arr)"/>

  <!-- R Step 3 -->
  <rect x="357" y="416" width="180" height="38" rx="6" fill="#fff" stroke="#c4b5fd" stroke-width="1.5"/>
  <text x="447" y="431" text-anchor="middle" font-size="11" fill="#1e293b">ステップ3</text>
  <text x="447" y="446" text-anchor="middle" font-size="11" fill="#1e293b">ファイルを保存</text>
  <line x1="447" y1="454" x2="447" y2="480" stroke="#6b7280" stroke-width="1.5" marker-end="url(#arr)"/>

  <!-- 変換後募集人数データ output -->
  <ellipse cx="447" cy="500" rx="120" ry="22" fill="#bbf7d0" stroke="#15803d" stroke-width="1.5"/>
  <text x="447" y="505" text-anchor="middle" font-size="11" fill="#14532d">変換後募集人数データ.xlsx</text>

  <!-- converge both outputs to ChilmAI upload -->
  <line x1="160" y1="722" x2="160" y2="770" stroke="#6b7280" stroke-width="1.5"/>
  <line x1="160" y1="770" x2="300" y2="770" stroke="#6b7280" stroke-width="1.5"/>
  <line x1="447" y1="522" x2="447" y2="770" stroke="#6b7280" stroke-width="1.5"/>
  <line x1="447" y1="770" x2="300" y2="770" stroke="#6b7280" stroke-width="1.5"/>
  <line x1="300" y1="770" x2="300" y2="800" stroke="#6b7280" stroke-width="1.5" marker-end="url(#arr)"/>

  <!-- ChilmAI upload final step -->
  <ellipse cx="300" cy="830" rx="145" ry="28" fill="#e9d5ff" stroke="#7c3aed" stroke-width="1.5"/>
  <text x="300" y="825" text-anchor="middle" font-size="12" fill="#4c1d95">ChilmAI へアップロード</text>
  <text x="300" y="842" text-anchor="middle" font-size="12" fill="#4c1d95">▶ 8章へ</text>

</svg>
</body>
</html>
""".format(W=SVG_WIDTH, H=SVG_HEIGHT)


def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
        f.write(HTML)
        tmp_path = f.name

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": SVG_WIDTH, "height": SVG_HEIGHT})
            page.goto(f"file://{tmp_path}", wait_until="networkidle")
            page.screenshot(
                path=str(OUT_PATH), clip={"x": 0, "y": 0, "width": SVG_WIDTH, "height": SVG_HEIGHT}
            )
            browser.close()
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    print(f"✓ {OUT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
