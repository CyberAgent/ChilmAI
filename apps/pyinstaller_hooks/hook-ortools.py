"""Bundle the shared libraries of the ortools wheel into frozen builds.

ortools 9.15 の Windows wheel は ortools/.libs/ に共有 DLL（ortools.dll、
libscip.dll、highs.dll ほか）を置き、ortools/__init__.py が実行時に
os.path.dirname(__file__)/.libs から ctypes.WinDLL でプリロードする。
DLL が見つからない場合は黙ってスキップするため、PyInstaller が .libs を
集めないと拡張モジュール（cp_model_helper など）の import が
"DLL load failed" で落ちる。collect_dynamic_libs はパッケージ相対の
配置（_internal/ortools/.libs/）を保ったまま DLL を収集するので、
凍結後も同じ探索パスで解決できる。
"""

from PyInstaller.utils.hooks import collect_dynamic_libs

binaries = collect_dynamic_libs("ortools")
