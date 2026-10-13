from dataclasses import replace

import pytest
from physica.ark_bridge import MotionCalibration
from physica.spatial import AABB
from vera_ark.capture import SyntheticCapture
from vera_ark.controller import DryRunController
from vera_ark.models import ActionIntention, ActionType, new_id, utc_now
from vera_ark.physica_guard import PhysicaMotionGuard, MotionGuardBlocked
from vera_ark.planner import OfflinePerceptionEngine
from vera_ark.runtime import RuntimeConfig, VeraArkRuntime
from vera_ark.storage import OperationalStorage


def intention(action_type=ActionType.MOVE):
    return ActionIntention(
        schema_version=ActionIntention.SCHEMA_VERSION,
        intention_id=new_id(), perception_id=new_id(), session_id=new_id(),
        step=0, action_type=action_type, x=1.0, y=0.0,
        duration_ms=500, reason="synthetic", planner="test",
        created_at=utc_now(), dry_run=True,
    )


def guard(obstacles=()):
    return PhysicaMotionGuard(
        position_m=(0, 0),
        calibration=MotionCalibration((2, 0), (0, 2)), radius_m=0.1,
        obstacles=obstacles,
    )


def test_clear_move_and_possible_collision():
    assert guard()(intention()).status == "NO_BROAD_PHASE_CANDIDATES"
    with pytest.raises(MotionGuardBlocked, match="wall"):
        guard((AABB("wall", (0.9, -0.1), (1.1, 0.1)),))(intention())


def test_nonmove_does_not_require_world_prediction():
    noop = replace(intention(), action_type=ActionType.NOOP, x=0.0, duration_ms=0)
    assert guard()(noop).status == "NOT_APPLICABLE_NON_MOVE"


def test_rejects_malformed_or_live_actions():
    with pytest.raises(MotionGuardBlocked):
        guard()({"action_type": "MOVE"})
    with pytest.raises(TypeError):
        PhysicaMotionGuard(position_m=(0, 0), calibration=None)


def test_runtime_blocks_before_serializing_and_still_releases(tmp_path):
    obstacle = AABB("wall", (0.9, -0.1), (1.1, 0.1))
    storage = OperationalStorage.create(tmp_path / "logs")
    controller = DryRunController(storage)

    class MovePlanner:
        name = "test"
        def plan(self, perception, frame, memory_context=()):
            return ActionIntention(
                schema_version=ActionIntention.SCHEMA_VERSION,
                intention_id=new_id(), perception_id=perception.perception_id,
                session_id=perception.session_id, step=perception.step,
                action_type=ActionType.MOVE, x=1.0, y=0.0,
                duration_ms=500, reason="synthetic", planner="test",
                created_at=utc_now(), dry_run=True,
            )
    runtime = VeraArkRuntime(
        config=RuntimeConfig(steps=1, interval_seconds=0,stop_file=tmp_path/"STOP"),
        capture=SyntheticCapture(),perception=OfflinePerceptionEngine(),
        planner=MovePlanner(),controller=controller,storage=storage,
        motion_guard=guard((obstacle,)),
    )
    with pytest.raises(MotionGuardBlocked, match="wall"):
        runtime.run()
    assert controller.external_inputs_sent == 0
    assert any('"kind":"RELEASE_ALL"' in x or '"kind": "RELEASE_ALL"' in x
               for x in storage.action_ledger.path.read_text().splitlines())
