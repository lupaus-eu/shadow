# pyright: reportPrivateUsage=false

import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import date
from multiprocessing.connection import Connection
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.api.v1.predictions.snapshots import (
    PredictionCalculation,
    PredictionInputSnapshot,
    PredictionTargetSnapshot,
    SnapshotFeaturePeriod,
)
from app.api.v1.predictions.worker import (
    ChildTarget,
    PredictionWorker,
    _child_calculate,
    use_private_temporary_directory,
)

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="uses Linux /proc process state"
)


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


def _sleeping_grandchild() -> subprocess.Popen[bytes]:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


def _report_isolation(_: str, sender: Connection, temporary_directory: str) -> None:
    os.setsid()
    use_private_temporary_directory(temporary_directory)
    handle, path = tempfile.mkstemp()
    os.close(handle)
    sender.send(
        (
            "completed",
            json.dumps(
                {
                    "sessionLeader": os.getsid(0) == os.getpid(),
                    "processGroup": os.getpgid(0),
                    "pid": os.getpid(),
                    "tmpdir": os.environ["TMPDIR"],
                    "mplconfigdir": os.environ["MPLCONFIGDIR"],
                    "tempfile": path,
                }
            ),
        )
    )
    sender.close()


def _sleep_before_setsid(_: str, sender: Connection, temporary_directory: str) -> None:
    del sender, temporary_directory
    time.sleep(60)
    os.setsid()


def _block_with_grandchild(
    pid_path: str, sender: Connection, temporary_directory: str
) -> None:
    del sender
    os.setsid()
    Path(temporary_directory, "model-output.csv").write_text("partial")
    Path(pid_path).write_text(str(_sleeping_grandchild().pid))
    time.sleep(60)


def _crash_with_grandchild(
    pid_path: str, sender: Connection, temporary_directory: str
) -> None:
    del sender
    os.setsid()
    Path(temporary_directory, "model-output.csv").write_text("partial")
    Path(pid_path).write_text(str(_sleeping_grandchild().pid))
    raise RuntimeError("deliberate child crash with a running grandchild")


def _long_prophet_fit(_: str, sender: Connection, temporary_directory: str) -> None:
    del sender
    os.setsid()
    use_private_temporary_directory(temporary_directory)
    import pandas as pd  # pyright: ignore[reportMissingTypeStubs]
    from prophet import Prophet

    frame = pd.DataFrame(
        {
            "ds": pd.date_range(  # pyright: ignore[reportUnknownMemberType]
                "2020-01-01", periods=200, freq="D"
            ),
            "y": [float(index % 7 + index / 10) for index in range(200)],
        }
    )
    # MCMC keeps CmdStan running long enough to stop it mid-fit.
    Prophet(mcmc_samples=200_000).fit(frame, seed=41)


def _process_running(pid: int) -> bool:
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (FileNotFoundError, ProcessLookupError):
        return False
    return state not in {"Z", "X"}


def _group_members(process_group_id: int) -> set[int]:
    members: set[int] = set()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
        except (FileNotFoundError, ProcessLookupError):
            continue
        if int(fields[2]) == process_group_id and fields[0] not in {"Z", "X"}:
            members.add(int(entry.name))
    return members


def _group_runs(process_group_id: int, executable_name: str) -> bool:
    # cmdline, not comm: comm is truncated to 15 characters.
    for pid in _group_members(process_group_id):
        try:
            command = Path(f"/proc/{pid}/cmdline").read_bytes()
        except (FileNotFoundError, ProcessLookupError):
            continue
        if Path(os.fsdecode(command.split(b"\0", 1)[0])).name == executable_name:
            return True
    return False


def _wait_until(condition: Callable[[], bool], timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


def _worker(child_target: ChildTarget) -> PredictionWorker:
    return PredictionWorker(create_engine("sqlite://"), child_target=child_target)


def _single_kind_snapshot() -> PredictionInputSnapshot:
    return PredictionInputSnapshot(
        organisationInternalId=1,
        organisationKey="organisation",
        predictionKey="prediction",
        name="Child entry",
        creatorUserId=1,
        cutoffMode="asOfStart",
        confidenceLevel=80,
        startDate=date(2025, 1, 1),
        endDate=date(2025, 2, 1),
        modelConfiguration={},
        modelKinds=["naive"],
        targets=[
            PredictionTargetSnapshot(
                scenarioInternalId=1,
                scenarioKey="scenario",
                scenarioName="Scenario",
                metricKey="metric",
                metricName="Metric",
                timeUnit="month",
                unit=None,
                status="ineligible",
                reason="No history.",
                seasonalPeriod=None,
                seasonalPeriodSource=None,
                observations=[],
                historyPeriods=[],
                predictionPeriods=[
                    SnapshotFeaturePeriod(date=date(2025, 1, 1), features={})
                ],
            )
        ],
    )


def test_calculation_child_entry_runs_in_its_own_group_with_private_tmp() -> None:
    worker = _worker(_child_calculate)
    child, receiver = worker._start_child(
        _single_kind_snapshot().model_dump_json(by_alias=True), "entry"
    )
    temporary_directory = worker._child_temporary_directory
    assert temporary_directory is not None
    assert Path(temporary_directory).parent == Path("/tmp")
    assert Path(temporary_directory).stat().st_mode & 0o777 == 0o700
    assert receiver.poll(30)
    state, payload = receiver.recv()
    receiver.close()
    worker._reap_child()

    assert state == "completed"
    calculation = PredictionCalculation.model_validate_json(payload)
    assert [result.kind for result in calculation.targets[0].results] == ["naive"]
    assert child.exitcode == 0
    assert not Path(temporary_directory).exists()
    assert worker._child is None and worker._child_temporary_directory is None


def test_child_isolation_uses_a_new_group_and_private_temporary_directory() -> None:
    supervisor_environment = dict(os.environ)
    worker = _worker(_report_isolation)
    child, receiver = worker._start_child("{}", "isolation")
    temporary_directory = worker._child_temporary_directory
    assert receiver.poll(30)
    state, payload = receiver.recv()
    receiver.close()
    worker._reap_child()

    report = json.loads(payload)
    assert state == "completed"
    assert report["sessionLeader"] is True
    assert report["processGroup"] == report["pid"] == child.pid
    assert report["tmpdir"] == report["mplconfigdir"] == temporary_directory
    assert Path(report["tempfile"]).parent == Path(str(temporary_directory))
    assert dict(os.environ) == supervisor_environment
    assert not Path(str(temporary_directory)).exists()


def test_stop_before_child_calls_setsid_stops_only_the_child() -> None:
    worker = _worker(_sleep_before_setsid)
    child, receiver = worker._start_child("{}", "before-setsid")
    receiver.close()
    temporary_directory = worker._child_temporary_directory
    assert child.pid is not None
    # The child is still in the supervisor's group; the group signal must not
    # address it, and the direct signal must still stop the child.
    assert os.getpgid(child.pid) == os.getpgid(0)

    started = time.monotonic()
    worker._stop_child()

    assert time.monotonic() - started < 5
    assert not child.is_alive()
    assert not Path(str(temporary_directory)).exists()


def test_stop_kills_the_child_group_and_removes_its_temporary_directory(
    tmp_path: Path,
) -> None:
    pid_path = tmp_path / "grandchild.pid"
    worker = _worker(_block_with_grandchild)
    child, receiver = worker._start_child(str(pid_path), "blocked")
    receiver.close()
    temporary_directory = worker._child_temporary_directory
    assert _wait_until(lambda: pid_path.exists() and pid_path.read_text() != "")
    grandchild = int(pid_path.read_text())
    assert _process_running(grandchild)

    started = time.monotonic()
    worker._stop_child()

    assert time.monotonic() - started < 5
    assert not child.is_alive()
    assert _wait_until(lambda: not _process_running(grandchild), timeout=5)
    assert not Path(str(temporary_directory)).exists()


def test_crashed_child_leaves_no_group_process_or_temporary_directory(
    tmp_path: Path,
) -> None:
    pid_path = tmp_path / "grandchild.pid"
    worker = _worker(_crash_with_grandchild)
    child, receiver = worker._start_child(str(pid_path), "crashed")
    # The plain join path: the child exits on its own before any stop.
    with pytest.raises(EOFError):
        receiver.recv()
    receiver.close()
    temporary_directory = worker._child_temporary_directory
    grandchild = int(pid_path.read_text())
    assert _process_running(grandchild)

    worker._reap_child()

    assert child.exitcode != 0
    assert _wait_until(lambda: not _process_running(grandchild), timeout=5)
    assert child.pid is not None and not _group_members(child.pid)
    assert not Path(str(temporary_directory)).exists()


def test_stopping_during_a_prophet_fit_leaves_no_cmdstan_process() -> None:
    worker = _worker(_long_prophet_fit)
    child, receiver = worker._start_child("{}", "prophet")
    receiver.close()
    temporary_directory = worker._child_temporary_directory
    try:
        assert child.pid is not None
        child_pid = child.pid
        # matplotlib's font cache rebuild runs fc-list in the same group first.
        assert _wait_until(lambda: _group_runs(child_pid, "prophet_model.bin"), 60), (
            "CmdStan did not start"
        )
        assert any(
            Path(temporary_directory or "").iterdir()
        ), "CmdStan did not write into the private temporary directory"

        started = time.monotonic()
        worker._stop_child()

        assert time.monotonic() - started < 5
    finally:
        # A failed assertion must not leave CmdStan sampling and pytest waiting
        # for the child at exit. After the timed stop this is a no-op.
        worker._stop_child()
    assert _wait_until(lambda: not _group_members(child_pid), timeout=5)
    assert not Path(str(temporary_directory)).exists()
