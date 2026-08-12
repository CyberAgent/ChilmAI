"""Save the upstream license and attribution files of the bundled native components.

    uv run --extra package python scripts/collect_native_notices.py

Files land verbatim in apps/licenses/native/<component>/<basename>, which is
derived from BundledComponent.notices -- there is no manifest to keep in step.
Why the generic SPDX texts cannot stand in for these is in
apps/licenses/README.md.

Nothing is written unless every URL resolves: a partially updated tree would
silently drop a component's attribution.
"""

from __future__ import annotations

import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.packager import (  # noqa: E402
    BUNDLED_NATIVE_COMPONENTS,
    NATIVE_NOTICE_SUBDIR,
    RUNTIME_NOTICE_SUBDIR,
    SUPPLEMENT_DIR,
    native_notice_files,
    runtime_components,
    runtime_notice_files,
)

USER_AGENT = "ChilmAI-license-audit (https://github.com/CyberAgent/ChilmAI)"
NATIVE_DIR = SUPPLEMENT_DIR / NATIVE_NOTICE_SUBDIR
RUNTIME_DIR = SUPPLEMENT_DIR / RUNTIME_NOTICE_SUBDIR


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def collect(components, notice_files) -> dict[str, bytes]:
    """Fetch every recorded notice for ``components`` into {relative path: bytes}."""
    collected: dict[str, bytes] = {}
    for component in components:
        for relative, url in zip(notice_files(component), component.notices):
            content = fetch(url)
            if not content.strip():
                raise ValueError(f"{url}: empty")
            collected[relative] = content
        if component.notices:
            print(f"{component.name}: {len(component.notices)} files", file=sys.stderr)
    return collected


def main() -> int:
    try:
        native = collect(BUNDLED_NATIVE_COMPONENTS, native_notice_files)
        # CPython 自身の LICENSE はバンドルする処理系から直接コピーするので取得しない
        # （apps/packager.py の interpreter_license_source）。
        runtime = collect(runtime_components(), runtime_notice_files)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as error:
        print(f"\nCould not resolve: {error}", file=sys.stderr)
        print("Nothing was written; re-run once the source is reachable.", file=sys.stderr)
        return 1

    for directory, collected in ((NATIVE_DIR, native), (RUNTIME_DIR, runtime)):
        if directory.exists():
            shutil.rmtree(directory)
        for relative, content in sorted(collected.items()):
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

    written = len(native) + len(runtime)
    total = sum(len(content) for content in (*native.values(), *runtime.values()))
    print(f"\nwrote {written} files ({total / 1024:.0f} KB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
