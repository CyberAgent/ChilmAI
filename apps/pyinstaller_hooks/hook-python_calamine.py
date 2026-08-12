"""Bundle python-calamine's compiled extension into frozen builds.

pandas loads the calamine reader lazily via ``engine="calamine"`` (a string),
so PyInstaller's static import graph never sees ``import python_calamine`` and
would otherwise omit the package and its Rust extension (.pyd). collect_all
pulls in the submodules, the compiled binary, and metadata so .xlsb/.xlsx
reading keeps working in ChilmAI.exe.
"""

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("python_calamine")
