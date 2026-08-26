from importlib import metadata
from pathlib import Path

import tomllib


def _resolve_version() -> str:
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if pyproject.exists():
        with pyproject.open("rb") as f:
            return tomllib.load(f)["project"]["version"]
    return metadata.version("ChilmAI")


CHILMAI_VERSION = _resolve_version()
