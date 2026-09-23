from __future__ import annotations

import pytest

from vera_ark.models import ActionIntention, ActionType, SchemaError, new_id, utc_now


def valid_action(**changes: object) -> ActionIntention:
    values: dict[str, object] = {
        "schema_version": ActionIntention.SCHEMA_VERSION,
        "intention_id": new_id(),
        "perception_id": new_id(),
        "session_id": new_id(),
        "step": 0,
        "action_type": ActionType.LOOK,
        "x": 0.25,
        "y": -0.25,
        "duration_ms": 200,
        "reason": "test",
        "planner": "test",
        "created_at": utc_now(),
        "dry_run": True,
    }
    values.update(changes)
    return ActionIntention(**values)  # type: ignore[arg-type]


def test_action_schema_rejects_invalid_range() -> None:
    with pytest.raises(SchemaError):
        valid_action(x=1.01)
    with pytest.raises(SchemaError):
        valid_action(duration_ms=1001)


def test_action_schema_rejects_live_output_and_unknown_keys() -> None:
    with pytest.raises(SchemaError):
        valid_action(dry_run=False)
    payload = valid_action().to_dict()
    payload["secret_override"] = True
    with pytest.raises(SchemaError):
        ActionIntention.from_dict(payload)


def test_noop_requires_zero_vector_and_duration() -> None:
    with pytest.raises(SchemaError):
        valid_action(action_type=ActionType.NOOP, x=0.1, y=0.0, duration_ms=0)
