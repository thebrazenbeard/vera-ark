from __future__ import annotations

from vera_ark.capture import SyntheticCapture
from vera_ark.models import ActionIntention, PerceptionSource, new_id
from vera_ark.planner import FallbackPlanner, HeuristicPlanner, OfflinePerceptionEngine, make_planner


def test_heuristic_planner_returns_valid_intention() -> None:
    frame = SyntheticCapture().capture(0)
    perception = OfflinePerceptionEngine().perceive(frame, new_id(), 0)
    intention = HeuristicPlanner().plan(perception, frame)
    assert isinstance(intention, ActionIntention)
    assert intention.dry_run is True
    assert -1.0 <= intention.x <= 1.0
    assert -1.0 <= intention.y <= 1.0
    assert 0 <= intention.duration_ms <= ActionIntention.MAX_DURATION_MS
    assert perception.source is PerceptionSource.OFFLINE_HEURISTIC


def test_missing_openai_key_uses_offline_path(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    planner = make_planner("openai")
    assert isinstance(planner, FallbackPlanner)
    frame = SyntheticCapture().capture(0)
    perception = OfflinePerceptionEngine().perceive(frame, new_id(), 0)
    intention = planner.plan(perception, frame)
    assert intention.planner == "heuristic-v1"
    assert planner.last_fallback_reason
