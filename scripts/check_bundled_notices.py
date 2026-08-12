"""Check the generated THIRD-PARTY-NOTICES.txt actually discloses what it must.

Run against a built distribution:

    uv run python scripts/check_bundled_notices.py dist/ChilmAI

The generated file is assembled from several sources, and a missing piece still
produces a valid-looking document -- the hand-written ortools notes could drop
out and the package list alone would carry on. So the content is asserted
explicitly after the build.

This lives in Python rather than inline PowerShell so it can be run locally
against a real distribution, on any platform.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

NOTICES_FILE = "THIRD-PARTY-NOTICES.txt"

# 落ちたら気づけないもの。文言ではなく論点で見る。
REQUIRED_TEXT = (
    "Code bundled inside those packages",
    "Rust crates compiled into the extension modules",
    "Cbc",  # Coin-OR (EPL-2.0)
    "Eigen",  # MPL-2.0
    "GLPK",  # GPL-3.0-or-later。未リンクである旨に触れていること
    "HiGHS",
    "Bootloader-exception",  # PyInstaller
    # CPython ランタイム。依存グラフ起点のチェックには
    # 引っかからない層なので、ここでしか検出できない。
    "CPython runtime frozen into ChilmAI.exe",
    "Python-2.0",  # CPython 本体
    "OpenSSL",  # Apache-2.0
    "Microsoft Distributable Code",  # vcruntime140*.dll / msvcp140.dll
)

# クレート一覧を必ず持つべき Rust 拡張。合算で数えると一方の欠落を他方が隠すので
# パッケージごとに見る（pydantic-core が 0 件のまま通っていたことがある）。
RUST_EXTENSIONS = ("python-calamine", "pydantic-core")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <dist dir>", file=sys.stderr)
        return 2

    path = Path(argv[1]) / NOTICES_FILE
    if not path.is_file():
        print(f"{path} does not exist", file=sys.stderr)
        return 1
    text = path.read_text(encoding="utf-8")

    problems = [f"missing {needle!r}" for needle in REQUIRED_TEXT if needle not in text]

    for package in RUST_EXTENSIONS:
        # 配布物は CRLF なので行末を固定しない。
        match = re.search(rf"^{re.escape(package)} -- (\d+) crates\s*$", text, re.MULTILINE)
        if match is None:
            problems.append(f"no crate list for {package}")
            continue
        count = int(match.group(1))
        print(f"  {package} -> {count} crates")
        if count < 1:
            problems.append(f"{package} contributes no crates")

    if problems:
        print(f"\n{NOTICES_FILE} is incomplete:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    # len(text) はコードポイント数で、しかもテキスト読みで CRLF が 1 文字に
    # 畳まれているため、バイト数としては両方向にずれる。実ファイルを見る。
    print(f"{NOTICES_FILE}: {path.stat().st_size} bytes, all required disclosures present")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
