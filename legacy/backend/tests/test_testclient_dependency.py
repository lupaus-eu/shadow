import subprocess
import sys


def test_fastapi_testclient_import_has_no_starlette_deprecation_warning() -> None:
    script = """
import importlib
import warnings

from starlette.exceptions import StarletteDeprecationWarning

warnings.simplefilter("error", StarletteDeprecationWarning)
importlib.import_module("fastapi.testclient")
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
