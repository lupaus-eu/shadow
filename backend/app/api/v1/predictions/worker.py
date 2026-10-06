"""Standalone durable prediction-request supervisor.

Run with ``python -m app.api.v1.predictions.worker``. The worker intentionally
does not import or start FastAPI and needs only DATABASE_URL.
"""
# pyright: reportUnknownMemberType=false

import argparse
import logging
import multiprocessing
import os
import shutil
import signal
import sys
import tempfile
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from multiprocessing.connection import Connection as ProcessConnection
from multiprocessing.process import BaseProcess
from time import sleep
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import Engine, create_engine, select, text, update
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.api.v1.predictions import service
from app.api.v1.predictions.models import PredictionRequest
from app.api.v1.predictions.snapshots import (
    PredictionCalculation,
    PredictionInputSnapshot,
)
from app.api.v1.users.models import User
from app.core.config import get_settings, get_sqlalchemy_database_url

# The standalone worker does not import the API routers. Keep the Users table in
# its model registry so PredictionRequest's string-based audit FKs resolve.
_REGISTERED_USER_TABLE = User.__table__

LOGGER = logging.getLogger("schatten.prediction_worker")
WORKER_ADVISORY_LOCK = 7_303_589_321_057
POLL_SECONDS = 1.0
TERMINATION_GRACE_SECONDS = 2.0
CHILD_TEMPORARY_ROOT = "/tmp"
Failure = tuple[str, str]
ChildMessage = tuple[Literal["completed", "failed"], str]
# (snapshot JSON, result sender, private temporary directory)
ChildTarget = Callable[[str, ProcessConnection, str], None]

CALCULATION_FAILURE: Failure = (
    "CALCULATION_FAILED",
    "Prediction calculation failed unexpectedly.",
)
CHILD_FAILURE: Failure = (
    "CALCULATION_PROCESS_FAILED",
    "Prediction calculation process stopped unexpectedly.",
)
PUBLICATION_FAILURE: Failure = (
    "PUBLICATION_FAILED",
    "Prediction results could not be saved.",
)
INTERRUPTED_FAILURE: Failure = (
    "WORKER_INTERRUPTED",
    "Prediction calculation was interrupted and was not retried.",
)


def use_private_temporary_directory(temporary_directory: str) -> None:
    """Direct CmdStan, matplotlib and tempfile to the child's own directory."""
    os.environ["TMPDIR"] = temporary_directory
    os.environ["MPLCONFIGDIR"] = temporary_directory
    tempfile.tempdir = None


def _child_calculate(
    snapshot_json: str, sender: ProcessConnection, temporary_directory: str
) -> None:
    # A private process group lets the supervisor stop CmdStan with the child
    # (ADR-014). Both steps precede any model import or temporary-file use.
    os.setsid()
    use_private_temporary_directory(temporary_directory)
    try:
        snapshot = PredictionInputSnapshot.model_validate_json(snapshot_json)
        calculation = service.calculate_prediction(snapshot)
        sender.send(("completed", calculation.model_dump_json(by_alias=True)))
    except BaseException:
        sender.send(("failed", CALCULATION_FAILURE[0]))
    finally:
        sender.close()


class PredictionWorker:
    def __init__(
        self,
        engine: Engine,
        *,
        worker_id: str | None = None,
        child_target: ChildTarget = _child_calculate,
    ) -> None:
        self.engine = engine
        self.worker_id = worker_id or f"prediction_worker_{uuid4().hex}"
        self._lock_connection: Connection | None = None
        self._stopping = False
        self._child: BaseProcess | None = None
        self._child_temporary_directory: str | None = None
        self._child_target = child_target

    def request_stop(self, *_: object) -> None:
        self._stopping = True

    def run(self, *, once: bool = False) -> bool:
        """Run the supervisor; return false when another worker owns the lock."""
        self._require_postgresql()
        with self.engine.connect() as lock_connection:
            acquired = bool(
                lock_connection.scalar(
                    text("SELECT pg_try_advisory_lock(:key)"),
                    {"key": WORKER_ADVISORY_LOCK},
                )
            )
            if not acquired:
                LOGGER.info("Prediction worker lock is already owned")
                return False
            self._lock_connection = lock_connection
            LOGGER.info("Prediction worker acquired global ownership")
            try:
                self._recover_abandoned_requests()
                while not self._stopping:
                    self._verify_ownership()
                    request_id = self._claim_next_request()
                    if request_id is None:
                        if once:
                            break
                        sleep(POLL_SECONDS)
                        continue
                    self._execute_request(request_id)
                    if once:
                        break
            finally:
                self._stop_child()
                self._lock_connection = None
                try:
                    lock_connection.execute(
                        text("SELECT pg_advisory_unlock(:key)"),
                        {"key": WORKER_ADVISORY_LOCK},
                    )
                except Exception:
                    LOGGER.warning("Prediction worker ownership connection was lost")
            return True

    def _require_postgresql(self) -> None:
        if self.engine.dialect.name != "postgresql":
            raise RuntimeError("The prediction worker requires PostgreSQL.")

    def _verify_ownership(self) -> None:
        if self._lock_connection is None:
            raise RuntimeError("Prediction worker does not own its advisory lock.")
        self._lock_connection.execute(text("SELECT 1"))
        self._lock_connection.commit()

    @contextmanager
    def _transaction(self) -> Generator[Session, None, None]:
        """Fence supervisor state changes with the lock-owning connection."""
        self._verify_ownership()
        if self._lock_connection is None:
            raise RuntimeError("Prediction worker ownership was lost.")
        with Session(bind=self._lock_connection) as session, session.begin():
            yield session

    def _recover_abandoned_requests(self) -> None:
        now = datetime.now(UTC)
        with self._transaction() as session:
            session.execute(
                update(PredictionRequest)
                .where(PredictionRequest.state == "running")
                .values(
                    state="failed",
                    finish_time=now,
                    worker_id=None,
                    failure_code=INTERRUPTED_FAILURE[0],
                    failure_reason=INTERRUPTED_FAILURE[1],
                )
            )
            session.execute(
                update(PredictionRequest)
                .where(PredictionRequest.state == "cancelling")
                .values(state="cancelled", finish_time=now, worker_id=None)
            )
        LOGGER.info("Recovered abandoned active prediction requests")

    def _claim_next_request(self) -> int | None:
        with self._transaction() as session:
            request = session.scalar(
                select(PredictionRequest)
                .where(PredictionRequest.state == "queued")
                .order_by(
                    PredictionRequest.submitted_time,
                    PredictionRequest.prediction_request_id,
                )
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if request is None:
                return None
            request.state = "running"
            request.start_time = datetime.now(UTC)
            request.worker_id = self.worker_id
            request_id = request.prediction_request_id
            request_key = request.prediction_request_key
        LOGGER.info("Claimed prediction request request_id=%s", request_key)
        return request_id

    def _execute_request(self, request_id: int) -> None:
        loaded = self._load_owned_snapshot(request_id)
        if loaded is None:
            return
        request_key, snapshot = loaded
        child, receiver = self._start_child(
            snapshot.model_dump_json(by_alias=True),
            f"prediction-calculation-{request_id}",
        )
        message: ChildMessage | None = None
        try:
            while True:
                if receiver.poll(POLL_SECONDS):
                    message = cast(ChildMessage, receiver.recv())
                    break
                self._verify_ownership()
                state = self._owned_request_state(request_id)
                if self._stopping or state == "cancelling" or state is None:
                    self._stop_child()
                    if state == "cancelling":
                        self._mark_cancelled(request_id)
                        LOGGER.info(
                            "Cancelled prediction request request_id=%s", request_key
                        )
                    elif state is not None:
                        self._mark_failed(request_id, INTERRUPTED_FAILURE)
                    return
                if not child.is_alive():
                    break
        except (EOFError, OSError):
            message = None
        finally:
            receiver.close()
        if message is None and child.is_alive():
            self._stop_child()
        else:
            self._reap_child()

        if message is None or message[0] != "completed" or child.exitcode != 0:
            self._mark_failed(
                request_id,
                CALCULATION_FAILURE if message is not None else CHILD_FAILURE,
            )
            LOGGER.warning("Prediction child failed request_id=%s", request_key)
            return
        try:
            calculation = PredictionCalculation.model_validate_json(message[1])
            outcome = self._publish(request_id, snapshot, calculation)
        except Exception:
            self._mark_failed(request_id, PUBLICATION_FAILURE)
            LOGGER.error("Prediction publication failed request_id=%s", request_key)
            return
        LOGGER.info("Prediction request %s request_id=%s", outcome, request_key)

    def _start_child(
        self, snapshot_json: str, name: str
    ) -> tuple[BaseProcess, ProcessConnection]:
        """Start one calculation child with its own private temporary directory."""
        temporary_directory = tempfile.mkdtemp(
            prefix="schatten-prediction-", dir=CHILD_TEMPORARY_ROOT
        )
        self._child_temporary_directory = temporary_directory
        context = multiprocessing.get_context("spawn")
        receiver, sender = context.Pipe(duplex=False)
        child = context.Process(
            target=self._child_target,
            args=(snapshot_json, sender, temporary_directory),
            name=name,
        )
        self._child = child
        try:
            child.start()
        except BaseException:
            receiver.close()
            self._release_child()
            raise
        finally:
            sender.close()
        return child, receiver

    def _load_owned_snapshot(
        self, request_id: int
    ) -> tuple[str, PredictionInputSnapshot] | None:
        with self._transaction() as session:
            request = session.get(PredictionRequest, request_id)
            if (
                request is None
                or request.state != "running"
                or request.worker_id != self.worker_id
            ):
                return None
            snapshot = PredictionInputSnapshot.model_validate(request.input_snapshot)
            return request.prediction_request_key, snapshot

    def _owned_request_state(self, request_id: int) -> str | None:
        with self._transaction() as session:
            return session.scalar(
                select(PredictionRequest.state).where(
                    PredictionRequest.prediction_request_id == request_id,
                    PredictionRequest.worker_id == self.worker_id,
                )
            )

    def _publish(
        self,
        request_id: int,
        snapshot: PredictionInputSnapshot,
        calculation: PredictionCalculation,
    ) -> str:
        with self._transaction() as session:
            service._lock_prediction_names(  # pyright: ignore[reportPrivateUsage]
                session, snapshot.organisation_internal_id
            )
            request = session.scalar(
                select(PredictionRequest)
                .where(PredictionRequest.prediction_request_id == request_id)
                .with_for_update()
            )
            if request is None or request.worker_id != self.worker_id:
                return "lost ownership"
            if request.state == "cancelling":
                request.state = "cancelled"
                request.finish_time = datetime.now(UTC)
                request.worker_id = None
                return "cancelled"
            if request.state != "running":
                return "not published"
            version = service.persist_prediction(session, snapshot, calculation)
            request.state = "completed"
            request.finish_time = datetime.now(UTC)
            request.worker_id = None
            request.completed_prediction_version_id = version.prediction_version_id
        return "completed"

    def _mark_cancelled(self, request_id: int) -> None:
        with self._transaction() as session:
            request = session.scalar(
                select(PredictionRequest)
                .where(PredictionRequest.prediction_request_id == request_id)
                .with_for_update()
            )
            if (
                request is not None
                and request.state == "cancelling"
                and request.worker_id == self.worker_id
            ):
                request.state = "cancelled"
                request.finish_time = datetime.now(UTC)
                request.worker_id = None

    def _mark_failed(self, request_id: int, failure: Failure) -> None:
        with self._transaction() as session:
            request = session.scalar(
                select(PredictionRequest)
                .where(PredictionRequest.prediction_request_id == request_id)
                .with_for_update()
            )
            if request is None or request.worker_id != self.worker_id:
                return
            if request.state == "cancelling":
                request.state = "cancelled"
                request.finish_time = datetime.now(UTC)
                request.worker_id = None
            elif request.state == "running":
                request.state = "failed"
                request.finish_time = datetime.now(UTC)
                request.worker_id = None
                request.failure_code = failure[0]
                request.failure_reason = failure[1]

    def _stop_child(self) -> None:
        child = self._child
        if child is None:
            return
        if child.pid is not None:
            if child.is_alive():
                child.terminate()
                _signal_process_group(child.pid, signal.SIGTERM)
                child.join(TERMINATION_GRACE_SECONDS)
            if child.is_alive():
                child.kill()
                _signal_process_group(child.pid, signal.SIGKILL)
            child.join()
        self._release_child()

    def _reap_child(self) -> None:
        child = self._child
        if child is not None and child.pid is not None:
            child.join()
        self._release_child()

    def _release_child(self) -> None:
        """Kill leftovers of a reaped child's group, then remove its files."""
        child = self._child
        if child is not None and child.pid is not None:
            _signal_process_group(child.pid, signal.SIGKILL)
        if self._child_temporary_directory is not None:
            shutil.rmtree(self._child_temporary_directory, ignore_errors=True)
        self._child = None
        self._child_temporary_directory = None


def _signal_process_group(process_group_id: int, signum: signal.Signals) -> None:
    # Address the group only by the child's PID: a child that has not called
    # os.setsid() yet is still in the supervisor's own group (ADR-014).
    try:
        os.killpg(process_group_id, signum)
    except ProcessLookupError:
        pass


def worker_is_healthy(engine: Engine) -> bool:
    """Return true when another live connection owns the worker lock."""
    if engine.dialect.name != "postgresql":
        return False
    try:
        with engine.connect() as connection:
            acquired = bool(
                connection.scalar(
                    text("SELECT pg_try_advisory_lock(:key)"),
                    {"key": WORKER_ADVISORY_LOCK},
                )
            )
            if acquired:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": WORKER_ADVISORY_LOCK},
                )
                return False
            return True
    except Exception:
        return False


def _engine() -> Engine:
    settings = get_settings()
    return create_engine(
        get_sqlalchemy_database_url(settings),
        pool_pre_ping=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the prediction worker")
    parser.add_argument(
        "command", nargs="?", choices=("run", "health-check"), default="run"
    )
    parser.add_argument("--once", action="store_true")
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    engine = _engine()
    try:
        if arguments.command == "health-check":
            return 0 if worker_is_healthy(engine) else 1
        worker = PredictionWorker(engine)
        signal.signal(signal.SIGTERM, worker.request_stop)
        signal.signal(signal.SIGINT, worker.request_stop)
        return 0 if worker.run(once=arguments.once) else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
