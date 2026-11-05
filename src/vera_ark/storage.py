from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import threading
from typing import Any, Protocol
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4

from .models import PerceptionResult, utc_now


class LedgerCorruptionError(RuntimeError):
    pass


class LedgerBusyError(LedgerCorruptionError):
    """A second writer or an unavailable OS lock must not corrupt the ledger."""

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
        self._writer_lease = self._acquire_writer_lease()
        try:
            self._sequence = self._validate_existing()
        except BaseException:
            self.close()
            raise

    def _acquire_writer_lease(self):
        """Nonblocking, OS-released single-writer ownership across processes."""
        lease_path = self.path.with_name(self.path.name + ".writer.lock")
        handle = lease_path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (ImportError, OSError) as exc:
            handle.close()
            raise LedgerBusyError("operational ledger already has a writer or no OS lock") from exc
        return handle

    def close(self) -> None:
        lock = getattr(self, "_lock", None)
        if lock is None:
            return
        with lock:
            handle = getattr(self, "_writer_lease", None)
            if handle is not None:
                self._writer_lease = None
                handle.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

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
            if self._writer_lease is None:
                raise LedgerBusyError("operational ledger writer lease is closed")
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


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Never forward the mirror credential or event payload to a redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


class SupabaseEventAdapter:
    """Optional HTTP-ack mirror; not durable-delivery or action-authority evidence.

    This project's design-only migration revokes anon/authenticated INSERT and
    defines no corresponding RLS INSERT policy. The environment adapter therefore
    starts unqualified and must not silently try to write to a provider.
    """

    def __init__(
        self,
        url: str,
        anon_key: str,
        table: str = "vera_ark_operational_events",
        timeout: float = 5.0,
        *,
        sink_qualified: bool = False,
    ) -> None:
        if not isinstance(url, str) or any(ord(ch) <= 32 for ch in url):
            raise ValueError("Supabase mirror URL must be an HTTPS origin")
        parsed = urllib.parse.urlsplit(url)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("invalid Supabase mirror origin port") from exc
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or (port is not None and port <= 0)
        ):
            raise ValueError("Supabase mirror URL must be a credential-free HTTPS origin")
        # Python's http.client encodes header values as latin-1 and can raise
        # UnicodeEncodeError on an unexpected non-ASCII token during emit.
        # Supabase JWT/publishable key representations use visible ASCII.
        if not isinstance(anon_key, str) or not anon_key or any(
            not 33 <= ord(ch) <= 126 for ch in anon_key
        ):
            raise ValueError("Supabase mirror key must contain visible ASCII only")
        if not isinstance(table, str) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table) is None:
            raise ValueError("Supabase mirror table must be a simple SQL identifier")
        if not isinstance(timeout, (float, int)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Supabase mirror timeout must be finite and positive")
        self.url = f"https://{parsed.netloc}"
        self.anon_key = anon_key
        self.table = table
        self.timeout = timeout
        # This is only a caller assertion; it is NOT live schema/RLS qualification.
        self.sink_qualified = sink_qualified is True

    @classmethod
    def from_environment(cls) -> "SupabaseEventAdapter | None":
        # Generic SUPABASE_* variables may belong to a completely different
        # service in this multi-project ecosystem. Never inherit them here.
        url = os.getenv("VERA_ARK_SUPABASE_URL", "")
        key = os.getenv("VERA_ARK_SUPABASE_ANON_KEY", "")
        project_ref = os.getenv("VERA_ARK_SUPABASE_PROJECT_REF", "")
        if not url or not key or re.fullmatch(r"[a-z0-9]+", project_ref) is None:
            return None
        if url.rstrip("/") != f"https://{project_ref}.supabase.co":
            return None
        try:
            return cls(url, key)
        except ValueError:
            # Optional provider configuration must not interrupt local logging.
            return None

    def emit(self, event: dict[str, Any]) -> bool:
        if not self.sink_qualified:
            return False
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
            # urllib's default redirect handler resends apikey and Authorization
            # after cross-origin HTTP 302 redirects. Never follow any redirect.
            opener = urllib.request.build_opener(_RejectRedirects())
            with opener.open(request, timeout=self.timeout) as response:
                # Prefer:return=minimal means a successful POST acknowledgment
                # should have an empty body. Read at most one byte; never buffer
                # attacker-controlled responses into the process.
                return response.status in (200, 201, 204) and not response.read(1)
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
