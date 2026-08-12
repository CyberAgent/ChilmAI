from __future__ import annotations

import os
import platform
import re
import sqlite3
import ssl
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    # tomllib は Python 3.11 で標準ライブラリ入り。3.10 は後方移植の tomli で代替する。
    import tomli as tomllib

import pytest

from apps import packager
from apps.packager import build_pyi_args


def test_project_declares_build_system_for_pyinstaller_metadata():
    pyproject = tomllib.loads((packager.ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["build-system"]["build-backend"] == "setuptools.build_meta"


def test_build_pyi_args_contains_entrypoint_and_icon():
    args = build_pyi_args()
    normalized = [arg.replace("\\", "/") for arg in args]

    assert any(arg.endswith("apps/api_launcher.py") for arg in normalized)
    assert any(arg.startswith("--icon=") and arg.endswith("assets/logo.ico") for arg in normalized)
    assert "--copy-metadata=ChilmAI" in args
    # Pinned so PyInstaller's output dir always matches copy_sample_dir()'s
    # target, regardless of the caller's cwd.
    assert f"--distpath={packager.ROOT / 'dist'}" in args


def test_build_pyi_args_resolves_apps_from_the_source_tree():
    # wheel には chilmai しか入らないので、venv に apps はインストール
    # されない。PyInstaller が api_launcher.py の import を解決できるよう、
    # リポジトリ直下を検索パスに渡す必要がある。
    args = build_pyi_args()

    assert f"--paths={packager.ROOT}" in args


def test_build_pyi_args_uses_custom_pytz_hook():
    args = build_pyi_args()
    normalized = [arg.replace("\\", "/") for arg in args]

    # Without this, PyInstaller falls back to its built-in hook-pytz.py,
    # which bundles ~600 zoneinfo files with country/city names.
    assert any(
        arg.startswith("--additional-hooks-dir=") and arg.endswith("apps/pyinstaller_hooks")
        for arg in normalized
    )


def test_build_pyi_args_contains_required_data_files():
    args = build_pyi_args()

    add_data_args = [arg.replace("\\", "/") for arg in args if arg.startswith("--add-data=")]
    assert any("apps/api/static" in arg for arg in add_data_args)
    assert any("apps/api/templates" in arg for arg in add_data_args)
    assert any("column_aliases.json" in arg for arg in add_data_args)
    assert all("data/config.json" not in arg for arg in add_data_args)
    # sample/ must not go through --add-data: PyInstaller places that under
    # _internal/, but users need it next to ChilmAI.exe (see copy_sample_dir).
    # Check the destination (not the whole arg) so an absolute source path that
    # happens to contain "sample" (e.g. a checkout dir name) can't false-fail this.
    destinations = [arg[len("--add-data=") :].rsplit(os.pathsep, 1)[-1] for arg in add_data_args]
    assert all(dest != "sample" for dest in destinations)


def test_build_pyi_args_never_packages_local_config_json(monkeypatch, tmp_path: Path):
    apps_api = tmp_path / "apps" / "api"
    (apps_api / "static").mkdir(parents=True)
    (apps_api / "templates").mkdir(parents=True)
    (tmp_path / "apps" / "api_launcher.py").write_text("", encoding="utf-8")
    (apps_api / "assets").mkdir()
    (apps_api / "assets" / "logo.ico").write_text("", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "config.json").write_text('{"children": {"child_id": "local"}}', encoding="utf-8")

    monkeypatch.setattr(packager, "ROOT", tmp_path)

    args = build_pyi_args()
    add_data_args = [arg.replace("\\", "/") for arg in args if arg.startswith("--add-data=")]
    assert all("data/config.json" not in arg for arg in add_data_args)


def test_copy_sample_dir_places_sample_next_to_dist_dir(monkeypatch, tmp_path: Path):
    sample_dir = tmp_path / "sample"
    sample_dir.mkdir()
    (sample_dir / "children_demo.csv").write_text("id\n1\n", encoding="utf-8")

    monkeypatch.setattr(packager, "ROOT", tmp_path)

    dist_dir = tmp_path / "dist" / "ChilmAI"
    dist_dir.mkdir(parents=True)

    packager.copy_sample_dir(dist_dir)

    assert (dist_dir / "sample" / "children_demo.csv").read_text(encoding="utf-8") == "id\n1\n"


def test_copy_sample_dir_is_noop_when_sample_missing(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(packager, "ROOT", tmp_path)

    dist_dir = tmp_path / "dist" / "ChilmAI"
    dist_dir.mkdir(parents=True)

    packager.copy_sample_dir(dist_dir)

    assert not (dist_dir / "sample").exists()


# ---------------------------------------------------------------------------
# 第三者ライセンスの開示
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def records() -> list[dict[str, str]]:
    # pip-licenses はサブプロセス起動なので、1 モジュールに 1 回で足りる。
    return packager.piplicenses_records(packager.runtime_distribution_names())


@pytest.fixture(scope="module")
def crates() -> dict[str, list[dict[str, str]]]:
    return packager.bundled_crates()


def all_crates(crates: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    return [crate for found in crates.values() for crate in found]


@pytest.fixture(scope="module")
def built(tmp_path_factory, records) -> Path:
    """Generate the license artefacts once into a throwaway dist dir."""
    dist_dir = tmp_path_factory.mktemp("dist")
    packager.generate_third_party_notices(dist_dir)
    return dist_dir


def test_generated_distribution_has_the_documented_layout(built: Path):
    # 一覧と条文原文の 2 つ。混ぜないのがこの構成の主旨。
    assert (built / packager.THIRD_PARTY_NOTICES_FILE).is_file()
    assert (built / packager.DIST_LICENSE_DIR).is_dir()


def test_notices_index_points_only_at_files_that_exist(built: Path):
    # 一覧に条文を載せない代わりに参照で示すので、参照先が実在しないと
    # 開示として成立しない。
    notices = (built / packager.THIRD_PARTY_NOTICES_FILE).read_text(encoding="utf-8")
    referenced = [
        token
        for line in notices.splitlines()
        for token in [line.strip()]
        if token.startswith(f"{packager.DIST_LICENSE_DIR}/")
        # 実際のパスだけを見る。散文中の <crate>/<version> のような
        # プレースホルダや、パスに続く説明文は対象外。
        and " " not in token
        and "<" not in token
    ]

    assert referenced, "the notices index references no license files at all"
    missing = [path for path in referenced if not (built / path).is_file()]
    assert not missing, f"the notices index points at files that do not exist: {missing}"


def test_notices_name_no_file_the_distribution_does_not_ship(built: Path):
    # 上の検査は行頭のパスだけを見るので、散文に埋め込まれた参照は通ってしまう。
    # 実際に、廃止した sbom.cdx.json への案内が注記に残っていた。配布物に無い
    # ものを案内すると、受領者は条文の在り処を辿れない。
    notices = (built / packager.THIRD_PARTY_NOTICES_FILE).read_text(encoding="utf-8")
    # URL の中のファイル名は配布物ではないので外す。
    prose = re.sub(r"https?://\S+", " ", notices)
    named = sorted(set(re.findall(r"[\w][\w./+-]*\.(?:txt|json)\b", prose)))

    assert named, "the notices mention no license file at all"
    missing = [name for name in named if not (built / name).is_file()]
    assert not missing, f"the notices name files the distribution does not ship: {missing}"


def test_license_files_are_copied_byte_for_byte(built: Path):
    # 著作権表示は「上流が書いたまま」で残す必要がある。転記や抽出を挟むと
    # そこが崩れるので、コピーであることを確認する。
    checked = 0
    for name in packager.runtime_distribution_names():
        key = packager.canonicalize_name(name)
        for destination, source in packager.distribution_license_files(name):
            assert (built / packager.DIST_LICENSE_DIR / key / destination).read_bytes() == (
                source.read_bytes()
            )
            checked += 1
    assert checked > 30, f"only {checked} license files were copied; expected the whole closure"


def test_vendored_license_files_are_not_flattened(built: Path):
    # setuptools は 12 個のパッケージを vendor しており、その LICENSE は
    # すべて同じファイル名。平坦化すると 11 個が黙って消える。
    vendored = sorted((built / packager.DIST_LICENSE_DIR / "setuptools" / "vendor").glob("*/LICENSE*"))

    assert len(vendored) >= 10, f"expected setuptools' vendored licenses, found {vendored}"
    assert (built / packager.DIST_LICENSE_DIR / "setuptools" / "LICENSE").is_file()


def test_license_files_are_taken_only_from_dist_info():
    # パッケージ本体のサンプルデータに LICENSE という名前のファイルが
    # 混ざっていても、条文として拾ってはいけない。
    for name in packager.runtime_distribution_names():
        for _, source in packager.distribution_license_files(name):
            parts = source.as_posix().split("/")
            assert any(part.endswith((".dist-info", ".egg-info")) for part in parts), source


def test_only_hand_disclosed_packages_may_ship_without_a_license_file():
    packager.verify_license_files_are_present()

    textless = {
        packager.canonicalize_name(name)
        for name in packager.runtime_distribution_names()
        if not packager.distribution_license_files(name)
    }
    # ortools だけが該当する。増えたら手書きの注記が必要になる。
    assert textless == packager.NO_LICENSE_TEXT_PACKAGES


def test_crate_lists_cover_every_rust_extension(crates: dict):
    found = all_crates(crates)
    names = {crate["name"] for crate in found}

    assert len(found) >= 140, f"expected the bundled crate list, found {len(found)}"
    # python-calamine 由来（PEP 770 SBOM）
    assert "calamine" in names
    # pydantic-core 由来（Cargo.lock）。以前はこちらが 0 件で、python-calamine の
    # 44 件だけで検査が通ってしまっていた。
    assert "jiter" in names
    assert "pyo3" in names


@pytest.mark.parametrize("package", packager.RUST_EXTENSION_PACKAGES)
def test_every_rust_extension_contributes_crates(crates: dict, package: str):
    # パッケージ単位で見る。合算で「1 件以上」だと、一方のクレートが他方の
    # 欠落を隠してしまう（pydantic-core が 0 件のまま通っていた原因）。
    assert crates[package], f"{package} contributes no crates"


def test_rust_extension_gate_catches_an_empty_crate_list(crates: dict):
    stripped = {**crates, "pydantic-core": []}

    with pytest.raises(RuntimeError, match="contribute no crates"):
        packager.verify_rust_extensions_declare_their_crates(stripped)


def test_cargo_lock_crates_match_the_installed_versions():
    # lockfile が別リリースのものだと、別のクレートを帰属表示することになる。
    for package, entry in packager.cargo_lock_crates().items():
        installed = packager.distribution(package).version
        assert entry["version"] == installed, (
            f"cargo-lock-crates.json records {package} {entry['version']} but {installed} is "
            "installed; rerun scripts/collect_rust_crate_notices.py"
        )
        assert entry["source"].startswith("https://")
        assert installed in entry["source"], "the source URL must pin the matching release tag"
        assert entry["crates"], f"no crates recorded for {package}"
        for crate in entry["crates"]:
            assert crate["name"] and crate["version"] and crate["license"]


def test_cargo_lock_version_mismatch_fails_loudly(monkeypatch):
    stale = {"pydantic-core": {"version": "0.0.0", "source": "https://example.invalid", "crates": []}}
    monkeypatch.setattr(packager, "cargo_lock_crates", lambda: stale)

    with pytest.raises(RuntimeError, match="but 2.41.5 is installed"):
        packager.cargo_lock_declared_crates("pydantic-core")


def test_cargo_lock_derived_crates_are_labelled_as_a_superset(crates: dict):
    # Cargo.lock は target / feature を解決しないので、実際にリンクされるものより
    # 多い。「静的リンク済み」と断定すると r-efi の説明と矛盾する。
    assert "conservative superset" in packager.CARGO_LOCK_SCOPE_NOTE
    assert all(packager.CARGO_LOCK_SCOPE_NOTE in crate["source"] for crate in crates["pydantic-core"])
    # SBOM 由来の側は wheel そのものの申告なので、この注記は付かない。
    assert all(packager.CARGO_LOCK_SCOPE_NOTE not in crate["source"] for crate in crates["python-calamine"])


def test_notices_explain_which_crate_list_is_exact(built: Path):
    notices = " ".join((built / packager.THIRD_PARTY_NOTICES_FILE).read_text(encoding="utf-8").split())

    assert "PEP 770 SBOM in the installed python-calamine wheel" in notices
    assert "conservative superset" in notices
    assert "r-efi" in notices


def test_tri_licensed_crate_is_permissive_because_we_elect_apache(crates: dict):
    # r-efi は MIT OR Apache-2.0 OR LGPL-2.1-or-later。OR は選択なので
    # Apache-2.0 を採れば LGPL の義務は生じない。全項に許容性を求める実装だと
    # ここで誤検知して、正しい一覧を載せられなくなる。
    declared = {crate["name"]: crate["license"] for crate in all_crates(crates)}

    assert declared["r-efi"] == "MIT OR Apache-2.0 OR LGPL-2.1-or-later"
    assert packager.is_permissive(declared["r-efi"])
    assert packager.elect_license(declared["r-efi"]) == "Apache-2.0"


def test_crate_list_comes_from_the_installed_wheel(crates: dict):
    # PEP 770 の SBOM は OS / アーキテクチャごとに異なる。ビルド中に
    # インストール済み wheel から読むので、他プラットフォームのクレートが
    # 混ざる余地が無い（macOS で生成した一覧を Windows 配布物に使う事故が
    # 構造的に起きない）。
    names = {crate["name"] for crate in crates["python-calamine"]}

    if sys.platform == "win32":
        assert "windows-link" in names
        assert "core-foundation-sys" not in names
    elif sys.platform == "darwin":
        assert "core-foundation-sys" in names
        assert "windows-link" not in names


def test_bundled_component_gate_rejects_a_copyleft_crate(crates: dict):
    # wheel の中に GPL のクレートが現れたらビルドを止める。Python の
    # メタデータには出ないので、この検査だけが気づける。
    poisoned = {
        **crates,
        "python-calamine": [
            *crates["python-calamine"],
            {"name": "evil-crate", "version": "1.0.0", "license": "GPL-3.0-only", "source": "x"},
        ],
    }

    with pytest.raises(RuntimeError, match="evil-crate"):
        packager.verify_bundled_component_licenses(poisoned)


def test_bundled_component_gate_passes_for_the_real_crate_lists(crates: dict):
    packager.verify_bundled_component_licenses(crates)
    packager.verify_license_texts_are_available(crates)


def test_license_text_gate_rejects_an_unregistered_license(crates: dict):
    unknown = {
        **crates,
        "python-calamine": [
            *crates["python-calamine"],
            {"name": "odd-crate", "version": "1.0.0", "license": "WTFPL-2.0", "source": "x"},
        ],
    }

    with pytest.raises(RuntimeError, match="WTFPL-2.0"):
        packager.verify_license_texts_are_available(unknown)


def test_every_relied_on_license_text_ships(built: Path, crates: dict):
    for name in packager.relied_on_licenses(crates):
        source = packager.license_text_source(name)
        if source is None:
            # Apache-2.0 は配布物直下の LICENSE が全文。
            continue
        relative = source.relative_to(packager.SUPPLEMENT_DIR)
        assert (built / packager.DIST_LICENSE_DIR / relative).is_file(), name


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("MIT OR Apache-2.0", "Apache-2.0"),
        ("Apache-2.0 OR MIT", "Apache-2.0"),
        ("Unlicense OR MIT", "MIT"),
        ("MIT/Apache-2.0", "Apache-2.0"),
        ("MIT", "MIT"),
        # AND は両方を満たす必要があるので畳まない。
        ("(Apache-2.0 OR MIT) AND BSD-3-Clause", "Apache-2.0 AND BSD-3-Clause"),
        ("(MIT OR Apache-2.0) AND Unicode-3.0", "Apache-2.0 AND Unicode-3.0"),
        # WITH は例外条項付きのひとまとまりなので分割しない。
        ("Apache-2.0 WITH LLVM-exception", "Apache-2.0 WITH LLVM-exception"),
    ],
)
def test_elect_license_prefers_apache_then_mit(expression: str, expected: str):
    assert packager.elect_license(expression) == expected


def test_apache_needs_no_extra_text_because_the_distribution_ships_it():
    assert packager.license_text_source("Apache-2.0") is None


def hand_written_notes() -> str:
    """Return the hand-written notes with wrapping collapsed.

    These assertions are about wording, not layout, so re-flowing a paragraph
    must not break them.
    """
    text = (packager.SUPPLEMENT_DIR / packager.SUPPLEMENT_NOTICE_FILE).read_text(encoding="utf-8")
    return " ".join(text.split())


def test_hand_written_notes_cover_what_the_inventory_cannot():
    notes = hand_written_notes()

    # 言い回しではなく、必ず触れていなければならない論点だけを見る。
    # ortools は wheel にライセンスファイルが無いので、理由を残す必要がある。
    assert "ships no license file" in notes
    # GPL の GLPK が未リンクであることは、監査で必ず聞かれる。
    assert "GLPK" in notes and "HiGHS" in notes
    # EPL-2.0 / MPL-2.0 で効いてくるのはソースの入手可能性。
    assert "Corresponding source code is" in notes
    # パッチが当たった状態でビルドされている事実に触れていること。
    assert "patch" in notes
    assert "Bootloader-exception" in notes


FLOATING_REFS = ("/tree/main", "/tree/master", "/tree/develop", "/blob/main", "/blob/master")


def test_bundled_native_source_urls_pin_a_release_not_a_branch():
    # ソースの入手方法を示す以上、既定ブランチを指していると後から中身が変わって
    # 「そのバイナリのソース」ではなくなる。上流自身がブランチを指していて固定
    # できないものだけ unpinned で除外し、その事実は注記に出す。
    for component in packager.BUNDLED_NATIVE_COMPONENTS:
        assert component.source.startswith("https://"), component
        if not component.unpinned:
            for floating in FLOATING_REFS:
                assert floating not in component.source, f"{component.name}: {component.source}"


def test_bundled_native_patches_are_pinned_to_the_ortools_release():
    # パッチも対応ソースの一部。ortools のタグに固定していないと、後から
    # 内容が変わって「そのバイナリに当たっていたパッチ」ではなくなる。
    patched = [c for c in packager.BUNDLED_NATIVE_COMPONENTS if c.patch]
    assert patched, "no component records a patch; check PATCH_COMMAND in the upstream CMake"

    for component in patched:
        assert component.patch.startswith("https://"), component
        for floating in FLOATING_REFS:
            assert floating not in component.patch, f"{component.name}: {component.patch}"


def test_notices_disclose_the_patches_applied_before_compiling(built: Path):
    # 表にパッチを書いても配布物に出ていなければ開示になっていない。
    notices = (built / packager.THIRD_PARTY_NOTICES_FILE).read_text(encoding="utf-8")

    for component in packager.BUNDLED_NATIVE_COMPONENTS:
        assert component.source in notices, component.name
        if component.patch:
            assert component.patch in notices, f"{component.name}: patch not disclosed"


def test_native_components_ship_their_real_copyright_lines(built: Path):
    # spdx/BSD-3-Clause.txt は "Copyright (c) <year> <owner>." というプレースホルダで、
    # 実際の著作権行の代わりにならない。配布物にその行が届いていることを見る。
    shipped = b"\n".join(path.read_bytes() for path in built.rglob("*") if path.is_file())

    for owner in (
        b"Copyright (c) 2009 The RE2 Authors",
        b"Jean-loup Gailly and Mark Adler",  # zlib
    ):
        assert owner in shipped, f"the distribution ships no real notice for {owner!r}"


def test_native_component_notices_are_copied_byte_for_byte(built: Path):
    # 宣言した原文が存在し、配布物へバイト単位でコピーされていること。
    for component in packager.BUNDLED_NATIVE_COMPONENTS:
        for relative in packager.native_notice_files(component):
            source = packager.SUPPLEMENT_DIR / packager.NATIVE_NOTICE_SUBDIR / relative
            shipped = built / packager.DIST_LICENSE_DIR / packager.NATIVE_NOTICE_SUBDIR / relative
            assert shipped.read_bytes() == source.read_bytes(), relative


def test_only_the_bootloader_is_exempt_from_shipping_its_own_notice():
    # 免除をライセンス種別で判定していたため、条文を持たない EPL-2.0 /
    # MPL-2.0 のコンポーネントが素通りしていた。免除はデータで宣言する。
    exempt = [c.name for c in packager.BUNDLED_NATIVE_COMPONENTS if c.notice_from_shared_text]

    assert exempt == ["PyInstaller bootloader"]

    fake = packager.BundledComponent(
        "ortools", "FakeEpl", "1.0", "EPL-2.0", "https://example.invalid/tree/v1.0"
    )
    with pytest.raises(RuntimeError, match="FakeEpl"):
        packager.verify_native_component_notices_are_available([*packager.BUNDLED_NATIVE_COMPONENTS, fake])


def test_weak_copyleft_components_ship_their_license_text():
    # EPL-2.0 / MPL-2.0 は SHARED_LICENSE_TEXTS 経由で条文が同梱される。
    weak = {c.spdx for c in packager.BUNDLED_NATIVE_COMPONENTS if c.spdx in ("EPL-2.0", "MPL-2.0")}
    assert weak == {"EPL-2.0", "MPL-2.0"}

    for spdx in weak:
        assert (packager.SUPPLEMENT_DIR / packager.SHARED_LICENSE_TEXTS[spdx]).is_file()


def test_ortools_notice_matches_the_pinned_version():
    # ortools を上げると同梱物の構成もバージョンも変わるので、注記と
    # BUNDLED_NATIVE_COMPONENTS を書き換え忘れたらここで落とす。
    pyproject = tomllib.loads((packager.ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pinned = [d for d in pyproject["project"]["dependencies"] if d.startswith("ortools==")]
    assert len(pinned) == 1

    version = pinned[0].split("==", 1)[1]
    notes = (packager.SUPPLEMENT_DIR / packager.SUPPLEMENT_NOTICE_FILE).read_text(encoding="utf-8")
    assert f"ortools {version}" in notes


def test_pyinstaller_notice_matches_the_pinned_version():
    # ブートローダは exe に埋め込まれるので、pin と注記がずれると
    # 「どの版のブートローダを配ったか」が説明できなくなる。
    pyproject = tomllib.loads((packager.ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_extra = pyproject["project"]["optional-dependencies"]["package"]
    pinned = [d for d in package_extra if d.startswith("pyinstaller==")]
    assert len(pinned) == 1
    version = pinned[0].split("==", 1)[1]

    entries = [e for e in packager.BUNDLED_NATIVE_COMPONENTS if e[1] == "PyInstaller bootloader"]
    assert len(entries) == 1
    assert entries[0][2] == version
    assert version in entries[0][4]

    notes = (packager.SUPPLEMENT_DIR / packager.SUPPLEMENT_NOTICE_FILE).read_text(encoding="utf-8")
    assert f"PyInstaller bootloader {version}" in notes


def test_pyinstaller_copying_text_contains_the_bootloader_exception():
    # 例外条項そのものを配らないと、GPL が及ばない根拠を示せない。
    text = (packager.SUPPLEMENT_DIR / "PyInstaller-COPYING.txt").read_text(encoding="utf-8")

    assert "Bootloader Exception" in text
    assert "unlimited permission to link or embed compiled bootloader" in text


def test_reviewed_license_packages_are_documented_in_the_notes():
    notes = (packager.SUPPLEMENT_DIR / packager.SUPPLEMENT_NOTICE_FILE).read_text(encoding="utf-8")

    for name in packager.REVIEWED_LICENSE_PACKAGES:
        assert name in notes, f"{name} is exempt from the license gate but is not disclosed"


def test_piplicenses_reports_every_requested_package(records):
    # pip-licenses は SYSTEM_PACKAGES (pip / setuptools / wheel ...) を
    # --packages で明示しても --with-system 無しでは黙って落とす。setuptools は
    # ChilmAI の直接のランタイム依存なので、静かに欠けると exe に同梱されている
    # のに一覧にも検査対象にも出てこない。
    packages = packager.runtime_distribution_names()

    assert len(records) == len(packages)
    names = {packager.canonicalize_name(record["Name"]) for record in records}
    assert packager.canonicalize_name("setuptools") in names


def test_piplicenses_raises_when_a_package_is_silently_dropped():
    with pytest.raises(RuntimeError, match="no record"):
        # 実在しないパッケージは pip-licenses が黙って無視する。
        packager.piplicenses_records(["chilmai-nonexistent-package"])


def test_license_exemption_requires_the_exact_declared_license():
    # バージョンを上げてライセンスが変わったら免除を外す。パッケージ名だけの
    # 免除だと、tqdm が GPL に変わっても素通りしてしまう。
    relicensed = [{"Name": "tqdm", "Version": "9.9.9", "License": "GNU General Public License v3"}]
    assert packager.find_unreviewed_licenses(relicensed) == [("tqdm", "GNU General Public License v3")]

    reviewed = [
        {
            "Name": "tqdm",
            "Version": "4.66.5",
            "License": packager.REVIEWED_LICENSE_PACKAGES["tqdm"],
        }
    ]
    assert packager.find_unreviewed_licenses(reviewed) == []


@pytest.mark.parametrize(
    "declared",
    [
        # 拒否リスト方式だと "GPL" を含まない強コピーレフトを取りこぼす。
        "EUPL-1.2",
        "OSL-3.0",
        "CECILL-2.1",
        "SSPL-1.0",
        "CPL-1.0",
        "QPL-1.0",
        "CC-BY-SA-4.0",
        "European Union Public Licence 1.2 (EUPL 1.2)",
        # SPDX ID は大文字小文字を区別しないので、小文字でも検知できること。
        "gpl-3.0-only",
        "GPL-3.0-only",
        # 過去に同梱から外した pyxlsb の宣言そのもの。このゲートの出発点なので固定する。
        "GNU Lesser General Public License v3 or later (LGPLv3+)",
        "Mozilla Public License 2.0 (MPL 2.0)",
        # AND は全項が binding。片方でも義務が残るなら止める。
        "Apache-2.0 AND GPL-3.0-only",
        # 選択肢がどれも許容的でない。
        "GPL-2.0-only OR AGPL-3.0-only",
        # 未宣言。
        "UNKNOWN",
        "",
    ],
)
def test_license_gate_flags_anything_not_known_permissive(declared: str):
    records = [{"Name": "mystery", "Version": "1.0", "License": declared}]

    assert packager.find_unreviewed_licenses(records) == [("mystery", declared)]


@pytest.mark.parametrize(
    "declared",
    [
        "MIT",
        "mit",
        "MIT License",
        "Apache-2.0",
        "Apache Software License",
        "BSD License",
        "3-Clause BSD License",
        "PSF-2.0",
        # pip-licenses は複数の分類子を "; " で連結する。
        "Apache Software License; BSD License",
        # SPDX 式の OR / AND も項ごとに見る。
        "Apache-2.0 OR BSD-2-Clause",
        "MIT AND Apache-2.0",
        # wheel の SBOM / Cargo.lock に現れる表記。
        "Apache-2.0 WITH LLVM-exception",
        "(MIT OR Apache-2.0) AND Unicode-3.0",
        "Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT",
        "BSD-2-Clause OR Apache-2.0 OR MIT",
        # SPDX の OR は選択。許容的な選択肢が 1 つあれば、そちらを採れる。
        # r-efi の三択と、Boost を含む二択がこれに当たる。
        "MIT OR Apache-2.0 OR LGPL-2.1-or-later",
        "Apache-2.0 OR BSL-1.0",
        "MIT OR GPL-2.0-only",
        # レガシーの "/" 区切りは OR の意味。
        "MIT/Apache-2.0",
    ],
)
def test_license_gate_accepts_the_permissive_declarations_we_actually_use(declared: str):
    records = [{"Name": "fine", "Version": "1.0", "License": declared}]

    assert packager.find_unreviewed_licenses(records) == []


def test_license_gate_passes_for_the_current_closure():
    # 許容リスト方式なので、ライセンス表記が新しくなった依存が入ると落ちる。
    # 落ちたら PERMISSIVE_LICENSES に足すか、REVIEWED_LICENSE_PACKAGES で
    # 個別に検討する（どちらも法務判断なのでレビューを通すこと）。
    packager.verify_no_unreviewed_licenses()


def test_records_without_a_declared_license_fail_the_build():
    with pytest.raises(RuntimeError, match="declare no license"):
        packager.verify_records_are_attributable(
            [{"Name": "mystery", "Version": "1.0", "License": "UNKNOWN"}]
        )


def test_every_native_wheel_in_the_closure_has_been_reviewed():
    # ネイティブ拡張は静的リンクした C / Rust コードを抱えうるが、それは
    # Python のメタデータに出ないので pip-licenses からは見えない。新しい
    # ネイティブ wheel が増えたら必ず人が確認する。
    packager.verify_native_extensions_are_reviewed()


def test_native_review_notes_do_not_cover_packages_that_left_the_closure():
    # 依存から外れたパッケージの根拠メモが残り続けると、次の監査で
    # 「まだ入っている」と誤読される。
    # 判定はランタイム依存かどうかだけで行う。wrapt / MarkupSafe などは
    # プラットフォームによって pure-Python wheel が選ばれるため、
    # native_extension_packages() と比べると OS 依存で落ちてしまう。
    present = {packager.canonicalize_name(name) for name in packager.runtime_distribution_names()}
    stale = sorted(set(packager.NATIVE_REVIEWED_PACKAGES) - present)

    assert not stale, f"NATIVE_REVIEWED_PACKAGES lists packages that are no longer dependencies: {stale}"


def test_native_review_notes_record_the_installed_versions():
    # 同梱物はバージョンごとに変わる。記録が古いままだと「確認済み」の意味が
    # 無くなるので、pin を上げたらここで落として再確認を強制する。
    for name, (reviewed_version, _) in packager.NATIVE_REVIEWED_PACKAGES.items():
        installed = packager.distribution(name).version
        assert installed == reviewed_version, (
            f"{name} is installed at {installed} but was reviewed at {reviewed_version}; "
            "re-check what the wheel bundles, update the notes, then bump the record"
        )


def test_native_review_is_invalidated_by_a_version_bump(monkeypatch):
    # 名前だけの免除では、numpy が OpenBLAS を差し替えても検査を素通りする。
    if not packager.native_extension_packages():
        pytest.skip("no native wheels in this environment's closure")
    bumped = {
        name: ("0.0.0-not-installed", reason)
        for name, (_, reason) in packager.NATIVE_REVIEWED_PACKAGES.items()
    }
    monkeypatch.setattr(packager, "NATIVE_REVIEWED_PACKAGES", bumped)

    with pytest.raises(RuntimeError, match="reviewed at 0.0.0-not-installed"):
        packager.verify_native_extensions_are_reviewed()


def test_crates_needing_attribution_ship_their_own_license_file(built: Path, crates: dict):
    # 一覧に名前を載せるだけでは MIT / BSD / Zlib の著作権表示保持は満たせない。
    # 汎用の SPDX 条文は "Copyright (c) <year> <copyright holders>" という
    # テンプレートなので、帰属表示にならない。
    packager.verify_crate_notices_are_available(crates)

    paths = packager.crate_notice_paths(crates)
    checked = 0
    for crate in all_crates(crates):
        if not packager.needs_own_copyright_notice(crate["license"]):
            continue
        stored = paths[f"{crate['name']} {crate['version']}"]
        assert stored, f"{crate['name']} {crate['version']} ships no license file of its own"
        for path in stored:
            assert (built / path).is_file()
        checked += 1
    assert checked >= 40, f"only {checked} crates were checked for attribution"


def test_crate_license_files_are_copied_byte_for_byte(built: Path, crates: dict):
    manifest = packager.crate_notice_manifest()
    stored = {
        path
        for crate in all_crates(crates)
        for path in manifest.get(f"{crate['name']} {crate['version']}", [])
    }
    for relative in sorted(stored):
        source = packager.SUPPLEMENT_DIR / packager.CARGO_CRATE_SUBDIR / relative
        shipped = built / packager.DIST_LICENSE_DIR / packager.CARGO_CRATE_SUBDIR / relative
        assert shipped.read_bytes() == source.read_bytes()
    assert len(stored) >= 70, f"only {len(stored)} crate license files were copied"


def test_a_real_copyright_line_ships_not_the_spdx_template(built: Path, crates: dict):
    # レビューで挙がった具体例。bitvec は MIT を選択するので、上流の
    # 著作権行そのものが配布物に入っていなければならない。
    # バージョンはクレート一覧から引く（pin を上げてもテストが嘘にならないように）。
    paths = packager.crate_notice_paths(crates)
    versions = {crate["name"]: crate["version"] for crate in all_crates(crates)}

    def shipped_text(crate: str) -> str:
        stored = paths[f"{crate} {versions[crate]}"]
        return "\n".join((built / path).read_text(encoding="utf-8") for path in stored)

    # Cargo.lock 由来の側
    assert "Copyright (c) 2018 myrrlyn" in shipped_text("bitvec")
    # PEP 770 SBOM 由来の側
    assert "Copyright (c) 2016 Johann Tuffe" in shipped_text("calamine")

    # 汎用条文の側はテンプレートのままである（だから足りない）。
    template = (packager.SUPPLEMENT_DIR / packager.SPDX_TEXT_SUBDIR / "MIT.txt").read_text(encoding="utf-8")
    assert "Copyright (c) <year> <copyright holders>" in template


def test_attribution_gate_fires_when_a_crate_notice_is_missing(crates: dict, monkeypatch):
    monkeypatch.setattr(packager, "crate_notice_manifest", dict)

    with pytest.raises(RuntimeError, match="no license file recorded"):
        packager.verify_crate_notices_are_available(crates)


def test_attribution_gate_fires_when_the_crate_ships_no_notice(crates: dict, monkeypatch):
    emptied = {key: [] for key in packager.crate_notice_manifest()}
    monkeypatch.setattr(packager, "crate_notice_manifest", lambda: emptied)

    with pytest.raises(RuntimeError, match="the published crate ships none"):
        packager.verify_crate_notices_are_available(crates)


@pytest.mark.parametrize(
    ("declared", "expected"),
    [
        # Apache-2.0 に寄せられるなら、配布物直下の LICENSE で足りる。
        ("MIT OR Apache-2.0", False),
        ("Apache-2.0", False),
        ("MIT OR Apache-2.0 OR LGPL-2.1-or-later", False),
        # 選択の余地が無いか、AND で他の条件が残るものは自前の表示が必要。
        ("MIT", True),
        ("Zlib", True),
        ("Unicode-3.0", True),
        ("(MIT OR Apache-2.0) AND Unicode-DFS-2016", True),
        ("Apache-2.0 WITH LLVM-exception", True),
    ],
)
def test_needs_own_copyright_notice(declared: str, expected: bool):
    assert packager.needs_own_copyright_notice(declared) is expected


def test_crate_notice_manifest_matches_the_files_on_disk():
    # マニフェストと実ファイルがずれると、コピー時に FileNotFoundError になる。
    manifest = packager.crate_notice_manifest()
    assert manifest, "no crate license files are recorded"

    root = packager.SUPPLEMENT_DIR / packager.CARGO_CRATE_SUBDIR
    for key, relatives in manifest.items():
        for relative in relatives:
            assert (root / relative).is_file(), f"{key}: {relative} is recorded but absent"

    # 内容アドレスなので、置いてあるファイルは全てどこかから参照されている。
    referenced = {root / relative for relatives in manifest.values() for relative in relatives}
    on_disk = {path for path in root.rglob("*") if path.is_file()}
    assert on_disk == referenced


# ---------------------------------------------------------------------------
# CPython ランタイム
#
# 他のチェックはすべて runtime_distribution_names() を起点にするので、
# インタプリタ本体と、そこに含まれてくる OpenSSL / SQLite / libffi /
# MSVC ランタイムはそちらには引っかからない。
# ---------------------------------------------------------------------------


def test_runtime_components_are_read_from_the_frozen_interpreter():
    # 固定値だと、CI（actions/setup-python）と手元（uv 管理ビルド）で
    # 実際にリンクされる版が違ったときに配布物と食い違う。
    components = {component.name: component for component in packager.runtime_components()}

    assert components["CPython"].version == platform.python_version()
    assert components["OpenSSL"].version in ssl.OPENSSL_VERSION
    assert components["SQLite"].version == sqlite3.sqlite_version


def test_the_frozen_interpreter_ships_a_license_we_can_copy():
    # PSF 条文はこのファイルでしか渡らない。Windows ビルドではさらに
    # Microsoft Distributable Code の条件も同じファイルが持つ。
    source = packager.interpreter_license_source()

    assert source.is_file()
    assert source.read_bytes().strip()


def test_runtime_notices_ship_for_everything_not_covered_by_the_interpreter(built: Path):
    packager.verify_runtime_component_notices_are_available()

    paths = packager.runtime_notice_paths()
    for component in packager.runtime_components():
        stored = paths[component.name]
        assert stored, f"{component.name} has no license text to ship"
        for relative in stored:
            assert (built / relative).is_file(), f"{component.name}: {relative} was not copied"


def test_the_interpreter_license_carries_the_psf_terms(built: Path):
    # 一覧に名前を載せるだけでは PSF の条文も著作権表示も渡らない。
    name = packager.interpreter_license_source().name
    text = (
        built / packager.DIST_LICENSE_DIR / packager.RUNTIME_NOTICE_SUBDIR / "CPython" / name
    ).read_text(encoding="utf-8", errors="replace")

    assert "PYTHON SOFTWARE FOUNDATION LICENSE" in text


def test_the_notices_disclose_the_frozen_runtime(built: Path):
    text = (built / packager.THIRD_PARTY_NOTICES_FILE).read_text(encoding="utf-8")

    for needle in ("CPython runtime frozen into ChilmAI.exe", "Python-2.0", "OpenSSL"):
        assert needle in text


@pytest.mark.parametrize(
    ("filename", "owner"),
    [
        ("python311.dll", "CPython"),
        ("python3.dll", "CPython"),
        ("libssl-3-x64.dll", "OpenSSL"),
        ("libcrypto-3-x64.dll", "OpenSSL"),
        ("libffi-8.dll", "libffi"),
        ("sqlite3.dll", "SQLite"),
        ("VCRUNTIME140.dll", "Microsoft Visual C++ runtime"),
        ("VCRUNTIME140_1.dll", "Microsoft Visual C++ runtime"),
        ("MSVCP140.dll", "Microsoft Visual C++ runtime"),
        # actions/setup-python の処理系には UCRT が含まれる。uv 管理のビルドには
        # 含まれないので、この対応表は手元の構成より広く持つ。
        ("ucrtbase.dll", "Microsoft Universal C Runtime"),
        ("api-ms-win-crt-runtime-l1-1-0.dll", "Microsoft Universal C Runtime"),
        ("api-ms-win-core-file-l1-2-0.dll", "Microsoft Universal C Runtime"),
        # 出所が説明できないものは、どの構成物にも紐づかない。
        ("libcurl.dll", None),
        ("mystery-vendor.dll", None),
    ],
)
def test_runtime_dll_owners_cover_what_the_interpreter_ships(filename: str, owner: str | None):
    # 対応表そのものを見る。どの構成物が実際に一覧へ出るかは処理系によって
    # 変わる（MSVC 系は MSC ビルドのみ）ので、そこは次のテストで見る。
    matched = next((name for pattern, name in packager.RUNTIME_DLL_OWNERS if pattern.match(filename)), None)

    assert matched == owner


def test_dlls_are_accounted_for_only_when_their_component_is_disclosed(tmp_path: Path):
    # 対応表に載っていても、その構成物が一覧に出ていなければ開示になっていない。
    # 照合は「実在する DLL に、配る一覧側の裏付けがあるか」で行う。
    internal = tmp_path / "_internal"
    internal.mkdir()
    disclosed = {component.name for component in packager.runtime_components()}
    for filename, owner in (
        ("python311.dll", "CPython"),
        ("libssl-3-x64.dll", "OpenSSL"),
        ("sqlite3.dll", "SQLite"),
        ("libffi-8.dll", "libffi"),
        ("VCRUNTIME140.dll", "Microsoft Visual C++ runtime"),
        ("ucrtbase.dll", "Microsoft Universal C Runtime"),
    ):
        if owner in disclosed:
            (internal / filename).write_bytes(b"")

    assert packager.unaccounted_runtime_dlls(tmp_path) == []


def test_an_undisclosed_runtime_dll_fails_the_build(tmp_path: Path):
    # pip の依存関係を起点にするチェックではこの層を拾えない。ビルド成果物の
    # 側から照合して、説明の無い DLL が見つかったら止める。
    internal = tmp_path / "_internal"
    internal.mkdir()
    (internal / "python311.dll").write_bytes(b"")
    (internal / "some-new-vendor.dll").write_bytes(b"")

    with pytest.raises(RuntimeError, match="some-new-vendor.dll"):
        packager.verify_runtime_dlls_are_accounted_for(tmp_path)


def test_wheel_provided_dlls_are_not_the_runtime_check_s_business(tmp_path: Path):
    # numpy.libs/ や pandas.libs/ の DLL は各パッケージの LICENSE が開示している。
    # ここで拾うと二重に止まる。
    vendored = tmp_path / "_internal" / "numpy.libs"
    vendored.mkdir(parents=True)
    (vendored / "libopenblas64_-deadbeef.dll").write_bytes(b"")

    assert packager.unaccounted_runtime_dlls(tmp_path) == []
