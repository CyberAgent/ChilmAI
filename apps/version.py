from importlib import metadata
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    # tomllib は Python 3.11 で標準ライブラリ入り。3.10 は後方移植の tomli で代替する。
    import tomli as tomllib


def _resolve_version() -> str:
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if pyproject.exists():
        with pyproject.open("rb") as f:
            return tomllib.load(f)["project"]["version"]
    return metadata.version("ChilmAI")


CHILMAI_VERSION = _resolve_version()
