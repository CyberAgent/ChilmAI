"""Build Windows standalone executable for generic FastAPI app."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import sqlite3
import ssl
import subprocess
import sys
import sysconfig
from importlib.metadata import PackageNotFoundError, distribution, requires
from pathlib import Path
from typing import NamedTuple

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]

# ChilmAI 自身のライセンス関連ファイル。配布物にそのまま同梱する。
OWN_LICENSE_FILES = ["LICENSE", "NOTICE", "TRADEMARK.md"]

# 配布物に置く第三者ライセンス関連のファイル。役割ごとに分ける。
#
#   THIRD-PARTY-NOTICES.txt  同梱物の一覧（名前・版・ライセンス・ソース URL）
#   licenses/                上流のライセンス / NOTICE 原文をそのまま配置
#
# 条文を 1 つのテキストに連結するのはやめた。上流の原文をそのまま置けば、
# 著作権表示の保持も改変していないことの説明も同時に済む。
#
# 機械可読な SBOM (CycloneDX) は出さない。どのライセンスも SBOM 形式を要求して
# おらず、この配布物は参考実装なので調達・審査の対象にしない。一覧はテキストで
# 一度出せば足りる。
THIRD_PARTY_NOTICES_FILE = "THIRD-PARTY-NOTICES.txt"
DIST_LICENSE_DIR = "licenses"

# dist-info 内でライセンス条文・帰属表示とみなすファイル名の接頭辞。
LICENSE_FILE_PREFIXES = ("LICENSE", "LICENCE", "NOTICE", "COPYING")

# ライセンスファイルを一切同梱していない配布物。手書きの注記で開示している
# ものだけを挙げる。未登録のパッケージに条文が無ければビルドを止める
# （verify_license_files_are_present）。
NO_LICENSE_TEXT_PACKAGES = {"ortools"}

# 手書きで補う情報の置き場。詳細は apps/licenses/README.md。
SUPPLEMENT_DIR = ROOT / "apps" / "licenses"
SUPPLEMENT_NOTICE_FILE = "bundled-native-notices.txt"

# 弱コピーレフトの条文全文。ソース入手方法の告知は BUNDLED_NATIVE_COMPONENTS の
# 取得元タグとパッチ URL が担い、条文の同梱はそれとは別に確実な側に倒して置く
# （条項の詳細は apps/licenses/README.md）。
SHARED_LICENSE_TEXTS = {
    "EPL-2.0": "EPL-2.0.txt",
    "MPL-2.0": "MPL-2.0.txt",
    # PyInstaller の COPYING.txt 原文。Bootloader Exception の条項そのものが
    # 入っているので、こちらを配るのが一番確実（SPDX ID も上流の表記に合わせる）。
    "GPL-2.0-or-later WITH Bootloader-exception": "PyInstaller-COPYING.txt",
}

# 選択（election）後のライセンスと対応する条文。デュアルライセンスは
# Apache-2.0 に寄せる方針なので、大半がその 1 本で足りる。
SPDX_TEXT_SUBDIR = "spdx"
SPDX_TEXT_FILES: dict[str, str | None] = {
    # 配布物直下の LICENSE が Apache-2.0 の全文そのものなので重複させない。
    "Apache-2.0": None,
    "Apache-2.0 WITH LLVM-exception": "LLVM-exception.txt",
    "BSD-3-Clause": "BSD-3-Clause.txt",
    "MIT": "MIT.txt",
    "Unicode-3.0": "Unicode-3.0.txt",
    "Unicode-DFS-2016": "Unicode-DFS-2016.txt",
    "Zlib": "Zlib.txt",
}

# SBOM を同梱していない Rust 拡張のクレート一覧。上流のリリースタグの
# Cargo.lock から scripts/collect_rust_crate_notices.py が生成する。crates.io への
# アクセスが必要なのでリリースビルド中には作らず、出力をコミットして読み込む。
#
# Cargo.lock は target / feature / 依存種別を解決しないため、実際に wheel へ
# コンパイルされるものより多い。「静的リンク済み」とは書かず、保守的な
# ビルド依存一覧として出す（過剰開示は無害、開示漏れは義務違反）。
CARGO_LOCK_CRATES_FILE = "cargo-lock-crates.json"
CARGO_LOCK_SCOPE_NOTE = "conservative superset from Cargo.lock; not resolved per target/feature"

# クレート自身の条文原文。汎用の SPDX 条文では著作権行が渡らないため
# （apps/licenses/README.md）、.crate 内の LICENSE / NOTICE を
# scripts/collect_rust_crate_notices.py が原文のまま取得する。抽出も転記もしない。
CARGO_CRATE_SUBDIR = "cargo"
CARGO_CRATE_MANIFEST_FILE = "cargo-crate-notices.json"

# 同じ理由で、手書きのネイティブ同梱物も上流の条文・帰属表示を原文で配る。
# scripts/collect_native_notices.py が native/<コンポーネント>/<ファイル名> に置く。
# クレート側と違って内容アドレスにしない。置き場所が BundledComponent.notices
# から直接決まるので、マニフェストも不要（判断の経緯は apps/licenses/README.md）。
NATIVE_NOTICE_SUBDIR = "native"

# クレート一覧を必ず持つべき Rust 拡張。wheel の SBOM か、上記の Cargo.lock
# 由来データのどちらかで埋まっていなければビルドを止める。自身のライセンスだけ
# では、静的リンクされた第三者クレートの著作権表示までは満たせない。
RUST_EXTENSION_PACKAGES = ("python-calamine", "pydantic-core")

# デュアルライセンスから実際に依拠する 1 本を選ぶ優先順位。Apache-2.0 の全文は
# 配布物直下の LICENSE そのものなので、そこへ寄せると同梱すべき条文が最小になる。
ELECTION_PREFERENCE = ("Apache-2.0", "MIT")


class BundledComponent(NamedTuple):
    """One thing compiled into a prebuilt wheel, and the source it was built from."""

    parent: str
    name: str
    version: str
    spdx: str
    source: str
    # ortools は取得したコンポーネントに自前のパッチを当ててからコンパイルする。
    # 当たっているものは「取得元 + このパッチ」が対応ソースなので併記する。
    patch: str | None = None
    # 上流が固定タグではなくブランチを指しているもの。正確なリビジョンは
    # マニフェストから決まらないので、憶測で埋めずその事実を書く。
    unpinned: bool = False
    # 上流のライセンス / 帰属表示ファイルの raw URL。SPDX の汎用条文では
    # 著作権行が渡らないので（"Copyright (c) <year> <owner>." になる）、
    # 原文をバイト単位で保存して配る。tree URL からの機械的な導出はブランチ名に
    # "/" を含むと曖昧なので、取得できる URL をそのまま書く。
    # scripts/collect_native_notices.py が native/<name>/<basename> に保存する。
    notices: tuple[str, ...] = ()
    # 上流原文を持たない代わりに SHARED_LICENSE_TEXTS 経由で条文を配るもの。
    # 免除の理由をデータで持つ。ライセンス種別で判定すると EPL-2.0 / MPL-2.0 の
    # コンポーネントまで素通りしてしまう。
    notice_from_shared_text: bool = False


# Python のメタデータにも wheel の SBOM にも現れない同梱物。ここだけは手書き。
# 上流のマニフェストと実バイナリの両方で裏を取ってから書く（手順は
# apps/licenses/README.md）。
#
# **取得元は GIT_TAG だけを見ても分からない。** ortools は Coin-OR について
# coin-or/* ではなく CMake 対応フォークの Mizux/* を取得し、さらに PATCH_COMMAND で
# パッチを当てる。上流プロジェクトのリリースタグを書くと、実際にビルドされた
# ソースを指さないことになる。GIT_REPOSITORY と PATCH_COMMAND まで読むこと。
ORTOOLS_PATCH = "https://github.com/google/or-tools/blob/v9.8/patches/{}"
BUNDLED_NATIVE_COMPONENTS = [
    # ortools の wheel はこれらを静的リンクする。9.8 の Windows wheel は共有
    # ライブラリを持たず、モジュールごとの .pyd に個別に入っている（CP-SAT の
    # .pyd 自体も Coin-OR と Eigen を含む）。構成はプラットフォームと版で変わる。
    #
    # Coin-OR の 5 件は Mizux の CMake 対応フォークの cmake/<version> タグ。
    # upstream の releases/<version> には CMakeLists.txt が無く、同じ構成では
    # ビルドできない（= 対応ソースではない）。
    BundledComponent(
        "ortools",
        "CoinUtils",
        "2.11.6",
        "EPL-2.0",
        "https://github.com/Mizux/CoinUtils/tree/cmake/2.11.6",
        ORTOOLS_PATCH.format("coinutils-2.11.patch"),
        notices=(
            "https://raw.githubusercontent.com/Mizux/CoinUtils/cmake/2.11.6/LICENSE",
            "https://raw.githubusercontent.com/Mizux/CoinUtils/cmake/2.11.6/AUTHORS",
        ),
    ),
    BundledComponent(
        "ortools",
        "Osi",
        "0.108.7",
        "EPL-2.0",
        "https://github.com/Mizux/Osi/tree/cmake/0.108.7",
        ORTOOLS_PATCH.format("osi-0.108.patch"),
        notices=("https://raw.githubusercontent.com/Mizux/Osi/cmake/0.108.7/LICENSE",),
    ),
    BundledComponent(
        "ortools",
        "Clp",
        "1.17.7",
        "EPL-2.0",
        "https://github.com/Mizux/Clp/tree/cmake/1.17.7",
        # パッチのファイル名は上流の付け方で 1.17.4 のまま。実物に合わせる。
        ORTOOLS_PATCH.format("clp-1.17.4.patch"),
        notices=(
            "https://raw.githubusercontent.com/Mizux/Clp/cmake/1.17.7/LICENSE",
            "https://raw.githubusercontent.com/Mizux/Clp/cmake/1.17.7/AUTHORS",
        ),
    ),
    BundledComponent(
        "ortools",
        "Cgl",
        "0.60.5",
        "EPL-2.0",
        "https://github.com/Mizux/Cgl/tree/cmake/0.60.5",
        ORTOOLS_PATCH.format("cgl-0.60.patch"),
        notices=(
            "https://raw.githubusercontent.com/Mizux/Cgl/cmake/0.60.5/LICENSE",
            "https://raw.githubusercontent.com/Mizux/Cgl/cmake/0.60.5/AUTHORS",
        ),
    ),
    BundledComponent(
        "ortools",
        "Cbc",
        "2.10.7",
        "EPL-2.0",
        "https://github.com/Mizux/Cbc/tree/cmake/2.10.7",
        ORTOOLS_PATCH.format("cbc-2.10.patch"),
        notices=(
            "https://raw.githubusercontent.com/Mizux/Cbc/cmake/2.10.7/LICENSE",
            "https://raw.githubusercontent.com/Mizux/Cbc/cmake/2.10.7/AUTHORS",
        ),
    ),
    BundledComponent(
        "ortools",
        "Eigen",
        "3.4.0",
        "MPL-2.0",
        "https://gitlab.com/libeigen/eigen/-/tree/3.4.0",
        ORTOOLS_PATCH.format("eigen3-3.4.0.patch"),
        notices=(
            "https://gitlab.com/libeigen/eigen/-/raw/3.4.0/COPYING.README",
            "https://gitlab.com/libeigen/eigen/-/raw/3.4.0/COPYING.MPL2",
            "https://gitlab.com/libeigen/eigen/-/raw/3.4.0/COPYING.BSD",
            "https://gitlab.com/libeigen/eigen/-/raw/3.4.0/COPYING.APACHE",
            "https://gitlab.com/libeigen/eigen/-/raw/3.4.0/COPYING.MINPACK",
            "https://gitlab.com/libeigen/eigen/-/raw/3.4.0/COPYING.GPL",
            "https://gitlab.com/libeigen/eigen/-/raw/3.4.0/COPYING.LGPL",
        ),
    ),
    # SCIP と re2 のパッチは v9.8 では PATCH_COMMAND がコメントアウトされている。
    BundledComponent(
        "ortools",
        "SCIP",
        "8.0.4",
        "Apache-2.0",
        "https://github.com/scipopt/scip/tree/v804",
        notices=("https://raw.githubusercontent.com/scipopt/scip/v804/LICENSE",),
    ),
    BundledComponent(
        "ortools",
        "re2",
        "2023-11-01",
        "BSD-3-Clause",
        "https://github.com/google/re2/tree/2023-11-01",
        notices=(
            "https://raw.githubusercontent.com/google/re2/2023-11-01/LICENSE",
            "https://raw.githubusercontent.com/google/re2/2023-11-01/AUTHORS",
        ),
    ),
    BundledComponent(
        "ortools",
        "abseil-cpp",
        "20230802.1",
        "Apache-2.0",
        "https://github.com/abseil/abseil-cpp/tree/20230802.1",
        ORTOOLS_PATCH.format("abseil-cpp-20230802.1.patch"),
        notices=(
            "https://raw.githubusercontent.com/abseil/abseil-cpp/20230802.1/LICENSE",
            "https://raw.githubusercontent.com/abseil/abseil-cpp/20230802.1/AUTHORS",
        ),
    ),
    BundledComponent(
        "ortools",
        "protobuf",
        "25.0",
        "BSD-3-Clause",
        "https://github.com/protocolbuffers/protobuf/tree/v25.0",
        ORTOOLS_PATCH.format("protobuf-v25.0.patch"),
        notices=("https://raw.githubusercontent.com/protocolbuffers/protobuf/v25.0/LICENSE",),
    ),
    BundledComponent(
        "ortools",
        "zlib",
        "1.2.13",
        "Zlib",
        "https://github.com/madler/zlib/tree/v1.2.13",
        ORTOOLS_PATCH.format("ZLIB.patch"),
        notices=("https://raw.githubusercontent.com/madler/zlib/v1.2.13/LICENSE",),
    ),
    BundledComponent(
        "ortools",
        "pybind11",
        "2.10.3",
        "BSD-3-Clause",
        "https://github.com/pybind/pybind11/tree/v2.10.3",
        ORTOOLS_PATCH.format("pybind11.patch"),
        notices=("https://raw.githubusercontent.com/pybind/pybind11/v2.10.3/LICENSE",),
    ),
    # v9.8 はこれをタグではなく main ブランチから取っている（GIT_TAG "main"）。
    # ビルド時点のリビジョンは上流に記録が無いので、固定できない旨をそのまま出す。
    BundledComponent(
        "ortools",
        "pybind11_protobuf",
        "unpinned",
        # 上流の LICENSE は Apache-2.0 ではなく BSD-3-Clause
        # （"Copyright (c) 2019-2021 The Pybind Development Team"）。
        "BSD-3-Clause",
        "https://github.com/pybind/pybind11_protobuf",
        ORTOOLS_PATCH.format("pybind11_protobuf.patch"),
        unpinned=True,
        notices=("https://raw.githubusercontent.com/pybind/pybind11_protobuf/main/LICENSE",),
    ),
    # exe の先頭に埋め込まれる PyInstaller のブートローダ。GPL-2.0-or-later だが、
    # Bootloader Exception が組み込み配布を明示的に許諾している。
    BundledComponent(
        "ChilmAI.exe",
        "PyInstaller bootloader",
        "6.21.0",
        "GPL-2.0-or-later WITH Bootloader-exception",
        "https://github.com/pyinstaller/pyinstaller/tree/v6.21.0/bootloader",
        # 上流の COPYING.txt 原文をブートローダ例外の条項ごと
        # PyInstaller-COPYING.txt として配っているので、別に取り直さない。
        notice_from_shared_text=True,
    ),
]

# PyInstaller が exe にバンドルする CPython ランタイムそのものと、Windows の
# 処理系に含まれてくるネイティブ DLL。
#
# これらは pip のパッケージではない。上のチェックはすべて
# runtime_distribution_names() を起点にするので、CPython 本体も、それに
# 含まれる OpenSSL や libffi もそちらには引っかからない。
#
# バージョンは固定しない。どの処理系がバンドルされるかはビルド環境で決まる
# （CI は actions/setup-python、手元は uv 管理の python-build-standalone）。
# 固定値を書くと、実際に配る zip の中身と食い違う。実行中の処理系から読む。
RUNTIME_NOTICE_SUBDIR = "runtime"

# 処理系自身が持つライセンス原文。python-build-standalone も python.org の
# Windows ビルドも、PSF 条文に加えて「この Windows バイナリ固有の条件」として
# Microsoft Distributable Code・bzip2・Tcl/Tk の条項を同じファイルに載せている。
# 上流から取り直すより、バンドルする処理系のものをそのまま配る方が正確で、
# ビルド中にネットワークも要らない。
INTERPRETER_LICENSE_NAMES = ("LICENSE.txt", "LICENSE")


class RuntimeComponent(NamedTuple):
    """Native code the frozen CPython runtime brings with it, not any wheel."""

    name: str
    version: str
    spdx: str
    source: str
    # 上流のライセンス原文の raw URL。scripts/collect_native_notices.py が
    # runtime/<name>/<basename> に保存する。
    notices: tuple[str, ...] = ()
    # 処理系自身の LICENSE が条項を含んでいるもの。別途取り直さない。
    notice_from_interpreter: bool = False


# 上流のライセンス原文は系列内で変わらないので、取得元タグは固定でよい。
# 実際に同梱される版は runtime_components() が処理系から読んで一覧に出す。
OPENSSL_NOTICE = "https://raw.githubusercontent.com/openssl/openssl/openssl-3.0.0/LICENSE.txt"
LIBFFI_NOTICE = "https://raw.githubusercontent.com/libffi/libffi/v3.4.6/LICENSE"
SQLITE_NOTICE = "https://raw.githubusercontent.com/sqlite/sqlite/version-3.45.0/LICENSE.md"


def interpreter_openssl_version() -> str:
    """Return just the version out of ``ssl.OPENSSL_VERSION``.

    The constant reads "OpenSSL 3.5.4 30 Sep 2025", and the build ships whatever
    the frozen interpreter links -- 3.0.x from actions/python-versions, 3.5.x
    from a uv-managed build -- so this is read rather than pinned.
    """
    match = re.search(r"\b(\d+\.\d+\.\d+[a-z]*)\b", ssl.OPENSSL_VERSION)
    return match.group(1) if match else ssl.OPENSSL_VERSION


def runtime_components() -> list[RuntimeComponent]:
    """Return the native code the frozen interpreter contributes.

    Every version here is read from the interpreter that PyInstaller is about to
    freeze, so the inventory describes the artifact actually being built.

    libffi is the one exception: it exposes no version to Python. Its ABI number
    is in the file name (libffi-8.dll) and that is all the distribution can state
    truthfully, so it is reported as the ABI rather than guessed at.
    """
    components = [
        RuntimeComponent(
            "CPython",
            platform.python_version(),
            "Python-2.0",
            f"https://github.com/python/cpython/tree/v{platform.python_version()}",
            notice_from_interpreter=True,
        ),
        RuntimeComponent(
            "OpenSSL",
            interpreter_openssl_version(),
            "Apache-2.0",
            "https://github.com/openssl/openssl",
            notices=(OPENSSL_NOTICE,),
        ),
        RuntimeComponent(
            "SQLite",
            sqlite3.sqlite_version,
            "blessing",
            "https://www.sqlite.org/src/",
            notices=(SQLITE_NOTICE,),
        ),
        RuntimeComponent(
            "libffi",
            "ABI 8",
            "MIT",
            "https://github.com/libffi/libffi",
            notices=(LIBFFI_NOTICE,),
        ),
    ]

    # Microsoft の再頒布物。MSVC でビルドされた処理系にだけ含まれる。
    # 条項は処理系の LICENSE が "Additional Conditions for this Windows binary
    # build" として持っており、Windows バイナリの再頒布を明示的に許諾している。
    #
    # どれが実際に同梱されるかは、ビルドされる処理系に依存する。actions/setup-python は
    # UCRT が含まれるが、uv 管理のビルドには含まれない。片方だけだと手元では
    # 通って CI で止まるので、両方を載せておく（過剰な開示は無害、足りない
    # 開示は義務違反）。
    compiler = platform.python_compiler()
    if compiler.startswith("MSC"):
        components += [
            RuntimeComponent(
                "Microsoft Visual C++ runtime",
                compiler,
                "Microsoft Distributable Code",
                "https://visualstudio.microsoft.com/license-terms/",
                notice_from_interpreter=True,
            ),
            # ucrtbase.dll と api-ms-win-*.dll。
            RuntimeComponent(
                "Microsoft Universal C Runtime",
                compiler,
                "Microsoft Distributable Code",
                "https://visualstudio.microsoft.com/license-terms/",
                notice_from_interpreter=True,
            ),
        ]
    return components


# _internal/ 直下に置かれる DLL と、それを説明する RuntimeComponent。
# pip の依存関係を起点にするチェックではこの層を拾えないので、「配布物に
# 実在する DLL」の側から照合して、説明の無いものが見つかったら止める。
# wheel に含まれる DLL はパッケージのサブディレクトリに入るため対象外
# （numpy.libs/、pandas.libs/ は各パッケージの LICENSE が開示している）。
RUNTIME_DLL_OWNERS = (
    (re.compile(r"^python3\d*\.dll$", re.IGNORECASE), "CPython"),
    (re.compile(r"^lib(ssl|crypto)-\d+.*\.dll$", re.IGNORECASE), "OpenSSL"),
    (re.compile(r"^sqlite3\.dll$", re.IGNORECASE), "SQLite"),
    (re.compile(r"^libffi-\d+\.dll$", re.IGNORECASE), "libffi"),
    (
        re.compile(r"^(vcruntime|msvcp|msvcr|concrt)\d+(_\d+)?\.dll$", re.IGNORECASE),
        "Microsoft Visual C++ runtime",
    ),
    # ucrtbase.dll と api-ms-win-*.dll。actions/setup-python の処理系に含まれる。
    (
        re.compile(r"^(ucrtbase\.dll|api-ms-win-[\w.-]+\.dll)$", re.IGNORECASE),
        "Microsoft Universal C Runtime",
    ),
)

# 許容的（permissive）と判断済みのライセンス。ここに載っていないものは
# 「未検討」としてビルドを止める。拒否リストにしない理由と SPDX 式の判定の
# 意味論は apps/licenses/README.md。
#
# 正規化して比較するので小文字で書くこと。ここへの追加は「このライセンスなら
# 無改変のバイナリ再配布に追加義務が生じない」という法務判断なので、
# 外すと現在の依存のどれかが通らなくなる項だけを載せる。OR で許容的な選択肢と
# 並んでいるだけのものは不要（未知のライセンスはビルド失敗で気づける）。
PERMISSIVE_LICENSES = {
    # PEP 639 の SPDX 表記
    "apache-2.0",
    "bsd-2-clause",
    "bsd-3-clause",
    "mit",
    "psf-2.0",
    "zlib",
    # wheel の PEP 770 SBOM / Cargo.lock に現れる Rust クレートのライセンス。
    # WITH 例外は分割せず 1 項として扱うので、この表記のまま登録する。
    "apache-2.0 with llvm-exception",
    "unicode-3.0",
    "unicode-dfs-2016",
    # Trove classifier 表記。pip-licenses は分類子から組み立てた文字列を返すので
    # SPDX ID と混在する。
    "3-clause bsd license",
    "apache software license",
    "bsd license",
    "mit license",
}

# 個別に検討済みで、bundled-native-notices.txt で開示しているパッケージ。
# パッケージ名ではなく「そのパッケージが宣言しているライセンス文字列」まで
# 一致を要求する。バージョンを上げてライセンスが変わったら再検討が必要なので、
# パッケージ単位の免除にすると変更を見逃す。
# ここに追加するときは必ず補遺の記述も更新する。
REVIEWED_LICENSE_PACKAGES = {
    # MPL-2.0 と MIT のデュアル。MPL 部分は未改変で再配布し、ソース入手先を
    # 補遺に記載している。
    "tqdm": "MIT License; Mozilla Public License 2.0 (MPL 2.0)",
}

# ネイティブ拡張を含む配布物は、静的リンクされた C / Rust ライブラリという形で
# Python のメタデータに現れない第三者コードを抱えている可能性がある。新しく
# 増えたときに開示の検討を強制するため、確認済みのものと根拠を残しておく。
#
# 「確認したバージョン」まで記録する。同梱物はバージョンごとに変わる
# （numpy の OpenBLAS、ortools の Coin-OR は実際に上げると入れ替わる）ので、
# 名前だけの免除ではバージョンを上げた瞬間に検査が意味を失う。
# バージョンを上げたら中身を再確認し、根拠を更新してからここを書き換える。
# 手順は apps/licenses/README.md。
NATIVE_EXTENSION_SUFFIXES = (".so", ".pyd", ".dll", ".dylib")
NATIVE_REVIEWED_PACKAGES = {
    # 同梱ライブラリ（OpenBLAS、libgfortran ほか）を upstream の LICENSE.txt が
    # 自前で開示しており、pip-licenses がそれをそのまま取り込む。
    "numpy": ("1.26.4", "upstream LICENSE.txt discloses its bundled libraries"),
    # PEP 770 の SBOM でリンク先の Rust クレートを申告している。
    # wheel_declared_crates() がそれを読む。
    "python-calamine": ("0.8.2", "ships a PEP 770 SBOM listing its Rust crates"),
    # ライセンスファイルを一切同梱していない。手書きの注記で開示する。
    "ortools": ("9.8.3296", "documented by hand in bundled-native-notices.txt"),
    # SBOM を持たない Rust 拡張。上流のリリースタグの Cargo.lock 由来の一覧を
    # apps/licenses/cargo-lock-crates.json から読む。
    "pydantic-core": ("2.41.5", "crates recorded from the upstream Cargo.lock"),
    # 自前のソースをビルドしただけで、第三者ライブラリを同梱していない。
    "pandas": ("2.2.3", "no third-party libraries bundled"),
    "protobuf": ("7.34.0", "no third-party libraries bundled"),
    "markupsafe": ("3.0.3", "no third-party libraries bundled"),
    "wrapt": ("2.1.1", "no third-party libraries bundled"),
}


def build_pyi_args() -> list[str]:
    candidate_pairs = [
        (ROOT / "apps" / "api" / "static", Path("apps") / "api" / "static"),
        (ROOT / "apps" / "api" / "templates", Path("apps") / "api" / "templates"),
        (ROOT / "apps" / "api" / "assets", Path("apps") / "api" / "assets"),
        (ROOT / "chilmai" / "generic" / "column_aliases.json", Path("chilmai") / "generic"),
    ]
    data_pairs = [(src, dst) for src, dst in candidate_pairs if src.exists()]

    args = [
        *[f"--add-data={src}{os.pathsep}{dst}" for src, dst in data_pairs],
        # apps はインストールされない（wheel は chilmai のみ）ので、
        # PyInstaller の解析にはリポジトリ直下を検索パスとして渡す
        "--paths=" + str(ROOT),
        "--additional-hooks-dir=" + str(ROOT / "apps" / "pyinstaller_hooks"),
        "--copy-metadata=ChilmAI",
        "--icon=" + str(ROOT / "apps" / "api" / "assets" / "logo.ico"),
        "--name=ChilmAI",
        "--noconfirm",
        "--clean",
        "--distpath=" + str(ROOT / "dist"),
        str(ROOT / "apps" / "api_launcher.py"),
    ]
    return args


def copy_sample_dir(dist_dir: Path) -> None:
    """Copy sample/ next to the exe so users don't have to dig into _internal/.

    PyInstaller's --add-data places files under _internal/ in onedir builds,
    but sample/ is user-facing demo data, not a runtime dependency, so it
    must live beside ChilmAI.exe instead.
    """
    src = ROOT / "sample"
    if not src.exists():
        return
    shutil.copytree(src, dist_dir / "sample", dirs_exist_ok=True)


def copy_own_license_files(dist_dir: Path) -> None:
    """Copy ChilmAI's own LICENSE / NOTICE / TRADEMARK next to the exe.

    Apache-2.0 (section 4) requires binary redistributions to include a copy
    of the License and to retain the NOTICE contents, so these must ship in
    the distribution zip alongside ChilmAI.exe.
    """
    for name in OWN_LICENSE_FILES:
        src = ROOT / name
        if not src.exists():
            raise FileNotFoundError(f"Required license file is missing: {src}")
        shutil.copy2(src, dist_dir / name)


def runtime_distribution_names() -> list[str]:
    """Return the transitive runtime dependency closure of ChilmAI.

    Build-only extras (e.g. pyinstaller, pip-licenses) are excluded because
    their markers only evaluate true under an ``extra`` that is not set here,
    so the result reflects just the packages PyInstaller bundles into the exe.
    """
    root = "ChilmAI"
    root_key = canonicalize_name(root)
    seen: set[str] = set()
    names: list[str] = []
    queue: list[str] = [root]
    while queue:
        name = queue.pop(0)
        key = canonicalize_name(name)
        if key in seen:
            continue
        seen.add(key)
        if key != root_key:
            names.append(name)
        try:
            reqs = requires(name) or []
        except PackageNotFoundError:
            continue
        for raw in reqs:
            req = Requirement(raw)
            # Skip deps guarded by an extra (test/format/package/...) or by a
            # platform/python marker that does not apply to this environment.
            if req.marker is not None and not req.marker.evaluate():
                continue
            queue.append(req.name)
    return sorted(names, key=str.lower)


def piplicenses_records(packages: list[str]) -> list[dict[str, str]]:
    """Run pip-licenses over ``packages`` and return one record per package.

    ``--with-system`` is mandatory: pip-licenses silently drops the names in its
    SYSTEM_PACKAGES list (pip, setuptools, wheel, ...) even when they are asked
    for explicitly via ``--packages``. setuptools is a pinned direct runtime
    dependency of ChilmAI, so without this it was omitted from both the copyleft
    check and the license bundle, with a zero exit code either way.

    Any package that still comes back missing is an error rather than a silent
    gap -- a compliance document that quietly lists fewer packages than were
    requested is worse than a failed build.
    """
    if not packages:
        raise RuntimeError("Could not resolve any runtime dependencies for the license report")

    # 条文は自前で dist-info からコピーする（distribution_license_files）ので、
    # pip-licenses からは名前・版・宣言ライセンス・URL だけを受け取る。
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "piplicenses",
            "--from=mixed",
            "--with-system",
            "--with-authors",
            "--with-urls",
            "--format=json",
            "--packages",
            *packages,
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    records = json.loads(completed.stdout)

    returned = {canonicalize_name(record["Name"]) for record in records}
    missing = sorted(name for name in packages if canonicalize_name(name) not in returned)
    if missing:
        raise RuntimeError(
            "pip-licenses returned no record for these runtime dependencies:\n"
            + "".join(f"  - {name}\n" for name in missing)
            + "\nThey would be missing from THIRD-PARTY-NOTICES.txt and skipped by the\n"
            "copyleft check. pip-licenses hides its SYSTEM_PACKAGES unless --with-system\n"
            "is passed; check for a newly added name in that list."
        )
    return sorted(records, key=lambda record: record["Name"].lower())


def _split_top_level(text: str, operator: str) -> list[str]:
    """Split ``text`` on ``operator`` at parenthesis depth zero."""
    pattern = re.compile(rf"\b{operator}\b", re.IGNORECASE)
    parts, depth, start, index = [], 0, 0, 0
    while index < len(text):
        character = text[index]
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif depth == 0:
            match = pattern.match(text, index)
            if match:
                parts.append(text[start : match.start()])
                index = start = match.end()
                continue
        index += 1
    parts.append(text[start:])
    return [part for part in parts if part.strip()]


def _is_permissive_atom(text: str) -> bool:
    text = text.strip()
    if text.startswith("(") and text.endswith(")"):
        return is_permissive(text[1:-1])
    if text.casefold() in PERMISSIVE_LICENSES:
        return True
    # レガシーの "MIT/Apache-2.0" は OR の意味。ただし "Zlib/Libpng License" の
    # ように名前そのものが "/" を含む分類子があるので、完全一致を先に試す。
    if "/" in text:
        return any(_is_permissive_atom(option) for option in text.split("/"))
    return False


def is_permissive(declared: str) -> bool:
    """Return whether an SPDX expression can be satisfied permissively.

    ``OR`` is a choice, so one permissive option is enough -- a crate offered as
    "MIT OR Apache-2.0 OR LGPL-2.1-or-later" is taken under Apache-2.0 and the
    LGPL never applies. ``AND`` means every term binds, so all must be permissive.

    ``;`` gets the conservative treatment instead. pip-licenses joins multiple
    Trove classifiers with it, and a classifier list does not say whether the
    licenses are alternatives or cumulative, so all of them must be permissive.
    That is what keeps tqdm ("MIT License; Mozilla Public License 2.0") in front
    of a human rather than silently electing MIT on its behalf.
    """
    parts = [part for part in declared.split(";") if part.strip()]
    if not parts:
        return False
    return all(
        any(
            all(_is_permissive_atom(term) for term in _split_top_level(option, "AND"))
            for option in _split_top_level(part, "OR")
        )
        for part in parts
    )


def find_unreviewed_licenses(records: list[dict[str, str]]) -> list[tuple[str, str]]:
    """Return (package, declared license) pairs that are not known-permissive.

    Reviewed exemptions must match the declared license string exactly, so a
    version bump that relicenses a package stops being exempt automatically.
    """
    hits = []
    for record in records:
        declared = record.get("License", "UNKNOWN")
        if is_permissive(declared):
            continue
        reviewed = REVIEWED_LICENSE_PACKAGES.get(canonicalize_name(record["Name"]))
        if reviewed is not None and reviewed == declared:
            continue
        hits.append((record["Name"], declared))
    return hits


def verify_no_unreviewed_licenses() -> None:
    """Fail the build unless every runtime dependency is permissively licensed.

    pyxlsb (LGPLv3+) shipped inside the exe for several releases before anyone
    noticed, so this runs on every build instead of relying on code review to
    catch it.

    This is an allowlist on purpose. Enumerating copyleft licenses cannot be
    exhaustive -- EUPL-1.2, OSL-3.0, CECILL-2.1 and SSPL-1.0 are all strongly
    copyleft without containing "GPL" anywhere -- so an unrecognised license
    fails the build and gets looked at, rather than passing silently.

    This can only see what Python package metadata declares. Code that a
    prebuilt wheel statically links into its native libraries is invisible here
    -- Coin-OR under EPL-2.0 inside ortools, for one -- which is what
    verify_native_extensions_are_reviewed() and the hand-written notices in
    apps/licenses/bundled-native-notices.txt cover.
    """
    hits = find_unreviewed_licenses(piplicenses_records(runtime_distribution_names()))
    if hits:
        raise RuntimeError(
            "These runtime dependencies declare licenses that are not on the reviewed\n"
            "permissive list:\n"
            + "".join(f"  - {name}: {declared}\n" for name, declared in hits)
            + "\nIf the license is permissive and safe for binary redistribution, add it to\n"
            "PERMISSIVE_LICENSES. If it carries extra obligations, either replace the\n"
            "dependency or -- when redistribution is genuinely permitted -- document it in\n"
            "apps/licenses/bundled-native-notices.txt and add the package to\n"
            "REVIEWED_LICENSE_PACKAGES with its exact declared license string."
        )


def native_extension_packages() -> list[str]:
    """Return runtime distributions that ship compiled extension modules."""
    found = []
    for name in runtime_distribution_names():
        try:
            files = distribution(name).files or []
        except PackageNotFoundError:
            continue
        if any(str(f).endswith(NATIVE_EXTENSION_SUFFIXES) for f in files):
            found.append(name)
    return found


def verify_native_extensions_are_reviewed() -> None:
    """Fail the build when an unreviewed native wheel joins the closure.

    A wheel with compiled extensions can statically link C or Rust code that
    never shows up in Python metadata, so neither pip-licenses nor
    verify_no_unreviewed_licenses() can see it. ortools is the worst case in the
    current closure: its wheel ships no license file at all, yet its compiled
    modules link Coin-OR (EPL-2.0) and Eigen (MPL-2.0).

    This does not inspect the binaries -- it only makes sure somebody looked, at
    the version we are actually shipping. What a wheel bundles changes between
    releases, so a name-only exemption would go stale the moment the pin moves.
    """
    unreviewed = []
    for name in native_extension_packages():
        reviewed = NATIVE_REVIEWED_PACKAGES.get(canonicalize_name(name))
        if reviewed is None:
            unreviewed.append(f"{name}: never reviewed")
            continue
        reviewed_version, _ = reviewed
        installed = distribution(name).version
        if installed != reviewed_version:
            unreviewed.append(f"{name}: reviewed at {reviewed_version}, now {installed}")
    if unreviewed:
        raise RuntimeError(
            "These runtime dependencies ship compiled extensions whose bundled\n"
            "third-party code has not been reviewed at the version being shipped:\n"
            + "".join(f"  - {entry}\n" for entry in unreviewed)
            + "\nCheck what the wheel links (a PEP 770 SBOM under dist-info/sboms/, the\n"
            "upstream LICENSE, or Cargo.lock / the CMake dependency manifest), disclose\n"
            "it in apps/licenses/bundled-native-notices.txt if needed, then record the\n"
            "version and finding in NATIVE_REVIEWED_PACKAGES. See apps/licenses/README.md."
        )


def elect_license(expression: str) -> str:
    """Resolve an SPDX expression to the single license whose text we ship.

    ``AND`` 項は同時に満たす必要があるのでそれぞれ個別に選択する。``OR`` は
    選択肢なので ELECTION_PREFERENCE で 1 本に寄せる。``WITH`` は例外条項付きの
    ひとまとまりなので分割しない。
    """
    terms = []
    for term in re.split(r"\bAND\b", expression):
        options = [o.strip() for o in re.split(r"\bOR\b|/", term.strip().strip("() ")) if o.strip()]
        if not options:
            continue
        chosen = next(
            (o for preferred in ELECTION_PREFERENCE for o in options if o == preferred),
            None,
        )
        terms.append(chosen or options[0])
    return " AND ".join(terms)


def distribution_license_files(name: str) -> list[tuple[Path, Path]]:
    """Return (destination relative to licenses/<pkg>/, source path) pairs.

    Only files inside a ``*.dist-info`` / ``*.egg-info`` directory count, so a
    package's own sample data cannot masquerade as a license. Files belonging to
    a *vendored* distribution go under ``vendor/<name>/`` -- setuptools vendors
    twelve packages whose license files all happen to be called ``LICENSE``, and
    flattening them would silently drop eleven.
    """
    dist = distribution(name)
    found: list[tuple[Path, Path]] = []
    for entry in sorted(dist.files or [], key=str):
        parts = str(entry).replace("\\", "/").split("/")
        if not parts[-1].upper().startswith(LICENSE_FILE_PREFIXES):
            continue
        info = [i for i, part in enumerate(parts) if part.endswith((".dist-info", ".egg-info"))]
        if not info:
            continue
        index = info[-1]
        if index == 0:
            destination = Path(parts[-1])
        else:
            vendored = parts[index].rsplit(".dist-info", 1)[0].rsplit(".egg-info", 1)[0]
            destination = Path("vendor") / vendored / parts[-1]
        found.append((destination, Path(dist.locate_file(entry))))
    return found


def copy_third_party_license_files(dist_dir: Path) -> dict[str, list[str]]:
    """Copy every dependency's license and NOTICE files into ``licenses/``, verbatim.

    Copying upstream files byte-for-byte is what actually discharges Apache-2.0
    section 4 and the MIT/BSD notice-retention terms: the copyright lines arrive
    exactly as their authors wrote them, with no transcription step in between.
    """
    root = dist_dir / DIST_LICENSE_DIR
    if root.exists():
        shutil.rmtree(root)

    placed: dict[str, list[str]] = {}
    for name in runtime_distribution_names():
        key = canonicalize_name(name)
        for destination, source in distribution_license_files(name):
            target = root / key / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            # pip-licenses が返す名前（et_xmlfile）と依存解決で得た名前
            # （et-xmlfile）は綴りが違うことがある。正規化名で引けるようにする。
            placed.setdefault(key, []).append((Path(DIST_LICENSE_DIR) / key / destination).as_posix())
    return placed


def wheel_declared_crates(name: str) -> list[dict[str, str]]:
    """Return the crates a wheel declares about itself in its PEP 770 SBOM.

    Read from the *installed* wheel, which is the only correct source: PEP 770 is
    explicit that one package version has different SBOMs per OS and
    architecture, so the wheel that was actually installed is the one describing
    what ships. Reading it during the Windows build therefore needs no network
    and cannot pick up another platform's crate list.
    """
    dist = distribution(name)
    crates: list[dict[str, str]] = []
    for entry in sorted(dist.files or [], key=str):
        path = str(entry).replace("\\", "/")
        if "/sboms/" not in path or not path.endswith(".json"):
            continue
        # PEP 770 は 1 つの wheel に複数の SBOM を置くことを許す。
        document = json.loads(dist.locate_file(entry).read_text(encoding="utf-8"))
        for component in document.get("components", []):
            declared = [
                option.get("expression") or (option.get("license") or {}).get("id")
                for option in component.get("licenses", [])
            ]
            declared = [value for value in declared if value]
            if not declared:
                raise RuntimeError(f"{name}: SBOM component {component.get('name')} declares no license")
            crates.append(
                {
                    "name": component["name"],
                    "version": component["version"],
                    "license": " AND ".join(declared),
                    "source": f"the PEP 770 SBOM in the installed {name} wheel",
                }
            )
    return crates


def cargo_lock_crates() -> dict[str, dict]:
    """Return the committed Cargo.lock crate data, keyed by package name."""
    path = SUPPLEMENT_DIR / CARGO_LOCK_CRATES_FILE
    if not path.exists():
        raise FileNotFoundError(f"Required license file is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))["packages"]


def cargo_lock_declared_crates(name: str) -> list[dict[str, str]]:
    """Return crates for a wheel that ships no PEP 770 SBOM.

    pydantic-core is the only such extension in the closure. Its own MIT license
    covers its own code, not the third-party crates linked into the binary, so
    leaving it empty would drop ~100 crates from the disclosure entirely.

    The recorded version must match what is installed: a lockfile from a
    different release describes different crates, and silently attributing the
    wrong ones is worse than failing the build.
    """
    # pip-licenses は pydantic_core、依存解決は pydantic-core を返す。正規化して引く。
    by_key = {canonicalize_name(key): value for key, value in cargo_lock_crates().items()}
    entry = by_key.get(canonicalize_name(name))
    if entry is None:
        return []

    installed = distribution(name).version
    if entry["version"] != installed:
        raise RuntimeError(
            f"{CARGO_LOCK_CRATES_FILE} records {name} {entry['version']} but {installed} is "
            f"installed.\nRegenerate it with scripts/collect_rust_crate_notices.py."
        )

    return [
        {
            "name": crate["name"],
            "version": crate["version"],
            "license": crate["license"],
            # Cargo.lock は target / feature / 依存種別を解決しないので、実際に
            # コンパイルされるものより多い。断定しないよう出典に書き添える。
            "source": f"{entry['source']} ({CARGO_LOCK_SCOPE_NOTE})",
        }
        for crate in entry["crates"]
    ]


def bundled_crates() -> dict[str, list[dict[str, str]]]:
    """Return the Rust crates linked into each extension module.

    Two sources, in order of preference: the wheel's own PEP 770 SBOM, else the
    committed Cargo.lock data. Neither carries copyright lines, so those are not
    transcribed anywhere -- the crates' own license files ship verbatim instead.
    """
    return {
        package: wheel_declared_crates(package) or cargo_lock_declared_crates(package)
        for package in RUST_EXTENSION_PACKAGES
    }


def verify_rust_extensions_declare_their_crates(crates: dict[str, list[dict[str, str]]]) -> None:
    """Fail when a Rust extension contributes no crates to the disclosure.

    Both sources are silent on failure -- a wheel that stops shipping its SBOM,
    or a cargo-lock-crates.json entry that goes missing, would simply produce an
    empty list. Counting per package matters: an aggregate "at least one crate"
    check lets one extension's crates mask the other's absence.
    """
    empty = sorted(package for package, found in crates.items() if not found)
    if empty:
        raise RuntimeError(
            "These Rust extensions contribute no crates to the disclosure:\n"
            + "".join(f"  - {package}\n" for package in empty)
            + "\nTheir own license does not cover the crates linked into the binary. Either\n"
            "the wheel stopped shipping a PEP 770 SBOM, or apps/licenses/"
            f"{CARGO_LOCK_CRATES_FILE}\nneeds regenerating with "
            "scripts/collect_rust_crate_notices.py."
        )


def verify_bundled_component_licenses(crates: dict[str, list[dict[str, str]]]) -> None:
    """Fail the build when code inside a wheel carries an unreviewed license.

    The Python-metadata gate cannot see this: a Rust crate compiled into a .pyd
    appears only in that wheel's own declaration. Running the same permissive
    allowlist over those crates means a copyleft one appearing inside a
    dependency stops the build.
    """
    hits = {
        f"{crate['name']} {crate['version']}: {crate['license']}"
        for found in crates.values()
        for crate in found
        if not is_permissive(crate["license"])
    }
    if hits:
        raise RuntimeError(
            "These components bundled inside a wheel declare licenses that are not on\n"
            "the reviewed permissive list:\n"
            + "".join(f"  - {entry}\n" for entry in sorted(hits))
            + "\nThey are compiled into a native extension, so replacing the dependency is\n"
            "usually the only clean fix. If the license is permissive, add it to\n"
            "PERMISSIVE_LICENSES."
        )


def crate_notice_manifest() -> dict[str, list[str]]:
    """Return which license files were saved for each crate, keyed "name version".

    Paths are relative to apps/licenses/cargo/ and are content-addressed, so
    crates shipping byte-identical texts share one stored file. 43 crates ship
    the same Apache-2.0 text; storing it once is the same bytes delivered.
    """
    path = SUPPLEMENT_DIR / CARGO_CRATE_MANIFEST_FILE
    if not path.exists():
        raise FileNotFoundError(f"Required license file is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))["crates"]


def native_notice_files(component: BundledComponent) -> list[str]:
    """Return the ``native/`` relative paths holding this component's notices.

    Derived from the recorded URLs, so there is no manifest to keep in step.
    """
    return [f"{component.name}/{url.rsplit('/', 1)[-1]}" for url in component.notices]


def verify_native_component_notices_are_available(
    components: list[BundledComponent] | None = None,
) -> None:
    """Fail when a bundled native component ships no upstream notice of its own.

    Same reason as the crates: spdx/BSD-3-Clause.txt carries the literal
    "Copyright (c) <year> <owner>." placeholder, so re2's and pybind11's real
    copyright lines only reach the recipient if the upstream file is copied.
    """
    problems = []
    for component in BUNDLED_NATIVE_COMPONENTS if components is None else components:
        if component.notice_from_shared_text:
            if component.spdx not in SHARED_LICENSE_TEXTS:
                problems.append(
                    f"  - {component.name}: claims a shared license text for "
                    f"{component.spdx}, but none is registered\n"
                )
            continue
        if not component.notices:
            problems.append(f"  - {component.name}: no upstream notice URL recorded\n")
            continue
        for relative in native_notice_files(component):
            if not (SUPPLEMENT_DIR / NATIVE_NOTICE_SUBDIR / relative).is_file():
                problems.append(f"  - {component.name}: {relative} is recorded but absent\n")

    if problems:
        raise RuntimeError(
            "These bundled native components have no upstream copyright notice to ship:\n"
            + "".join(problems)
            + f"\nRegenerate apps/licenses/{NATIVE_NOTICE_SUBDIR}/ with"
            "\nscripts/collect_native_notices.py."
        )


def native_notice_paths() -> dict[str, list[str]]:
    """Map each native component to the licenses/ paths carrying its notices."""
    return {
        component.name: [
            (Path(DIST_LICENSE_DIR) / NATIVE_NOTICE_SUBDIR / relative).as_posix()
            for relative in native_notice_files(component)
        ]
        for component in BUNDLED_NATIVE_COMPONENTS
    }


def copy_native_component_notices(dist_dir: Path) -> int:
    """Copy each native component's upstream notices into ``licenses/native/``."""
    root = dist_dir / DIST_LICENSE_DIR / NATIVE_NOTICE_SUBDIR
    if root.exists():
        shutil.rmtree(root)

    copied = 0
    for component in BUNDLED_NATIVE_COMPONENTS:
        for relative in native_notice_files(component):
            source = SUPPLEMENT_DIR / NATIVE_NOTICE_SUBDIR / relative
            if not source.exists():
                raise FileNotFoundError(f"Required license file is missing: {source}")
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied += 1
    return copied


def interpreter_license_source() -> Path:
    """Return the LICENSE file of the interpreter PyInstaller is freezing.

    Read from ``sys.base_prefix`` rather than fetched from a tag: the shipped
    Windows build's LICENSE carries conditions the source tree's does not --
    Microsoft Distributable Code, bzip2 and Tcl/Tk -- and which build gets frozen
    depends on the environment. Copying the file that belongs to this very
    interpreter is both exact and offline.
    """
    # Windows は base_prefix 直下、POSIX は標準ライブラリのディレクトリに入る
    # （CPython の make install が LIBDEST に置く）。両方を見る。
    directories = [Path(sys.base_prefix), Path(sysconfig.get_paths()["stdlib"])]
    for directory in directories:
        for name in INTERPRETER_LICENSE_NAMES:
            candidate = directory / name
            if candidate.is_file():
                return candidate
    searched = ", ".join(str(directory) for directory in directories)
    raise FileNotFoundError(
        f"No {' / '.join(INTERPRETER_LICENSE_NAMES)} found for this interpreter (looked in {searched}).\n"
        "PyInstaller freezes this runtime into ChilmAI.exe, so its PSF license text has\n"
        "to ship with the distribution. See apps/licenses/README.md."
    )


def runtime_notice_files(component: RuntimeComponent) -> list[str]:
    """Return the ``runtime/`` relative paths holding this component's notices."""
    return [f"{component.name}/{url.rsplit('/', 1)[-1]}" for url in component.notices]


def verify_runtime_component_notices_are_available() -> None:
    """Fail when part of the frozen runtime has no license text to ship.

    Components marked ``notice_from_interpreter`` are covered by the
    interpreter's own LICENSE, so that file has to exist too -- it is the only
    thing carrying the PSF terms and the Microsoft Distributable Code conditions.
    """
    problems = []
    for component in runtime_components():
        if component.notice_from_interpreter:
            continue
        if not component.notices:
            problems.append(f"  - {component.name}: no upstream notice URL recorded\n")
            continue
        for relative in runtime_notice_files(component):
            if not (SUPPLEMENT_DIR / RUNTIME_NOTICE_SUBDIR / relative).is_file():
                problems.append(f"  - {component.name}: {relative} is recorded but absent\n")

    if problems:
        raise RuntimeError(
            "These parts of the frozen CPython runtime have no license text to ship:\n"
            + "".join(problems)
            + f"\nRegenerate apps/licenses/{RUNTIME_NOTICE_SUBDIR}/ with"
            "\nscripts/collect_native_notices.py."
        )

    interpreter_license_source()


def runtime_notice_paths() -> dict[str, list[str]]:
    """Map each runtime component to the licenses/ paths carrying its notices."""
    interpreter = (
        Path(DIST_LICENSE_DIR) / RUNTIME_NOTICE_SUBDIR / "CPython" / interpreter_license_source().name
    ).as_posix()
    mapped: dict[str, list[str]] = {}
    for component in runtime_components():
        if component.notice_from_interpreter:
            mapped[component.name] = [interpreter]
            continue
        mapped[component.name] = [
            (Path(DIST_LICENSE_DIR) / RUNTIME_NOTICE_SUBDIR / relative).as_posix()
            for relative in runtime_notice_files(component)
        ]
    return mapped


def copy_runtime_component_notices(dist_dir: Path) -> int:
    """Copy the frozen runtime's license texts into ``licenses/runtime/``."""
    root = dist_dir / DIST_LICENSE_DIR / RUNTIME_NOTICE_SUBDIR
    if root.exists():
        shutil.rmtree(root)

    source = interpreter_license_source()
    target = root / "CPython" / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    copied = 1

    for component in runtime_components():
        for relative in runtime_notice_files(component):
            stored = SUPPLEMENT_DIR / RUNTIME_NOTICE_SUBDIR / relative
            if not stored.exists():
                raise FileNotFoundError(f"Required license file is missing: {stored}")
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(stored, target)
            copied += 1
    return copied


def unaccounted_runtime_dlls(dist_dir: Path) -> list[str]:
    """Return DLLs sitting directly in ``_internal/`` that nothing discloses."""
    internal = dist_dir / "_internal"
    if not internal.is_dir():
        return []
    known = {component.name for component in runtime_components()}
    unaccounted = []
    for entry in sorted(internal.glob("*.dll"), key=lambda path: path.name.lower()):
        owner = next((name for pattern, name in RUNTIME_DLL_OWNERS if pattern.match(entry.name)), None)
        if owner is None or owner not in known:
            unaccounted.append(entry.name)
    return unaccounted


def verify_runtime_dlls_are_accounted_for(dist_dir: Path) -> None:
    """Fail when the built distribution ships a runtime DLL nothing discloses.

    This checks the artifact rather than the dependency graph, which is the whole
    point: every other gate starts from runtime_distribution_names(), so none of
    them can see what the interpreter contributes. Asking the built
    _internal/ directory instead means a new DLL cannot ship undisclosed.

    Only the top level is checked. DLLs a wheel brings live in that package's own
    subdirectory (numpy.libs/, pandas.libs/) and are disclosed by its license.
    """
    unaccounted = unaccounted_runtime_dlls(dist_dir)
    if unaccounted:
        raise RuntimeError(
            "These DLLs ship in _internal/ but no runtime component discloses them:\n"
            + "".join(f"  - {name}\n" for name in unaccounted)
            + "\nThe frozen interpreter changed what it bundles. Establish where each one\n"
            "comes from and under which license, then add it to runtime_components() and\n"
            "RUNTIME_DLL_OWNERS. See apps/licenses/README.md."
        )


def needs_own_copyright_notice(declared: str) -> bool:
    """Return whether relying on this license requires the crate's own notice.

    Apache-2.0 does not: its section 4 is satisfied by the LICENSE file shipped
    with the distribution plus any NOTICE the crate provides. MIT, the BSD
    variants, Zlib and the Unicode licenses all require the copyright line
    itself, which only the crate's own file carries.
    """
    return any(term.strip() != "Apache-2.0" for term in elect_license(declared).split(" AND "))


def verify_crate_notices_are_available(crates: dict[str, list[dict[str, str]]]) -> None:
    """Fail when a crate needing attribution has no license file to ship.

    The generic SPDX text is not attribution -- MIT.txt carries the literal
    "Copyright (c) <year> <copyright holders>" template. Only the crate's own
    file has the real copyright line, so the build stops if one is missing.
    """
    manifest = crate_notice_manifest()
    unknown, textless = set(), set()
    for found in crates.values():
        for crate in found:
            if not needs_own_copyright_notice(crate["license"]):
                continue
            key = f"{crate['name']} {crate['version']}"
            if key not in manifest:
                unknown.add(f"{key} ({crate['license']})")
            elif not manifest[key]:
                textless.add(f"{key} ({crate['license']})")

    problems = [f"  - {entry}: no license file recorded\n" for entry in sorted(unknown)]
    problems += [f"  - {entry}: the published crate ships none\n" for entry in sorted(textless)]
    if problems:
        raise RuntimeError(
            "These crates rely on a license that requires reproducing their copyright\n"
            "notice, but no notice ships for them:\n"
            + "".join(problems)
            + f"\nRegenerate apps/licenses/{CARGO_CRATE_MANIFEST_FILE} and the "
            f"{CARGO_CRATE_SUBDIR}/ tree with\nscripts/collect_rust_crate_notices.py. If a "
            "crate genuinely publishes no license file,\nits copyright holder has to be "
            "established by hand."
        )


def crate_notice_paths(crates: dict[str, list[dict[str, str]]]) -> dict[str, list[str]]:
    """Map "crate version" to the licenses/ paths carrying its notice."""
    manifest = crate_notice_manifest()
    mapped = {}
    for found in crates.values():
        for crate in found:
            key = f"{crate['name']} {crate['version']}"
            mapped[key] = [
                (Path(DIST_LICENSE_DIR) / CARGO_CRATE_SUBDIR / stored).as_posix()
                for stored in manifest.get(key, [])
            ]
    return mapped


def copy_crate_license_files(dist_dir: Path, crates: dict[str, list[dict[str, str]]]) -> int:
    """Copy each bundled crate's own license files into ``licenses/cargo/``."""
    manifest = crate_notice_manifest()
    root = dist_dir / DIST_LICENSE_DIR / CARGO_CRATE_SUBDIR
    if root.exists():
        shutil.rmtree(root)

    # 内容アドレスなので、同一条文を共有するクレートは同じパスを指す。
    wanted = {
        stored
        for found in crates.values()
        for crate in found
        for stored in manifest.get(f"{crate['name']} {crate['version']}", [])
    }
    for stored in sorted(wanted):
        source = SUPPLEMENT_DIR / CARGO_CRATE_SUBDIR / stored
        if not source.exists():
            raise FileNotFoundError(f"Required license file is missing: {source}")
        target = root / stored
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return len(wanted)


def license_text_source(name: str) -> Path | None:
    """Return where the text for ``name`` lives, or None if LICENSE already covers it."""
    if name in SPDX_TEXT_FILES:
        filename = SPDX_TEXT_FILES[name]
        # Apache-2.0 の全文は配布物直下の LICENSE そのもの。重複させない。
        return None if filename is None else SUPPLEMENT_DIR / SPDX_TEXT_SUBDIR / filename
    if name in SHARED_LICENSE_TEXTS:
        return SUPPLEMENT_DIR / SHARED_LICENSE_TEXTS[name]
    raise KeyError(name)


def relied_on_licenses(crates: dict[str, list[dict[str, str]]]) -> list[str]:
    """Return the licenses whose text the distribution has to carry.

    Dual-licensed components are elected down to one license, so a crate offering
    "MIT OR Apache-2.0" needs no MIT copy -- Apache-2.0 is the distribution's own
    LICENSE. ``AND`` terms are kept separately because both apply.
    """
    relied: set[str] = set()
    for found in crates.values():
        for crate in found:
            relied.update(term.strip() for term in elect_license(crate["license"]).split(" AND "))
    for component in BUNDLED_NATIVE_COMPONENTS:
        relied.update(term.strip() for term in elect_license(component.spdx).split(" AND "))
    return sorted(relied)


def verify_license_texts_are_available(crates: dict[str, list[dict[str, str]]]) -> None:
    """Fail when a license the distribution relies on has no text registered."""
    unregistered = []
    for name in relied_on_licenses(crates):
        try:
            license_text_source(name)
        except KeyError:
            unregistered.append(name)
    if unregistered:
        raise RuntimeError(
            "No license text is registered for these licenses:\n"
            + "".join(f"  - {name}\n" for name in unregistered)
            + f"\nAdd each text under apps/licenses/ (SPDX ids under {SPDX_TEXT_SUBDIR}/) and "
            "register it in SPDX_TEXT_FILES or SHARED_LICENSE_TEXTS."
        )


def copy_relied_on_license_texts(dist_dir: Path, crates: dict[str, list[dict[str, str]]]) -> list[str]:
    """Copy the license texts the bundled components rely on into ``licenses/``."""
    written = []
    for name in relied_on_licenses(crates):
        source = license_text_source(name)
        if source is None:
            continue
        if not source.exists():
            raise FileNotFoundError(f"Required license file is missing: {source}")
        relative = source.relative_to(SUPPLEMENT_DIR)
        target = dist_dir / DIST_LICENSE_DIR / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        written.append((Path(DIST_LICENSE_DIR) / relative).as_posix())
    return written


def render_notices(
    records: list[dict[str, str]],
    placed: dict[str, list[str]],
    shared: list[str],
    crate_notices: int,
    crates: dict[str, list[dict[str, str]]],
) -> str:
    """Render the human-readable index of what ships and where its license is."""
    lines = [
        "ChilmAI Windows distribution - Third-Party Notices",
        "",
        "ChilmAI itself is licensed under the Apache License 2.0; see the LICENSE and",
        "NOTICE files next to ChilmAI.exe. This file indexes the third-party code that",
        "PyInstaller bundles into ChilmAI.exe.",
        "",
        f"License texts are not reproduced here. They ship verbatim under {DIST_LICENSE_DIR}/,",
        "exactly as their authors published them, so every copyright notice is retained",
        "as written.",
        "",
        "=" * 78,
        "Python packages",
        "=" * 78,
        "",
    ]
    width = max(len(record["Name"]) for record in records)
    for record in records:
        name = record["Name"]
        lines.append(f"{name:<{width}}  {record['Version']:<14}  {record.get('License', 'UNKNOWN')}")
        if record.get("URL", "UNKNOWN") != "UNKNOWN":
            lines.append(f"{'':<{width}}  {record['URL']}")
        paths = placed.get(canonicalize_name(name), [])
        for path in paths:
            lines.append(f"{'':<{width}}  {path}")
        if not paths:
            # ortools だけが該当する。理由は Notes 節で説明している。
            lines.append(f"{'':<{width}}  (ships no license file; see Notes)")
        lines.append("")

    lines += [
        "=" * 78,
        "Code bundled inside those packages",
        "=" * 78,
        "",
        "The components below are compiled into a prebuilt wheel's native library, so",
        "they appear in no Python package metadata. Each entry gives the source it was",
        "built from, the patch the build applied before compiling it where there was",
        "one, and the upstream license and attribution files shipped for it.",
        "",
        "Corresponding source code is the listed source together with the listed patch.",
        "Where an entry carries a note that the build fetched a default branch, upstream",
        "records no revision, so that line names the source repository rather than the",
        "exact revision that was built.",
        "",
    ]
    width = max(len(component.name) for component in BUNDLED_NATIVE_COMPONENTS)
    notices = native_notice_paths()
    for component in BUNDLED_NATIVE_COMPONENTS:
        lines.append(f"{component.name:<{width}}  {component.version:<14}  {component.spdx}")
        lines.append(f"{'':<{width}}  bundled in: {component.parent}")
        lines.append(f"{'':<{width}}  source:     {component.source}")
        if component.patch:
            lines.append(f"{'':<{width}}  patch:      {component.patch}")
        for index, path in enumerate(notices.get(component.name, [])):
            label = "notices:" if index == 0 else ""
            lines.append(f"{'':<{width}}  {label:<11} {path}")
        if not component.notices:
            # ブートローダのみ。条文は SHARED_LICENSE_TEXTS 経由で配っている。
            lines.append(
                f"{'':<{width}}  notices:    {DIST_LICENSE_DIR}/" f"{SHARED_LICENSE_TEXTS[component.spdx]}"
            )
        if component.unpinned:
            # 憶測でリビジョンを書かない。決まらないことを書く。
            lines.append(
                f"{'':<{width}}  note:       the build fetched this from the default branch,"
                " so the exact"
            )
            lines.append(f"{'':<{width}}              revision is not recorded upstream")
        lines.append("")

    lines += [
        "=" * 78,
        "Rust crates compiled into the extension modules",
        "=" * 78,
        "",
        f"{crate_notices} license files from these crates ship verbatim under",
        f"{DIST_LICENSE_DIR}/{CARGO_CRATE_SUBDIR}/. Those files carry the copyright lines that",
        "MIT, BSD and Zlib require to be reproduced; the generic SPDX texts alone would",
        "only supply a template. Identical texts are stored once and shared, so several",
        "crates may point at the same path.",
        "",
        "They are all permissively licensed; the build fails if that stops being true.",
        "A crate list taken from a Cargo.lock is a conservative superset of what is",
        "actually compiled in -- r-efi, for instance, only builds for UEFI targets --",
        "because a lockfile covers every target, feature and dependency kind at once.",
        "",
    ]
    notice_paths = crate_notice_paths(crates)
    for package, found in crates.items():
        lines += [f"{package} -- {len(found)} crates", ""]
        if found:
            lines += [f"  Source of this list: {found[0]['source']}", ""]
        width = max((len(crate["name"]) for crate in found), default=1)
        for crate in sorted(found, key=lambda entry: entry["name"]):
            lines.append(f"  {crate['name']:<{width}}  {crate['version']:<12}  {crate['license']}")
            for path in notice_paths.get(f"{crate['name']} {crate['version']}", []):
                lines.append(f"  {'':<{width}}  {path}")
        lines.append("")

    lines += [
        "=" * 78,
        "CPython runtime frozen into ChilmAI.exe",
        "=" * 78,
        "",
        "PyInstaller freezes a whole CPython runtime into the distribution: the",
        "interpreter, its standard library, and the native DLLs that build links. None",
        "of it appears in Python package metadata, so it is listed from the interpreter",
        "that was actually frozen rather than from the dependency graph.",
        "",
        "CPython's own LICENSE ships below. On a Windows build that file also carries",
        "the conditions for the Microsoft Distributable Code linked into the runtime,",
        "and for bzip2 and Tcl/Tk, so those are covered by it rather than listed apart.",
        "",
    ]
    runtime = runtime_components()
    width = max(len(component.name) for component in runtime)
    runtime_notices = runtime_notice_paths()
    for component in runtime:
        lines.append(f"{component.name:<{width}}  {component.version:<14}  {component.spdx}")
        lines.append(f"{'':<{width}}  source:     {component.source}")
        for index, path in enumerate(runtime_notices.get(component.name, [])):
            label = "notices:" if index == 0 else ""
            lines.append(f"{'':<{width}}  {label:<11} {path}")
        lines.append("")

    lines += ["=" * 78, "Shared license texts", "=" * 78, ""]
    lines += [f"  {path}" for path in shared]
    lines.append("")

    path = SUPPLEMENT_DIR / SUPPLEMENT_NOTICE_FILE
    if not path.exists():
        raise FileNotFoundError(f"Required license file is missing: {path}")
    lines += ["=" * 78, "Notes", "=" * 78, "", path.read_text(encoding="utf-8").rstrip(), ""]
    return "\n".join(lines)


def verify_records_are_attributable(records: list[dict[str, str]]) -> None:
    """Fail when a package declares no license in its metadata.

    render_notices() omits UNKNOWN fields rather than printing them, which keeps
    the index readable but also means a package with no declared license would
    slip through as a name and version alone. Check it here, where the build can
    stop. Whether a license *file* exists to copy is a separate question, handled
    by verify_license_files_are_present().
    """
    undeclared = [r["Name"] for r in records if r.get("License", "UNKNOWN") == "UNKNOWN"]
    if undeclared:
        raise RuntimeError(
            "These runtime dependencies declare no license in their metadata:\n"
            + "".join(f"  - {name}\n" for name in undeclared)
            + "\nThey cannot be attributed automatically. Establish the license from\n"
            "upstream and record it in apps/licenses/bundled-native-notices.txt."
        )


def verify_license_files_are_present() -> None:
    """Fail when a dependency ships no license file for us to copy.

    This asks the installed distribution directly rather than trusting
    pip-licenses' extracted text, because what matters is whether there is a file
    to place under licenses/ -- that copy is what retains the copyright notice.
    """
    textless = [
        name
        for name in runtime_distribution_names()
        if not distribution_license_files(name) and canonicalize_name(name) not in NO_LICENSE_TEXT_PACKAGES
    ]
    if textless:
        raise RuntimeError(
            "These runtime dependencies ship no license file:\n"
            + "".join(f"  - {name}\n" for name in textless)
            + "\nOnly packages disclosed by hand may lack one. Document the package in\n"
            "apps/licenses/bundled-native-notices.txt and add it to\n"
            "NO_LICENSE_TEXT_PACKAGES, or vendor the license text."
        )


def generate_third_party_notices(dist_dir: Path) -> None:
    """Write the notices index and the verbatim license files."""
    records = piplicenses_records(runtime_distribution_names())
    verify_records_are_attributable(records)
    verify_license_files_are_present()

    crates = bundled_crates()
    # 条文を書き出す前に検査する。落ちるなら不完全な配布物を作らない方がよい。
    verify_rust_extensions_declare_their_crates(crates)
    verify_bundled_component_licenses(crates)
    verify_license_texts_are_available(crates)
    verify_crate_notices_are_available(crates)
    verify_native_component_notices_are_available()
    verify_runtime_component_notices_are_available()

    placed = copy_third_party_license_files(dist_dir)
    shared = copy_relied_on_license_texts(dist_dir, crates)
    crate_notices = copy_crate_license_files(dist_dir, crates)
    copy_native_component_notices(dist_dir)
    copy_runtime_component_notices(dist_dir)

    (dist_dir / THIRD_PARTY_NOTICES_FILE).write_text(
        render_notices(records, placed, shared, crate_notices, crates), encoding="utf-8"
    )

    # ビルド成果物の側から照合する。依存グラフ起点のチェックではこの層を拾えない。
    verify_runtime_dlls_are_accounted_for(dist_dir)


if __name__ == "__main__":
    from PyInstaller.__main__ import run

    # ビルドは数分かかるので、ライセンス検査は先に済ませて早く落とす。
    verify_no_unreviewed_licenses()
    verify_native_extensions_are_reviewed()

    run(build_pyi_args())
    dist_dir = ROOT / "dist" / "ChilmAI"
    copy_sample_dir(dist_dir)
    copy_own_license_files(dist_dir)
    generate_third_party_notices(dist_dir)
