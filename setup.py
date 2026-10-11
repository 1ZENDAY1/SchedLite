import sys
import os
from cx_Freeze import setup, Executable

PYTHON_INSTALL_DIR = os.path.dirname(os.path.dirname(os.__file__))

include_files = [
    ("schedule.db", "schedule.db"),
    (os.path.join(PYTHON_INSTALL_DIR, "DLLs", "tcl86t.dll"), "tcl86t.dll"),
    (os.path.join(PYTHON_INSTALL_DIR, "DLLs", "tk86t.dll"), "tk86t.dll"),
]

build_exe_options = {
    "packages": ["tkinter", "sqlite3", "json", "datetime"],
    "include_files": include_files,
    "excludes": ["test", "unittest", "email", "http", "xml"],
}

base = None
if sys.platform == "win32":
    base = "Win32GUI"

setup(
    name="SchedLite",
    version="1.0",
    description="Электронное расписание школы",
    options={"build_exe": build_exe_options},
    executables=[
        Executable("main.py", base=base, target_name="SchedLite_v2.exe", icon="icon.ico"),
        Executable("mainversion2.py", base=base, target_name="SchedLite.exe", icon="icon.ico"),
    ],
)
