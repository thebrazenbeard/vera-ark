from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
import math
import re
from typing import Any, Mapping
from uuid import UUID, uuid4


class SchemaError(ValueError):
    """Raised when untrusted structured data violates a closed schema."""


class PerceptionSource(StrEnum):
    OFFLINE_HEURISTIC = "OFFLINE_HEURISTIC"
    OPENAI_VISION = "OPENAI_VISION"


class ActionType(StrEnum):
    NOOP = "NOOP"
    MOVE = "MOVE"
    LOOK = "LOOK"
    INTERACT = "INTERACT"
    RELEASE_ALL = "RELEASE_ALL"


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def new_id() -> str:
    return str(uuid4())


def _require_exact_keys(data: Mapping[str, Any], keys: set[str], label: str) -> None:
    actual = set(data)
    missing = sorted(keys - actual)
    extra = sorted(actual - keys)
    if missing or extra:
        raise SchemaError(f"{label} keys mismatch; missing={missing}, extra={extra}")


def _require_str(value: Any, field: str, *, maximum: int = 4096, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise SchemaError(f"{field} must be a string")
    if not allow_empty and not value.strip():
        raise SchemaError(f"{field} must not be empty")
    if len(value) > maximum:
        raise SchemaError(f"{field} exceeds {maximum} characters")
    return value


def _require_int(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaError(f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise SchemaError(f"{field} must be between {minimum} and {maximum}")
    return value


def _require_float(value: Any, field: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchemaError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise SchemaError(f"{field} must be finite")
    if not minimum <= result <= maximum:
        raise SchemaError(f"{field} must be between {minimum} and {maximum}")
    return result


def _require_uuid(value: Any, field: str) -> str:
    text = _require_str(value, field, maximum=36)
    try:
        parsed = UUID(text)
    except ValueError as exc:
        raise SchemaError(f"{field} must be a UUID") from exc
    if str(parsed) != text.lower():
        raise SchemaError(f"{field} must use canonical UUID text")
    return text.lower()


def _require_timestamp(value: Any, field: str) -> str:
    text = _require_str(value, field, maximum=40)
    if not text.endswith("Z"):
        raise SchemaError(f"{field} must be UTC and end with Z")
    try:
        datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise SchemaError(f"{field} is not a valid timestamp") from exc
    return text


@dataclass(frozen=True, slots=True)
class PerceptionResult:
    schema_version: str
    perception_id: str
    session_id: str
    step: int
    captured_at: str
    image_sha256: str
    width: int
    height: int
    monitor_index: int
    summary: str
    observations: tuple[str, ...]
    confidence: float
    source: PerceptionSource

    SCHEMA_VERSION = "VERA_ARK_PERCEPTION_V1"

    def __post_init__(self) -> None:
        if self.schema_version != self.SCHEMA_VERSION:
            raise SchemaError(f"schema_version must be {self.SCHEMA_VERSION}")
        _require_uuid(self.perception_id, "perception_id")
        _require_uuid(self.session_id, "session_id")
        _require_int(self.step, "step", minimum=0, maximum=1_000_000)
        _require_timestamp(self.captured_at, "captured_at")
        if not isinstance(self.image_sha256, str) or not _SHA256_RE.fullmatch(self.image_sha256):
            raise SchemaError("image_sha256 must be lowercase SHA-256")
        _require_int(self.width, "width", minimum=1, maximum=32768)
        _require_int(self.height, "height", minimum=1, maximum=32768)
        _require_int(self.monitor_index, "monitor_index", minimum=0, maximum=127)
        _require_str(self.summary, "summary", maximum=1000)
        if not isinstance(self.observations, tuple) or len(self.observations) > 32:
            raise SchemaError("observations must be a tuple with at most 32 entries")
        for item in self.observations:
            _require_str(item, "observation", maximum=300)
        _require_float(self.confidence, "confidence", minimum=0.0, maximum=1.0)
        if not isinstance(self.source, PerceptionSource):
            raise SchemaError("source must be a PerceptionSource")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["observations"] = list(self.observations)
        result["source"] = self.source.value
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PerceptionResult":
        keys = {
            "schema_version", "perception_id", "session_id", "step", "captured_at",
            "image_sha256", "width", "height", "monitor_index", "summary",
            "observations", "confidence", "source",
        }
        _require_exact_keys(data, keys, "PerceptionResult")
        observations = data["observations"]
        if not isinstance(observations, list):
            raise SchemaError("observations must be a list")
        try:
            source = PerceptionSource(data["source"])
        except (TypeError, ValueError) as exc:
            raise SchemaError("source is unknown") from exc
        return cls(
            schema_version=data["schema_version"],
            perception_id=data["perception_id"],
            session_id=data["session_id"],
            step=data["step"],
            captured_at=data["captured_at"],
            image_sha256=data["image_sha256"],
            width=data["width"],
            height=data["height"],
            monitor_index=data["monitor_index"],
            summary=data["summary"],
            observations=tuple(observations),
            confidence=data["confidence"],
            source=source,
        )


@dataclass(frozen=True, slots=True)
class ActionIntention:
    schema_version: str
    intention_id: str
    perception_id: str
    session_id: str
    step: int
    action_type: ActionType
    x: float
    y: float
    duration_ms: int
    reason: str
    planner: str
    created_at: str
    dry_run: bool

    SCHEMA_VERSION = "VERA_ARK_ACTION_INTENTION_V1"
    MAX_DURATION_MS = 1000

    def __post_init__(self) -> None:
        if self.schema_version != self.SCHEMA_VERSION:
            raise SchemaError(f"schema_version must be {self.SCHEMA_VERSION}")
        _require_uuid(self.intention_id, "intention_id")
        _require_uuid(self.perception_id, "perception_id")
        _require_uuid(self.session_id, "session_id")
        _require_int(self.step, "step", minimum=0, maximum=1_000_000)
        if not isinstance(self.action_type, ActionType):
            raise SchemaError("action_type must be an ActionType")
        x = _require_float(self.x, "x", minimum=-1.0, maximum=1.0)
        y = _require_float(self.y, "y", minimum=-1.0, maximum=1.0)
        duration = _require_int(
            self.duration_ms, "duration_ms", minimum=0, maximum=self.MAX_DURATION_MS
        )
        _require_str(self.reason, "reason", maximum=500)
        _require_str(self.planner, "planner", maximum=100)
        _require_timestamp(self.created_at, "created_at")
        if self.dry_run is not True:
            raise SchemaError("dry_run must be true; live output is not supported")
        if self.action_type in {ActionType.NOOP, ActionType.RELEASE_ALL, ActionType.INTERACT}:
            if x != 0.0 or y != 0.0:
                raise SchemaError(f"{self.action_type.value} requires x=0 and y=0")
        if self.action_type in {ActionType.NOOP, ActionType.RELEASE_ALL} and duration != 0:
            raise SchemaError(f"{self.action_type.value} requires duration_ms=0")
        if self.action_type is ActionType.INTERACT and duration == 0:
            raise SchemaError("INTERACT requires duration_ms between 1 and 1000")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["action_type"] = self.action_type.value
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ActionIntention":
        keys = {
            "schema_version", "intention_id", "perception_id", "session_id", "step",
            "action_type", "x", "y", "duration_ms", "reason", "planner",
            "created_at", "dry_run",
        }
        _require_exact_keys(data, keys, "ActionIntention")
        try:
            action_type = ActionType(data["action_type"])
        except (TypeError, ValueError) as exc:
            raise SchemaError("action_type is unknown") from exc
        return cls(
            schema_version=data["schema_version"],
            intention_id=data["intention_id"],
            perception_id=data["perception_id"],
            session_id=data["session_id"],
            step=data["step"],
            action_type=action_type,
            x=data["x"],
            y=data["y"],
            duration_ms=data["duration_ms"],
            reason=data["reason"],
            planner=data["planner"],
            created_at=data["created_at"],
            dry_run=data["dry_run"],
        )
