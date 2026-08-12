# 第三者ライセンス開示

Windows ZIP は依存パッケージとネイティブコードそのものを再配布するため、条文の同梱、著作権表示の保持、ソース入手方法の告知が必要です。ソース配布のみであれば依存は利用者がインストールするので、このディレクトリは不要になります。

配布物に入るのは `apps/packager.py` の `generate_third_party_notices()` が Windows ビルド中に生成する `THIRD-PARTY-NOTICES.txt`（同梱物の一覧）と `licenses/` です。

| パス | 内容 |
| --- | --- |
| `licenses/<パッケージ>/…` | その `dist-info` にあるライセンス / NOTICE 原文 |
| `licenses/<パッケージ>/vendor/<名前>/…` | vendor されたもの（setuptools など） |
| `licenses/cargo/<hash>/…` | Rust クレート自身の条文 |
| `licenses/native/<コンポーネント>/…` | ネイティブ同梱物の上流条文・帰属表示 |
| `licenses/runtime/<コンポーネント>/…` | CPython ランタイムの条文 |
| `licenses/spdx/*.txt` | クレートが依拠する汎用条文 |
| `licenses/EPL-2.0.txt`, `licenses/MPL-2.0.txt` | ortools の同梱物用 |
| `licenses/PyInstaller-COPYING.txt` | ブートローダの例外条項を含む上流原文 |

条文は一覧に転記せず、上流のファイルをバイト単位でコピーします。SPDX の定型文は著作権行がプレースホルダなので、帰属表示は上流原文の側で配ります。

機械可読な SBOM（CycloneDX）は出していません。

## Rust 拡張のクレート

`python-calamine` と `pydantic-core` は Rust 拡張で、リンクされたクレートは Python のメタデータに現れません。取得元により精度が異なるため、一覧に出典を併記します。

| パッケージ | 取得元 | 精度 |
| --- | --- | --- |
| `python-calamine` | wheel 同梱の PEP 770 SBOM | 配布する wheel がリンクするもの |
| `pydantic-core` | 上流リリースタグの `Cargo.lock` | target・feature をまとめた保守的な superset |

PEP 770 SBOM は同じ版でも OS ごとに異なるため、ビルド中にインストール済み wheel から読みます。`Cargo.lock` は target や feature を解決しないので、実際にコンパイルされるものより広くなります（`r-efi` は UEFI ターゲット専用で配布物には入りません）。正確な解決には cargo が必要なので、superset である旨を明記してそのまま出します。

条文は各クレートの `.crate` から `LICENSE*` / `NOTICE*` / `COPYRIGHT*` を `cargo/<sha256 先頭 12 桁>/<ファイル名>` に内容アドレスで置きます。同じ Apache-2.0 や MIT の定型文を配るクレートが多く、そのまま並べると大半が重複します。クレートとファイルの対応は `cargo-crate-notices.json` が持ちます。

Apache-2.0 を選択できるクレートは配布物直下の `LICENSE` で足りますが、それ以外は自身の条文が無ければビルドを止めます。

```bash
uv run --extra package python scripts/collect_rust_crate_notices.py
```

取得対象は `Cargo.lock` 由来と SBOM 由来の union です。SBOM はプラットフォームごとに違うので、配布・テストに使う 3 プラットフォーム分を取得します。手元の wheel だけから集めると、macOS で生成したときに `windows-link` の条文が抜けて Windows ビルドで止まります。

## ネイティブ同梱物

自動で扱えないものは `bundled-native-notices.txt` と、`apps/packager.py` の `BUNDLED_NATIVE_COMPONENTS` に持ちます。

- `ortools`: wheel がライセンスファイルを同梱しておらず、同梱するコンパイル済みコードが Coin-OR（EPL-2.0）と Eigen（MPL-2.0）を静的リンクしています。
- PyInstaller ブートローダ: exe に埋め込まれます。GPL-2.0-or-later ですが Bootloader Exception があります。

上流条文は `BundledComponent.notices` の raw URL から取得し、 `native/<コンポーネント>/<ファイル名>` に原文のまま保存します。クレート側と違い件数が少ないので内容アドレスにはしていません。

```bash
uv run --extra package python scripts/collect_native_notices.py
```

条文を持たないコンポーネントは `verify_native_component_notices_are_available()` が止めます。免除は `notice_from_shared_text=True` で宣言したものだけです（PyInstaller ブートローダのみ）。ライセンス種別で判定すると、条文を持たない EPL-2.0 / MPL-2.0 のコンポーネントが素通りします。

Coin-OR の `AUTHORS` は各ファイルのヘッダを参照するよう書かれているだけで名前を持ちません。上流がそう書いているのでそのまま配ります。

### EPL-2.0 / MPL-2.0 の対応ソース

EPL-2.0 §3.1(a) と MPL-2.0 §3.2(a) が、対応するソースの入手可能化と、その方法の告知を求めます（EPL-2.0 §3.2 はソース形式で配布する場合の条件です）。そのため `BUNDLED_NATIVE_COMPONENTS` のソース URL は既定ブランチではなく、実際に取得されたタグを指します。

ortools v9.8 は Coin-OR の 5 コンポーネントを `coin-or/*` ではなく CMake 対応フォークの `Mizux/*` の `cmake/<version>` タグから取得し、`PATCH_COMMAND` でパッチを当ててからコンパイルします。Eigen も同様です。

```
FetchContent_Declare(
  CoinUtils
  GIT_REPOSITORY "https://github.com/Mizux/CoinUtils.git"
  GIT_TAG "cmake/2.11.6"
  PATCH_COMMAND git apply --ignore-whitespace ".../patches/coinutils-2.11.patch")
```

上流の `coin-or/CoinUtils` の `releases/2.11.6` は autotools で `CMakeLists.txt` を持たず、同じ構成でビルドできません。対応ソースは `GIT_REPOSITORY` と `GIT_TAG` と `PATCH_COMMAND` の 3 点で決まるので、取得元タグとパッチ URL の両方を開示します。

EPL-2.0 の "Source Code" は configuration files を含むため、ビルド設定のみの変更も対応ソースとして扱います。v9.8 では EPL-2.0 / MPL-2.0 対象（Coin-OR 5 件と Eigen）のパッチはいずれも `CMakeLists.txt` のみの変更です。 `re2` と `SCIP` は v9.8 では `PATCH_COMMAND` がコメントアウトされています。 `pybind11_protobuf` は `GIT_TAG "main"` で取得されており上流にリビジョンが残らないため、固定できない旨をそのまま注記に出します（`unpinned=True`）。

告知の方法は EPL が "in a reasonable manner on or through a medium customarily used for software exchange"、MPL が "by reasonable means in a timely manner" で、いずれも手段を特定していません。配布物には入手先の URL を記載しています。配布済みバイナリが参照するタグとパッチは消さないでください。第三者リポジトリに依存しない形にするなら、取得元タグ・パッチ・適用手順をまとめたアーカイブを自前で持つ方法があります。

### Eigen

`COPYING.README` は一部のファイルが BSD または LGPL であると述べており、ortools は `EIGEN_MPL2_ONLY` を定義していません。3.4.0 で LGPL を宣言しているのは `unsupported/Eigen/src/IterativeSolvers/` の 2 ファイル（`ConstrainedConjGrad.h`、 `IterationController.h`）で、PDLP は `unsupported/` を include しておらず、配布 wheel に `constrained_cg` / `IterationController` のシンボルもありません。

```bash
grep -rl "Lesser General Public" eigen-3.4.0/Eigen eigen-3.4.0/unsupported
strings -a ow/ortools/*/*.pyd ow/ortools/*/*/*.pyd | grep -c constrained_cg
```

どれを落とせるかの判断にはコンパイル単位の分析が必要になるので、取捨選択はせず上流の `COPYING.*` を全部配ります。

## CPython ランタイム

PyInstaller は CPython のランタイム一式（インタプリタ、標準ライブラリ、そのビルドがリンクする OpenSSL・SQLite・libffi・MSVC ランタイム）を exe にバンドルします。これらは pip のパッケージではないため Python のパッケージメタデータには現れず、`runtime_distribution_names()` を起点にする他のチェックには引っかかりません。

バンドルされる処理系はビルド環境によって異なります（CI は `actions/setup-python`、手元は uv 管理の python-build-standalone）。同じ 3.11 でもリンクされている OpenSSL の版が異なり、バージョンを固定で書くと実際に配布する zip の中身と食い違うため、`runtime_components()` が実行中の処理系からバージョンを読み取ります。

CPython 自身のライセンスは `sys.base_prefix` の `LICENSE.txt` をそのままコピーします。上流のタグから取り直さないのは、Windows バイナリに付属する `LICENSE.txt` には PSF の条文に加えて次の記載があるためです。

- リンカが各 `.exe` / `.dll` / `.pyd` に埋め込む Microsoft Distributable Code の条件（Windows バイナリの再頒布を明示的に許諾しています）
- bzip2 と Tcl/Tk の条項

Microsoft の再頒布物がどれだけ含まれてくるかは、ビルドされる処理系に依存します。`actions/setup-python` の処理系には UCRT（`ucrtbase.dll` と `api-ms-win-*.dll`）が含まれますが、uv 管理のビルドには含まれません。片方だけを載せると手元では通って CI で止まるため、両方を一覧に載せています。

この `LICENSE.txt` は OpenSSL・SQLite・libffi には触れていないため、この 3 つは上流のライセンス原文を `runtime/` に置いて配ります（`collect_native_notices.py` が取得します）。ライセンス原文は同じ系列の中では変わらないので取得元のタグは固定し、実際に同梱される版は一覧の側で処理系から読んで記載します。

### ビルド成果物との照合

`verify_runtime_dlls_are_accounted_for()` は依存グラフではなく、ビルドされた `_internal/` 直下の DLL を数えます。pip の依存関係を起点にするチェックではランタイム側の同梱物を拾えないため、「実在する DLL すべてに説明が付いているか」を成果物の側から確認し、説明の無い DLL が見つかったらビルドを止めます。

wheel に含まれる DLL は `numpy.libs/` のようなパッケージごとのサブディレクトリに入るため対象外です。そちらは各パッケージの `LICENSE` が開示しています。

## 検査

ビルドごとに走ります。CI では Windows ビルドを待たずに弾けるよう、`lint.yml` の `licenses` ジョブでも先に実行します。

| 検査 | 何を止めるか |
| --- | --- |
| `verify_no_unreviewed_licenses()` | 宣言ライセンスが許容リストに無い依存 |
| `verify_rust_extensions_declare_their_crates()` | クレート一覧が空になった Rust 拡張 |
| `verify_crate_notices_are_available()` | 著作権表示が必要なのに自身の条文が無いクレート |
| `verify_bundled_component_licenses()` | クレートに許容リスト外のライセンス |
| `verify_native_extensions_are_reviewed()` | 未確認、または確認済み版から変わったネイティブ拡張 |
| `verify_native_component_notices_are_available()` | 上流条文が無いネイティブ同梱物 |
| `verify_runtime_component_notices_are_available()` | 条文が無いランタイム構成物、条文を持たない処理系 |
| `verify_runtime_dlls_are_accounted_for()` | `_internal/` にあるのに説明が無い DLL |
| `verify_license_texts_are_available()` | 依拠するのに条文が未登録のライセンス |
| `verify_license_files_are_present()` | 条文ファイルを持たない依存（免除リスト以外） |

コピーレフトは拒否リストではなく許容リスト（`PERMISSIVE_LICENSES`）で判定します。 `EUPL-1.2` や `OSL-3.0` のように "GPL" を含まない強コピーレフトがあり、拒否リストでは漏れます。SPDX 式は `OR` を選択、`AND` を累積として解釈し、`;`（pip-licenses が Trove 分類子を連結する区切り）は判別できないため保守的に AND として扱います（`is_permissive()`）。`PERMISSIVE_LICENSES` への追加は法務判断なので、OR で許容的な選択肢と並んでいるだけのものは足さず、必要な項だけにしてください。

## 更新が必要なタイミング

- `ortools`: 同梱物の構成も版も変わります。後述の手順で確認し、 `BUNDLED_NATIVE_COMPONENTS`（取得元・パッチ・`notices`）と `bundled-native-notices.txt` を更新して `collect_native_notices.py` を再実行します。
- `pyinstaller`: ブートローダの版。`PyInstaller-COPYING.txt` も取り直します。
- `pydantic-core` / `python-calamine`: `collect_rust_crate_notices.py` を再実行します。
- ネイティブ拡張を含む依存の増減・版変更: 検査が止めるので、中身を確認して `NATIVE_REVIEWED_PACKAGES` の版を書き換えます。
- `REVIEWED_LICENSE_PACKAGES` への追加: 注記にも根拠を残します。

新しいネイティブ wheel が引っかかったら、`dist-info/sboms/*.json`（PEP 770 SBOM）、 upstream の `LICENSE`、CMake の依存マニフェストの順で何をリンクしているか探します。

## ortools の pin を上げるとき

上流のマニフェストと実バイナリの両方で確認します。マニフェストに載っていてもビルドフラグ次第でリンクされないもの（GLPK、HiGHS）があります。

1. 取得元・タグ・パッチと、上流のビルド既定値を確認します。v9.8 では `USE_COINOR=ON`（EPL-2.0）、`USE_PDLP=ON`（→ `BUILD_Eigen3`、MPL-2.0）、 `USE_GLPK=OFF`、`USE_HIGHS=OFF` です。

   ```bash
   BASE=https://raw.githubusercontent.com/google/or-tools/v9.8
   curl -sSL $BASE/cmake/dependencies/CMakeLists.txt \
     | grep -nE 'FetchContent_Declare|GIT_REPOSITORY|GIT_TAG|PATCH_COMMAND|patches/'
   curl -sSL $BASE/CMakeLists.txt | grep -nE '(option|CMAKE_DEPENDENT_OPTION)\(' \
     | grep -iE 'coinor|scip|pdlp|glpk|highs|eigen'

   # 各パッチが触っている範囲
   for p in coinutils-2.11 osi-0.108 clp-1.17.4 cgl-0.60 cbc-2.10 eigen3-3.4.0; do
     echo "--- $p"
     curl -sSL "$BASE/patches/$p.patch" | grep -E '^(\+\+\+|---) ' | sort -u
   done
   ```

   Windows wheel がこの CMake 経路でビルドされていることは `tools/release/build_delivery_win.cmd` で確認できます（`cmake -DBUILD_PYTHON=ON`）。

2. 配布対象である Windows wheel の実物を確認します。構成はプラットフォームで違い、 9.8 の Windows wheel は共有ライブラリを持たず、モジュールごとに静的リンクされた `.pyd` が並びます（`ortools.dll` も `.libs/` もありません）。Linux / macOS は単一の `.libs/libortools.*` です。

   ```bash
   V=9.8.3296
   URL=$(curl -sSL "https://pypi.org/pypi/ortools/$V/json" \
     | python -c 'import json,sys;print(next(f["url"] for f in json.load(sys.stdin)["urls"] if f["filename"].endswith("-win_amd64.whl") and "-cp311-" in f["filename"]))')
   curl -sSL "$URL" -o /tmp/ortools-win.whl && unzip -oq /tmp/ortools-win.whl -d /tmp/ow

   # CP-SAT のモジュール単体に何が入っているか
   strings -a /tmp/ow/ortools/sat/python/swig_helper*.pyd \
     | grep -cE 'CbcModel|ClpSimplex|OsiSolverInterface|CoinUtils|CglCutGenerator|SCIPcreate|Eigen'

   # 未リンクの根拠
   for sym in glp_ HiGHS; do
     printf '%s: %s\n' "$sym" "$(strings -a /tmp/ow/ortools/*/*.pyd /tmp/ow/ortools/*/*/*.pyd | grep -c "$sym")"
   done
   ```

   ChilmAI が呼び出すのは CP-SAT（`cp_model`）だけですが、その `.pyd` 自体が Coin-OR と Eigen を含みます。EPL-2.0 §3.1 と MPL-2.0 §3.2 は配布を基準にしているので、呼び出しの有無は義務に影響しません。

3. 各コンポーネントのライセンスはそのバージョンのタグで確認します。Coin-OR は 2.10 前後で EPL-1.0 から EPL-2.0 に変わっています。ライセンス確認は上流タグでよいですが、開示するソース URL は実際に取得された `Mizux/*` の `cmake/*` タグです。フォークがライセンスを変えていないことも併せて確認します。

   ```bash
   curl -sSL https://raw.githubusercontent.com/coin-or/Cbc/releases/2.10.7/LICENSE | head -1
   curl -sSL https://raw.githubusercontent.com/Mizux/Cbc/cmake/2.10.7/LICENSE | head -1
   ```
