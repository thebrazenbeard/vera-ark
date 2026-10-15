"""Offline semantic report-binding adversarial regression tests."""
import copy
import json
from pathlib import Path

import pytest
from vera_ark import cli
from vera_ark.offline_session_audit import audit_offline_session
from vera_ark.offline_semantic_evidence import audit_offline_semantic_binding, contract_expected_reports


@pytest.fixture
def ledgers(tmp_path: Path):
    folder = tmp_path / "demo"
    assert cli.main(["demo", "--steps", "2", "--log-dir", str(folder)]) == 0
    return tuple([json.loads(x) for x in (folder / name).read_text().splitlines()]
                 for name in ("events.jsonl", "actions.jsonl"))


def test_unmodified_offline_demo_is_semantically_consistent(ledgers):
    report = audit_offline_semantic_binding(*ledgers)
    assert report["semantic_report_byte_binding_verified"] is True
    assert report["live_controller_route_verified"] is False
    assert report["controller_causality_verified"] is False

def test_declared_action_spoof_is_rejected(ledgers):
    events, actions = copy.deepcopy(ledgers)
    declared = actions[0]["payload"]["intention"]
    if declared["action_type"] == "NOOP":
        declared["action_type"], declared["duration_ms"] = "INTERACT", 1
    else:
        declared.update({"action_type": "NOOP", "x": 0.0, "y": 0.0, "duration_ms": 0})
    for event in events:
        if event["kind"] == "ACTION_INTENTION_PLANNED" and event["payload"]["step"] == 0:
            event["payload"] = copy.deepcopy(declared)
            break
    assert audit_offline_session(events, actions)["status"] == (
        "DECLARED_DRY_RUN_LEDGER_SELF_CONSISTENT"
    )
    with pytest.raises(ValueError, match="semantic"):
        audit_offline_semantic_binding(events, actions)


def test_contract_interact_exact_cross_byte(ledgers):
    from vera_ark.models import ActionIntention
    source = copy.deepcopy(ledgers[1][0]["payload"]["intention"])
    source.update(action_type="INTERACT", x=0.0, y=0.0, duration_ms=19)
    reports = contract_expected_reports(ActionIntention.from_dict(source))
    assert reports[0][0].hex() == "018080808028" + "00" * 58
    assert reports[1][1] == 19

def test_contract_move_and_look_extremes(ledgers):
    from vera_ark.models import ActionIntention
    source = copy.deepcopy(ledgers[1][0]["payload"]["intention"])
    source.update(action_type="MOVE", x=1.0, y=-1.0, duration_ms=100)
    move = contract_expected_reports(ActionIntention.from_dict(source))
    assert move[0][0][1:3] == bytes([255, 255])
    source.update(action_type="LOOK", x=-1.0, y=1.0)
    look = contract_expected_reports(ActionIntention.from_dict(source))
    assert look[0][0][3:5] == bytes([0, 0])


def test_oracle_does_not_call_controller_mapper(ledgers, monkeypatch):
    import vera_ark.controller as controller
    from vera_ark.models import ActionIntention
    source = copy.deepcopy(ledgers[1][0]["payload"]["intention"])
    source.update(action_type="INTERACT", x=0.0, y=0.0, duration_ms=10)
    monkeypatch.setattr(controller, "intention_to_ds4_sequence", lambda _: (_ for _ in ()).throw(AssertionError("shared mapper called")))
    assert contract_expected_reports(ActionIntention.from_dict(source))[0][0][5] == 0x28


def test_stopped_before_first_action_has_no_semantic_evidence(tmp_path: Path):
    stop = tmp_path / "STOP"
    stop.write_text("stop", encoding="utf-8")
    folder = tmp_path / "stopped"
    assert cli.main(["demo", "--steps", "2", "--log-dir", str(folder),
                     "--stop-file", str(stop)]) == 0
    events, actions = tuple(
        [json.loads(line) for line in (folder / name).read_text().splitlines()]
        for name in ("events.jsonl", "actions.jsonl")
    )
    assert audit_offline_session(events, actions)["completed_steps"] == 0
    result = audit_offline_semantic_binding(events, actions)
    assert result["semantic_report_byte_binding_verified"] is False
    assert result["semantic_actions_checked"] == 0
    assert result["semantic_binding_status"] == "NOT_APPLICABLE_NO_ACTIONS"


def test_completed_demo_counts_only_semantic_actions(ledgers):
    result = audit_offline_semantic_binding(*ledgers)
    assert result["semantic_actions_checked"] == 2
    assert result["semantic_binding_status"] == "CHECKED"


@pytest.mark.parametrize(
    "kind,x,y,expected",
    [
        ("MOVE", -1.0, 1.0, bytes([0, 0, 128, 128, 8])),
        ("MOVE", 1.0, -1.0, bytes([255, 255, 128, 128, 8])),
        ("LOOK", -1.0, 1.0, bytes([128, 128, 0, 0, 8])),
        ("LOOK", 1.0, -1.0, bytes([128, 128, 255, 255, 8])),
        ("INTERACT", 0.0, 0.0, bytes([128, 128, 128, 128, 0x28])),
        ("NOOP", 0.0, 0.0, bytes([128, 128, 128, 128, 8])),
    ],
)
def test_contract_independent_byte_anchors(ledgers, kind, x, y, expected):
    from vera_ark.models import ActionIntention
    source = copy.deepcopy(ledgers[1][0]["payload"]["intention"])
    source.update(action_type=kind, x=x, y=y,
                  duration_ms=0 if kind == "NOOP" else 31)
    reports = contract_expected_reports(ActionIntention.from_dict(source))
    assert reports[0][0][:6] == b"\x01" + expected
    assert len(reports[0][0]) == 64
    assert reports[-1][0] == bytes.fromhex("018080808008" + "00" * 58)
    assert len(reports) == (1 if kind == "NOOP" else 2)
    if kind != "NOOP":
        assert reports[-1][1] == 31


def test_neutral_only_session_is_not_nonneutral_evidence(tmp_path, monkeypatch):
    from dataclasses import replace
    from vera_ark.models import ActionType
    from vera_ark.planner import HeuristicPlanner
    original = HeuristicPlanner.plan

    def neutral(self, perception, frame, memory_context=()):
        return replace(original(self, perception, frame, memory_context),
                       action_type=ActionType.NOOP, x=0.0, y=0.0, duration_ms=0)

    monkeypatch.setattr(HeuristicPlanner, "plan", neutral)
    folder = tmp_path / "neutral"
    assert cli.main(["demo", "--steps", "2", "--log-dir", str(folder)]) == 0
    rows = tuple([json.loads(x) for x in (folder / name).read_text().splitlines()]
                 for name in ("events.jsonl", "actions.jsonl"))
    result = audit_offline_semantic_binding(*rows)
    assert result["semantic_actions_checked"] == 2
    assert result["nonneutral_report_batches_checked"] == 0
    assert result["nonneutral_report_binding_checked"] is False
    assert result["live_controller_route_verified"] is False


def test_non_neutral_session_counts_checked_reports(tmp_path, monkeypatch):
    from dataclasses import replace
    from vera_ark.models import ActionType
    from vera_ark.planner import HeuristicPlanner
    original = HeuristicPlanner.plan

    def look(self, perception, frame, memory_context=()):
        return replace(original(self, perception, frame, memory_context),
                       action_type=ActionType.LOOK, x=1.0, y=-1.0, duration_ms=20)

    monkeypatch.setattr(HeuristicPlanner, "plan", look)
    folder = tmp_path / "nonneutral"
    assert cli.main(["demo", "--steps", "2", "--log-dir", str(folder)]) == 0
    rows = tuple([json.loads(x) for x in (folder / name).read_text().splitlines()]
                 for name in ("events.jsonl", "actions.jsonl"))
    result = audit_offline_semantic_binding(*rows)
    assert result["semantic_actions_checked"] == 2
    assert result["nonneutral_report_batches_checked"] == 2
    assert result["nonneutral_report_binding_checked"] is True
    assert result["controller_causality_verified"] is False


def test_declared_look_axis_spoof_with_matching_event_is_rejected(ledgers):
    events, actions = copy.deepcopy(ledgers)
    intention = actions[0]["payload"]["intention"]
    intention.update(action_type="LOOK", x=1.0, y=-1.0, duration_ms=25)
    for event in events:
        if event["kind"] == "ACTION_INTENTION_PLANNED" and event["payload"]["step"] == 0:
            event["payload"] = copy.deepcopy(intention)
            break
    assert audit_offline_session(events, actions)["status"] == (
        "DECLARED_DRY_RUN_LEDGER_SELF_CONSISTENT")
    with pytest.raises(ValueError, match="semantic action"):
        audit_offline_semantic_binding(events, actions)
