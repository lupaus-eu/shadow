from datetime import UTC, datetime
from threading import Lock


class FixedWindowRateLimiter:
    def __init__(self, max_entries: int = 10_000) -> None:
        self._max_entries = max_entries
        self._entries: dict[tuple[str, str, int], int] = {}
        self._lock = Lock()

    def allow(
        self,
        bucket: str,
        address: str,
        limit: int,
        *,
        now: datetime | None = None,
    ) -> bool:
        current = now or datetime.now(UTC)
        window = int(current.timestamp()) // 60
        key = (bucket, address, window)
        with self._lock:
            expired = [entry for entry in self._entries if entry[2] < window]
            for entry in expired:
                del self._entries[entry]
            count = self._entries.get(key)
            if count is None:
                if len(self._entries) >= self._max_entries:
                    return False
                self._entries[key] = 1
                return True
            if count >= limit:
                return False
            self._entries[key] = count + 1
            return True
