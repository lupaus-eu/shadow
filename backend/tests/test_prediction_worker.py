import subprocess
import sys


def test_standalone_worker_registers_user_foreign_key_target() -> None:
    script = """
from app.api.v1.predictions.worker import PredictionRequest
from app.core.models import Base

foreign_key = next(
    iter(PredictionRequest.__table__.c.submitted_by.foreign_keys)
)
assert foreign_key.column is Base.metadata.tables["users"].c.user_id
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
