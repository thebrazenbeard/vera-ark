from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import threading
from typing import Any, Protocol
import urllib.error
import urllib.request
from uuid import uuid4

from .models import PerceptionResult, utc_now


class LedgerCorruptionError(RuntimeError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def strict_json_loads(text: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result

    return json.loads(
        text,
        object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-finite: {value}")
        ),
    )


class AppendOnlyJsonl:
    """Local append-only ledger with strict startup validation and durable flushes."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._sequence = self._validate_existing()

    def _validate_existing(self) -> int:
        if not self.path.exists():
            return 0
        expected = 1
        with self.path.open("r", encoding="utf-8", newline="") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.endswith("\n"):
                    raise LedgerCorruptionError(
                        f"{self.path} line {line_number} is not newline-terminated"
                    )
                try:
                    record = strict_json_loads(line)
                except (json.JSONDecodeError, ValueError) as exc:
                    raise LedgerCorruptionError(
                        f"{self.path} line {line_number} is invalid"
                    ) from exc
                if not isinstance(record, dict) or record.get("sequence") != expected:
                    raise LedgerCorruptionError(
                        f"{self.path} sequence mismatch at line {line_number}"
                    )
                expected += 1
        return expected - 1

    def append(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("kind must be a non-empty string")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        with self._lock:
            sequence = self._sequence + 1
            record = {
                "schema_version": "VERA_ARK_OPERATIONAL_EVENT_V1",
                "event_id": str(uuid4()),
                "sequence": sequence,
                "record_time": utc_now(),
                "kind": kind,
                "payload": payload,
            }
            encoded = canonical_json(record) + "\n"
            with self.path.open("a", encoding="utf-8", newline="") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            self._sequence = sequence
            return record

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        result: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                value = strict_json_loads(line)
                if not isinstance(value, dict):
                    raise LedgerCorruptionError("ledger record is not an object")
                result.append(value)
        return result


class EventAdapter(Protocol):
    def emit(self, event: dict[str, Any]) -> bool: ...


class NullEventAdapter:
    def emit(self, event: dict[str, Any]) -> bool:
        del event
        return False


class SupabaseEventAdapter:
    """Optional best-effort event mirror. It is never an action or authority source."""

    def __init__(
        self,
        url: str,
        anon_key: str,
        table: str = "vera_ark_operational_events",
        timeout: float = 5.0,
    ) -> None:
        self.url = url.rstrip("/")
        self.anon_key = anon_key
        self.table = table
        self.timeout = timeout

    @classmethod
    def from_environment(cls) -> "SupabaseEventAdapter | None":
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_ANON_KEY", "")
        if not url or not key:
            return None
        return cls(url, key)

    def emit(self, event: dict[str, Any]) -> bool:
        body = canonical_json(event).encode("utf-8")
        request = urllib.request.Request(
            f"{self.url}/rest/v1/{self.table}",
            data=body,
            method="POST",
            headers={
                "apikey": self.anon_key,
                "Authorization": f"Bearer {self.anon_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return 200 <= response.status < 300
        except (urllib.error.URLError, TimeoutError, OSError):
            return False


@dataclass(slots=True)
class OperationalStorage:
    event_ledger: AppendOnlyJsonl
    action_ledger: AppendOnlyJsonl
    adapter: EventAdapter

    @classmethod
    def create(
        cls,
        directory: Path,
        adapter: EventAdapter | None = None,
    ) -> "OperationalStorage":
        directory = Path(directory)
        return cls(
            event_ledger=AppendOnlyJsonl(directory / "events.jsonl"),
            action_ledger=AppendOnlyJsonl(directory / "actions.jsonl"),
            adapter=adapter or NullEventAdapter(),
        )

    def event(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = self.event_ledger.append(kind, payload)
        self.adapter.emit(record)
        return record

    def action(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = self.action_ledger.append(kind, payload)
        self.adapter.emit(record)
        return record


class MemoryAdapter(Protocol):
    def recall(self, perception: PerceptionResult) -> list[str]: ...


class NullMemoryAdapter:
    def recall(self, perception: PerceptionResult) -> list[str]:
        del perception
        return []


class JsonlMemoryAdapter:
    """Optional text-only context adapter. Invalid data fails closed to no context."""

    def __init__(self, path: Path, limit: int = 5) -> None:
        self.path = Path(path)
        self.limit = max(0, min(limit, 20))
        self.last_error: str | None = None

    def recall(self, perception: PerceptionResult) -> list[str]:
        del perception
        self.last_error = None
        if not self.path.exists() or self.limit == 0:
            return []
        try:
            rows: list[str] = []
            with self.path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    value = strict_json_loads(line)
                    if not isinstance(value, dict) or set(value) != {"text"}:
                        raise ValueError(f"invalid memory row {line_number}")
                    text = value["text"]
                    if not isinstance(text, str) or not text.strip() or len(text) > 500:
                        raise ValueError(f"invalid memory text {line_number}")
                    rows.append(text)
            return rows[-self.limit :]
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return []
