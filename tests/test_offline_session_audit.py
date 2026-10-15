"""Adversarial checks for declared offline session ledger consistency."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from vera_ark import cli
from vera_ark.controller import ControllerError
from vera_ark.offline_session_audit import audit_offline_session


@pytest.fixture
def demo(tmp_path: Path) -> tuple[list[dict], list[dict]]:
    directory = tmp_path / "demo"
    assert cli.main(["demo", "--steps", "2", "--log-dir", str(directory)]) == 0
    def load(name: str) -> list[dict]:
        return [json.loads(line) for line in (directory / name).read_text().splitlines()]
    return load("events.jsonl"), load("actions.jsonl")


def test_valid_real_offline_demo_records(demo):
    report = audit_offline_session(*demo)
    assert report["completed_steps"] == 2
    assert report["verified_serialized_batches"] == 3
    assert report["terminal_neutral_release_declared_and_byte_checked"] is True
    assert report["live_controller_route_verified"] is False
    assert report["controller_causality_verified"] is False


@pytest.mark.parametrize("mutation", [
    "missing_release", "duplicate_release", "false_external_input",
    "altered_neutral", "altered_batch", "altered_report_digest",
    "wrong_session", "wrong_planned_intention", "missing_action_event",
    "wrong_completed_count", "duplicate_sequence", "noncanonical_hex",
    "altered_decoded_state", "altered_offset", "duplicate_intention",
])
def test_adversarial_tampering_rejected(demo, mutation):
    events, actions = copy.deepcopy(demo)
    if mutation == "missing_release":
        actions.pop()
    elif mutation == "duplicate_release":
        actions.insert(-1, copy.deepcopy(actions[-1]))
    elif mutation == "false_external_input":
        actions[0]["payload"]["receipt"]["external_inputs_sent"] = 1
    elif mutation == "altered_neutral":
        actions[-1]["payload"]["transport_receipts"][0]["report_hex"] = "00" * 64
    elif mutation == "altered_batch":
        actions[0]["payload"]["transport_receipts"][0]["submission_hex"] = "00" * 84
    elif mutation == "altered_report_digest":
        actions[0]["payload"]["transport_receipts"][0]["report_sha256"] = "0" * 64
    elif mutation == "wrong_session":
        actions[0]["payload"]["intention"]["session_id"] = "00000000-0000-4000-8000-000000000000"
    elif mutation == "wrong_planned_intention":
        for event in events:
            if event["kind"] == "ACTION_INTENTION_PLANNED":
                event["payload"]["reason"] = "tampered"
                break
    elif mutation == "missing_action_event":
        events = [e for e in events if e["kind"] != "DRY_RUN_ACTION_RECORDED"]
        for n, event in enumerate(events, 1):
            event["sequence"] = n
    elif mutation == "wrong_completed_count":
        events[-1]["payload"]["completed_steps"] = 9
    elif mutation == "duplicate_sequence":
        actions[1]["sequence"] = 1
    elif mutation == "noncanonical_hex":
        actions[0]["payload"]["transport_receipts"][0]["report_hex"] = (
            actions[0]["payload"]["transport_receipts"][0]["report_hex"].upper()
        )
        if actions[0]["payload"]["transport_receipts"][0]["report_hex"].isdigit():
            actions[0]["payload"]["transport_receipts"][0]["report_hex"] += " "
    elif mutation == "altered_decoded_state":
        actions[0]["payload"]["transport_receipts"][0]["decoded_state"]["left_x"] = 255
    elif mutation == "altered_offset":
        actions[0]["payload"]["transport_receipts"][0]["offset_ms"] = 123
    elif mutation == "duplicate_intention":
        actions[1]["payload"]["intention"]["intention_id"] = (
            actions[0]["payload"]["intention"]["intention_id"]
        )
    with pytest.raises((ValueError, KeyError, TypeError, ControllerError)):
        audit_offline_session(events, actions)


def test_no_gameplay_claims_even_when_offline_audit_passes(demo):
    report = audit_offline_session(*demo)
    assert report["capture_authenticity_verified"] is False
    assert report["independent_review"] is False
    assert report["claim_ceiling"] == "CALLER_SUPPLIED_OFFLINE_LEDGER_CONSISTENCY_ONLY"

@pytest.mark.parametrize("mutation", [
    "record_before_plan", "missing_capture", "missing_perception",
    "duplicate_session_start", "wrong_frame_hash", "orphan_stop",
])
def test_event_chronology_and_capture_chain_rejected(demo, mutation):
    events, actions = copy.deepcopy(demo)
    if mutation == "record_before_plan":
        planned = next(i for i, e in enumerate(events) if e["kind"] == "ACTION_INTENTION_PLANNED")
        recorded = next(i for i, e in enumerate(events) if e["kind"] == "DRY_RUN_ACTION_RECORDED")
        events[planned], events[recorded] = events[recorded], events[planned]
    elif mutation == "missing_capture":
        events.remove(next(e for e in events if e["kind"] == "FRAME_CAPTURED"))
    elif mutation == "missing_perception":
        events.remove(next(e for e in events if e["kind"] == "PERCEPTION_RESULT"))
    elif mutation == "duplicate_session_start":
        events.insert(1, copy.deepcopy(events[0]))
    elif mutation == "wrong_frame_hash":
        next(e for e in events if e["kind"] == "FRAME_CAPTURED")["payload"]["image_sha256"] = "0" * 64
    elif mutation == "orphan_stop":
        events.insert(-2, {"schema_version": events[0]["schema_version"],
                           "sequence": 0, "kind": "EMERGENCY_STOP_OBSERVED",
                           "payload": {"session_id": events[0]["payload"]["session_id"],
                                       "step": 2, "phase": "BEFORE_CAPTURE"}})
    for n, event in enumerate(events, 1):
        event["sequence"] = n
    with pytest.raises((ValueError, KeyError, TypeError, ControllerError)):
        audit_offline_session(events, actions)


def test_future_backend_metadata_cannot_claim_live_installation(demo):
    events, actions = copy.deepcopy(demo)
    actions[0]["payload"]["selected_future_windows_backend"]["live_output_authorized"] = True
    with pytest.raises(ValueError):
        audit_offline_session(events, actions)


def test_next_frame_cannot_precede_prior_action_receipt(demo):
    events, actions = copy.deepcopy(demo)
    previous = next(i for i, e in enumerate(events) if e["kind"] == "DRY_RUN_ACTION_RECORDED")
    later = next(i for i, e in enumerate(events) if e["kind"] == "FRAME_CAPTURED" and
                 e["payload"]["step"] == 1)
    events[previous], events[later] = events[later], events[previous]
    for n, event in enumerate(events, 1):
        event["sequence"] = n
    with pytest.raises(ValueError):
        audit_offline_session(events, actions)
