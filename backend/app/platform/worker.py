"""The platform worker: background jobs and the email outbox (ADR-019).

Run with ``python -m app.platform.worker``. It needs only ``DATABASE_URL`` (and
the email settings once outbox delivery is registered) and does not import
FastAPI. ``health-check`` verifies that a new process can reach the database
(it does not prove the main loop is alive); ``--once`` drains the due work and
exits. A handler still running at shutdown is killed after the grace period and
its job is taken over after the claim timeout (at-least-once).
"""

import argparse
import logging
import os
import signal
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from time import sleep
from types import FrameType

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import (
    RequestContext,
    get_engine,
    get_session_factory,
    transaction_session,
)
from app.platform.jobs import run_one_background_job, run_schedulers

LOGGER = logging.getLogger("shadow.worker")


class Worker:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        schedule_interval: timedelta = timedelta(hours=1),
        idle_sleep_seconds: float = 1.0,
        error_sleep_seconds: float = 5.0,
    ) -> None:
        self._session_factory = session_factory
        self._schedule_interval = schedule_interval
        self._idle_sleep_seconds = idle_sleep_seconds
        self._error_sleep_seconds = error_sleep_seconds
        self._next_schedule = datetime.now(UTC)
        self._stop = False

    def request_stop(
        self, _signal_number: int = 0, _frame: FrameType | None = None
    ) -> None:
        self._stop = True

    def run_once(self, now: datetime | None = None) -> bool:
        """One pass: due schedulers, then one job. True when any work was done."""
        now = now or datetime.now(UTC)
        worked = False
        if now >= self._next_schedule:
            run_schedulers(self._session_factory, now)
            self._next_schedule = now + self._schedule_interval
        if run_one_background_job(self._session_factory):
            worked = True
        return worked

    def run(self, *, once: bool = False) -> None:
        while not self._stop:
            try:
                worked = self.run_once()
                if once:
                    while worked and not self._stop:
                        worked = self.run_once()
                    return
            except Exception:  # noqa: BLE001 - a database blip must not end the worker
                if once:
                    raise
                LOGGER.exception("worker pass failed; retrying")
                sleep(self._error_sleep_seconds)
                continue
            if not worked:
                sleep(self._idle_sleep_seconds)


def worker_is_healthy(session_factory: sessionmaker[Session]) -> bool:
    try:
        with transaction_session(session_factory, RequestContext()) as session:
            return session.scalar(text("SELECT 1")) == 1
    except Exception:  # noqa: BLE001 - any failure means unhealthy
        LOGGER.exception("worker health check failed")
        return False


def _schedule_interval_seconds() -> int:
    raw = os.getenv("WORKER_SCHEDULE_INTERVAL_SECONDS", "3600")
    try:
        seconds = int(raw)
    except ValueError:
        raise ValueError(
            f"WORKER_SCHEDULE_INTERVAL_SECONDS must be an integer, got {raw!r}"
        ) from None
    if seconds < 1:
        raise ValueError("WORKER_SCHEDULE_INTERVAL_SECONDS must be at least 1")
    return seconds


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the platform worker")
    parser.add_argument(
        "command", nargs="?", choices=("run", "health-check"), default="run"
    )
    parser.add_argument("--once", action="store_true")
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    session_factory = get_session_factory()
    try:
        if arguments.command == "health-check":
            return 0 if worker_is_healthy(session_factory) else 1
        worker = Worker(
            session_factory,
            schedule_interval=timedelta(seconds=_schedule_interval_seconds()),
        )
        signal.signal(signal.SIGTERM, worker.request_stop)
        signal.signal(signal.SIGINT, worker.request_stop)
        worker.run(once=arguments.once)
        return 0
    finally:
        get_engine().dispose()


if __name__ == "__main__":
    sys.exit(main())
