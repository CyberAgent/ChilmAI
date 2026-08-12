"""Save the license files of the Rust crates linked into our extension modules.

    uv run --extra package python scripts/collect_rust_crate_notices.py

Fetches each crate's published ``.crate`` tarball and saves its ``LICENSE`` /
``NOTICE`` / ``COPYRIGHT`` files **verbatim** -- no parsing, no copyright-line
extraction. Storage is content-addressed (apps/licenses/cargo/<sha256[:12]>/)
and cargo-crate-notices.json records which crate maps to which file. Why the
generic SPDX texts cannot stand in for these, and why the texts are deduplicated,
are in apps/licenses/README.md.

It also records pydantic-core's crate list, because that wheel ships no PEP 770
SBOM and its crates would otherwise be absent from the inventory entirely. That
list comes from the upstream Cargo.lock, which is a *conservative superset* of
what gets compiled in -- see CARGO_LOCK_SOURCES.

Which crates get fetched
------------------------
The union of:

  * pydantic-core's Cargo.lock (platform-independent).
  * python-calamine's PEP 770 SBOM, for every platform we build or test on.
    A wheel's SBOM is per-platform, so generating from only the local wheel
    would miss windows-link on a macOS run and the build would then fail on
    Windows. Fetching the union keeps one regeneration valid everywhere;
    a stored file for a crate we do not ship is harmless.

Failures are fatal: nothing is written unless every crate resolved. A partial
run would silently drop attribution.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LICENSE_DIR = ROOT / "apps" / "licenses"
CARGO_DIR = LICENSE_DIR / "cargo"
CRATE_MANIFEST = LICENSE_DIR / "cargo-crate-notices.json"
CARGO_LOCK_OUTPUT = LICENSE_DIR / "cargo-lock-crates.json"

USER_AGENT = "ChilmAI-license-audit (https://github.com/CyberAgent/ChilmAI)"

# SBOM を同梱していない Rust 拡張。上流のリリースタグの Cargo.lock を見る。
CARGO_LOCK_SOURCES = {
    "pydantic-core": "https://raw.githubusercontent.com/pydantic/pydantic-core/v{version}/Cargo.lock",
}

# SBOM を同梱している Rust 拡張と、条文を集めるべきプラットフォーム。
# 配布は Windows だけだが、テストは Linux / macOS でも SBOM を組み立てるので
# そこで条文が欠けないように union を取る。
#   win_amd64            リリースする Windows 配布物
#   macosx_11_0_arm64    maintainer の手元
#   manylinux_2_17_x86_64  CI の ubuntu-latest
# manylinux は "manylinux_2_17_x86_64.manylinux2014_x86_64" のような複合タグに
# なるので、末尾一致ではなく部分一致で探す。
SBOM_PACKAGES = ("python-calamine",)
SBOM_PLATFORM_TAGS = ("win_amd64", "macosx_11_0_arm64", "manylinux_2_17_x86_64")
SBOM_PYTHON_TAG = "cp311"

LICENSE_FILE_PREFIXES = ("LICENSE", "LICENCE", "NOTICE", "COPYRIGHT")
# 条文は cargo/<sha256 先頭 PREFIX_LENGTH 桁>/<ファイル名> に置く。80 件強に対して
# 48 bit なので衝突はまず起きないが、起きたら検出して落とす（下記）。
PREFIX_LENGTH = 12
LOCK_ENTRY = re.compile(r'\[\[package\]\]\nname = "([^"]+)"\nversion = "([^"]+)"')


class ResolutionError(Exception):
    """Raised when a crate list, license or license file cannot be resolved."""


def fetch(url: str, *, attempts: int = 3) -> bytes:
    """Fetch ``url``, retrying so a blip does not look like missing attribution."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            # 4xx は再試行しても変わらない。名前かバージョンが違う。
            if error.code < 500 or attempt == attempts:
                raise
        except Exception:
            if attempt == attempts:
                raise
        time.sleep(2 * attempt)
    raise AssertionError("unreachable")


def installed_version(package: str) -> str:
    try:
        return distribution(package).version
    except PackageNotFoundError as error:
        raise ResolutionError(f"{package} is not installed; run `uv sync --extra package` first") from error


def cargo_lock_crates(package: str, version: str) -> list[dict[str, str]]:
    """Return the crate list from the upstream Cargo.lock, licensed via crates.io."""
    lock = fetch(CARGO_LOCK_SOURCES[package].format(version=version)).decode("utf-8")
    crates = []
    for name, crate_version in sorted(set(LOCK_ENTRY.findall(lock))):
        if name == package:
            continue
        payload = json.loads(fetch(f"https://crates.io/api/v1/crates/{name}/{crate_version}"))
        expression = payload["version"].get("license")
        if not expression:
            # 空欄のまま出すと、検査が「宣言なし」を見逃せなくなる。
            raise ResolutionError(f"{name} {crate_version} declares no license on crates.io")
        crates.append({"name": name, "version": crate_version, "license": expression})
    if not crates:
        raise ResolutionError(f"parsed no packages out of {package}'s Cargo.lock")
    return crates


def sbom_crates(package: str, version: str) -> set[tuple[str, str]]:
    """Return every (crate, version) any platform's wheel declares in its SBOM."""
    payload = json.loads(fetch(f"https://pypi.org/pypi/{package}/{version}/json"))
    found: set[tuple[str, str]] = set()
    for platform_tag in SBOM_PLATFORM_TAGS:
        matches = [
            entry
            for entry in payload["urls"]
            if f"-{platform_tag}" in entry["filename"] and f"-{SBOM_PYTHON_TAG}-" in entry["filename"]
        ]
        if not matches:
            raise ResolutionError(
                f"{package} {version} publishes no {SBOM_PYTHON_TAG}/{platform_tag} wheel; "
                "check SBOM_PLATFORM_TAGS against what upstream builds"
            )
        archive = zipfile.ZipFile(io.BytesIO(fetch(matches[0]["url"])))
        names = [n for n in archive.namelist() if "/sboms/" in n and n.endswith(".json")]
        if not names:
            raise ResolutionError(f"{matches[0]['filename']} ships no PEP 770 SBOM")
        for name in names:
            for component in json.loads(archive.read(name)).get("components", []):
                found.add((component["name"], component["version"]))
    return found


def crate_license_files(name: str, version: str) -> dict[str, bytes]:
    """Return the crate's license files, byte for byte as published."""
    url = f"https://static.crates.io/crates/{name}/{name}-{version}.crate"
    blob = fetch(url)
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
        for member in archive.getmembers():
            base = member.name.rsplit("/", 1)[-1]
            if not member.isfile() or not base.upper().startswith(LICENSE_FILE_PREFIXES):
                continue
            handle = archive.extractfile(member)
            if handle is None:
                continue
            files[base] = handle.read()
    return files


def main() -> int:
    try:
        # 1. SBOM を持たないパッケージのクレート一覧（+ ライセンス式）。
        lock_data = {}
        wanted: set[tuple[str, str]] = set()
        for package in CARGO_LOCK_SOURCES:
            version = installed_version(package)
            crates = cargo_lock_crates(package, version)
            lock_data[package] = {
                "version": version,
                "source": CARGO_LOCK_SOURCES[package].format(version=version),
                "crates": crates,
            }
            wanted.update((crate["name"], crate["version"]) for crate in crates)
            print(f"{package} {version}: {len(crates)} crates from Cargo.lock", file=sys.stderr)

        # 2. SBOM を持つパッケージは、全プラットフォーム分の union を取る。
        for package in SBOM_PACKAGES:
            version = installed_version(package)
            crates = sbom_crates(package, version)
            wanted.update(crates)
            print(f"{package} {version}: {len(crates)} crates from SBOMs", file=sys.stderr)

        # 3. 各クレートの条文を原文のまま集める。
        print(f"fetching license files for {len(wanted)} crates...", file=sys.stderr)
        collected: dict[tuple[str, str], dict[str, bytes]] = {}
        for name, version in sorted(wanted):
            collected[(name, version)] = crate_license_files(name, version)
    except (ResolutionError, OSError) as error:
        # 途中まで書いたものを残さない。1 件でも解決できなければ何もしない。
        print(f"\nCould not resolve: {error}", file=sys.stderr)
        print("Nothing was written; re-run once the source is reachable.", file=sys.stderr)
        return 1

    # ここまで来たら全件揃っている。配置先を先に決め切ってから書き出す。
    manifest: dict[str, list[str]] = {}
    layout: dict[str, bytes] = {}
    for (name, version), files in sorted(collected.items()):
        stored = []
        for base, content in sorted(files.items()):
            # 内容アドレスで重ねる。同一バイト列は 1 つだけ置く。
            digest = hashlib.sha256(content).hexdigest()[:PREFIX_LENGTH]
            relative = f"{digest}/{base}"
            # 短縮 prefix なので衝突は起こり得る。黙って上書きすると、そのパスを
            # 指す別のクレートに他人の条文を配ってしまう。書く前に止める。
            if layout.setdefault(relative, content) != content:
                print(
                    f"\nsha256[:{PREFIX_LENGTH}] collision on {relative} ({name} {version}).",
                    file=sys.stderr,
                )
                print("Nothing was written; raise PREFIX_LENGTH and re-run.", file=sys.stderr)
                return 1
            stored.append(relative)
        manifest[f"{name} {version}"] = stored

    if CARGO_DIR.exists():
        shutil.rmtree(CARGO_DIR)
    for relative, content in sorted(layout.items()):
        path = CARGO_DIR / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    CRATE_MANIFEST.write_text(
        json.dumps(
            {
                "_comment": (
                    "Generated by scripts/collect_rust_crate_notices.py. Maps each crate to "
                    "the license files saved verbatim under cargo/<sha256[:12]>/. Storage is "
                    "content-addressed, so crates shipping identical texts share one file. An "
                    "empty list means the published .crate ships no license file of its own."
                ),
                "crates": manifest,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    CARGO_LOCK_OUTPUT.write_text(
        json.dumps(
            {
                "_comment": (
                    "Generated by scripts/collect_rust_crate_notices.py. A Cargo.lock records "
                    "the union of all targets, features and dependency kinds, so each crate "
                    "list is a conservative superset of what is compiled into the shipped wheel."
                ),
                "packages": lock_data,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    textless = [key for key, files in manifest.items() if not files]
    referenced = sum(len(files) for files in manifest.values())
    on_disk = len({path for files in manifest.values() for path in files})
    print(
        f"\nwrote {on_disk} unique license files for {len(manifest)} crates "
        f"({referenced} references, {referenced - on_disk} deduplicated)",
        file=sys.stderr,
    )
    if textless:
        print(f"{len(textless)} crates ship no license file: {textless}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
