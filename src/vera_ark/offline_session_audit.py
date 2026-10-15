"""Fail-closed offline audit of one declared Vera ARK dry-run session.

No device access, ledger writes, screenshot authentication, or live-input claims.
"""
from __future__ import annotations

import hashlib

from .controller import (
    DS4_LOOPBACK_BACKEND, DS4_REPORT_CONTRACT, DS4_SELECTED_WINDOWS_BACKEND,
    DS4USBReportV1, VHFDS4SubmissionBatchV1,
)
from .models import ActionIntention, ActionType

SCHEMA = "VERA_ARK_OFFLINE_SESSION_AUDIT_V1"
LEDGER_SCHEMA = "VERA_ARK_OPERATIONAL_EVENT_V1"
MAX_RECORDS = 50_000


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def _records(rows: object, name: str) -> list[dict]:
    _require(type(rows) is list and 1 <= len(rows) <= MAX_RECORDS,
             f"{name}: invalid record count")
    for index, row in enumerate(rows, 1):
        _require(type(row) is dict and row.get("schema_version") == LEDGER_SCHEMA,
                 f"{name}: invalid record schema")
        _require(type(row.get("sequence")) is int and row["sequence"] == index,
                 f"{name}: noncontiguous sequence")
        _require(type(row.get("kind")) is str and type(row.get("payload")) is dict,
                 f"{name}: malformed event")
    return rows


def _hex_bytes(value: object, field: str) -> bytes:
    _require(type(value) is str and len(value) % 2 == 0, f"invalid {field}")
    try:
        data = bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError(f"invalid {field}") from exc
    _require(data.hex() == value, f"noncanonical {field}")
    return data


def _verify_action(row: dict, session_id: str, batch_sequence: int) -> tuple[ActionIntention, dict, int]:
    kind, payload = row["kind"], row["payload"]
    _require(kind in ("ACTION_INTENTION_DRY_RUN", "RELEASE_ALL"), "unexpected action kind")
    _require(payload.get("controller") == "dry-run-ds4-loopback-v1" and
             payload.get("selected_future_windows_backend") == DS4_SELECTED_WINDOWS_BACKEND,
             "controller or future-backend declaration drift")
    intention = ActionIntention.from_dict(payload["intention"])
    _require(intention.session_id == session_id, "action session mismatch")
    _require((intention.action_type is ActionType.RELEASE_ALL) == (kind == "RELEASE_ALL"),
             "release kind mismatch")
    receipt = payload["receipt"]
    _require(type(receipt) is dict, "invalid controller receipt")
    _require(receipt.get("intention_id") == intention.intention_id and
             receipt.get("session_id") == session_id and receipt.get("step") == intention.step,
             "controller receipt mismatch")
    _require(receipt.get("transport_backend") == DS4_LOOPBACK_BACKEND and
             receipt.get("report_contract") == DS4_REPORT_CONTRACT and
             receipt.get("loopback_verified") is True and
             type(receipt.get("external_inputs_sent")) is int and
             receipt["external_inputs_sent"] == 0,
             "controller receipt lacks dry-run evidence")
    transports = payload.get("transport_receipts")
    _require(type(transports) is list and 1 <= len(transports) <= 8 and
             type(receipt.get("reports_serialized")) is int and
             receipt["reports_serialized"] == len(transports),
             "transport count mismatch")
    batch_sequence += 1
    first = transports[0]
    _require(type(first) is dict, "invalid transport receipt")
    submission = _hex_bytes(first.get("submission_hex"), "submission_hex")
    parsed_sequence, parsed_reports = VHFDS4SubmissionBatchV1.deserialize(submission)
    _require(parsed_sequence == batch_sequence and len(parsed_reports) == len(transports),
             "batch sequence or count mismatch")
    submission_sha = hashlib.sha256(submission).hexdigest()
    for transport, (report, offset_ms) in zip(transports, parsed_reports):
        _require(type(transport) is dict, "invalid transport receipt")
        _require(transport.get("backend") == DS4_LOOPBACK_BACKEND and
                 transport.get("report_contract") == DS4_REPORT_CONTRACT and
                 transport.get("loopback_verified") is True and
                 type(transport.get("external_inputs_sent")) is int and
                 transport["external_inputs_sent"] == 0,
                 "transport receipt lacks dry-run evidence")
        _require(type(transport.get("batch_sequence")) is int and
                 transport["batch_sequence"] == batch_sequence and
                 type(transport.get("offset_ms")) is int and
                 transport["offset_ms"] == offset_ms,
                 "transport batch or offset mismatch")
        _require(transport.get("submission_hex") == first["submission_hex"] and
                 transport.get("submission_sha256") == submission_sha,
                 "submission bytes or digest mismatch")
        _require(_hex_bytes(transport.get("report_hex"), "report_hex") == report and
                 transport.get("report_sha256") == hashlib.sha256(report).hexdigest(),
                 "report bytes or digest mismatch")
        _require(transport.get("decoded_state") ==
                 DS4USBReportV1.verify_round_trip(report).to_dict(),
                 "decoded DS4 state mismatch")
    if kind == "RELEASE_ALL":
        _require(len(parsed_reports) == 1 and
                 parsed_reports[0] == (DS4USBReportV1.neutral_report(), 0) and
                 payload.get("neutral_report_hex") == DS4USBReportV1.neutral_report().hex() and
                 receipt.get("disposition") == "VERIFIED_NEUTRAL_DS4_REPORT_NO_EXTERNAL_INPUT",
                 "terminal release is not exact neutral")
    else:
        _require(receipt.get("disposition") ==
                 "DS4_REPORTS_LOOPBACK_VERIFIED_NO_EXTERNAL_INPUT",
                 "invalid dry-run disposition")
    return intention, receipt, batch_sequence


def audit_offline_session(events: object, actions: object) -> dict:
    """Check declared one-session ledger consistency, not capture or device provenance."""
    events = _records(events, "events")
    actions = _records(actions, "actions")
    _require(events[0]["kind"] == "SESSION_STARTED" and
             events[-1]["kind"] == "SESSION_ENDED" and
             events[-2]["kind"] == "FORCED_RELEASE_RECORDED",
             "incomplete session envelope")
    start, end = events[0]["payload"], events[-1]["payload"]
    session_id = start.get("session_id")
    _require(type(session_id) is str and bool(session_id) and
             end.get("session_id") == session_id, "session identity mismatch")
    config = start.get("config")
    _require(type(config) is dict and
             config.get("controller_backend") == "dry-run-ds4-loopback-v1" and
             type(config.get("steps")) is int and config["steps"] >= 1 and
             end.get("requested_steps") == config["steps"], "session config mismatch")
    _require(type(end.get("completed_steps")) is int and
             type(end.get("stopped")) is bool and
             end.get("release_recorded") is True and
             type(end.get("external_inputs_sent")) is int and
             end["external_inputs_sent"] == 0, "invalid terminal session declaration")
    _require(actions[-1]["kind"] == "RELEASE_ALL" and
             all(a["kind"] == "ACTION_INTENTION_DRY_RUN" for a in actions[:-1]),
             "missing or misplaced terminal release")
    planned = [e for e in events if e["kind"] == "ACTION_INTENTION_PLANNED"]
    recorded = [e for e in events if e["kind"] == "DRY_RUN_ACTION_RECORDED"]
    _require(len(recorded) == len(actions) - 1 ==
             end["completed_steps"] and len(planned) >= len(recorded),
             "action/event count mismatch")
    allowed = {
        "SESSION_STARTED", "FRAME_CAPTURED", "PERCEPTION_RESULT",
        "ACTION_INTENTION_PLANNED", "OPTIONAL_MEMORY_IGNORED",
        "PLANNER_FALLBACK", "PHYSICA_MOTION_GUARD",
        "DRY_RUN_ACTION_RECORDED", "EMERGENCY_STOP_OBSERVED",
        "FORCED_RELEASE_RECORDED", "SESSION_ENDED",
    }
    _require(all(e["kind"] in allowed for e in events), "unexpected event kind")
    for kind in ("SESSION_STARTED", "SESSION_ENDED", "FORCED_RELEASE_RECORDED"):
        _require(sum(e["kind"] == kind for e in events) == 1,
                 "duplicated session envelope event")
    positions = {
        kind: [(index, e) for index, e in enumerate(events) if e["kind"] == kind]
        for kind in ("FRAME_CAPTURED", "PERCEPTION_RESULT",
                     "ACTION_INTENTION_PLANNED", "DRY_RUN_ACTION_RECORDED",
                     "EMERGENCY_STOP_OBSERVED")
    }
    frames = positions["FRAME_CAPTURED"]
    perceptions = positions["PERCEPTION_RESULT"]
    plans = positions["ACTION_INTENTION_PLANNED"]
    executed = positions["DRY_RUN_ACTION_RECORDED"]
    stops = positions["EMERGENCY_STOP_OBSERVED"]
    _require(len(frames) == len(perceptions) == len(plans) and
             len(plans) <= config["steps"], "incomplete frame/perception chain")
    _require(len(stops) <= 1 and end["stopped"] == bool(stops),
             "stop declaration mismatch")
    _require(
        (end["stopped"] and len(recorded) < config["steps"]) or
        (not end["stopped"] and len(recorded) == config["steps"]),
        "session completion/stop mismatch")
    if stops:
        stop_index, stop = stops[0]
        _require(stop_index < len(events) - 2 and
                 stop["payload"].get("session_id") == session_id and
                 stop["payload"].get("step") == len(recorded) and
                 stop["payload"].get("phase") in ("BEFORE_CAPTURE", "BEFORE_ACTION"),
                 "invalid stop evidence")
    for step, ((frame_pos, frame), (perception_pos, perception),
               (plan_pos, plan)) in enumerate(zip(frames, perceptions, plans)):
        f, p, a = frame["payload"], perception["payload"], plan["payload"]
        _require(frame_pos < perception_pos < plan_pos < len(events) - 2,
                 "capture/perception/plan order mismatch")
        _require(f.get("session_id") == session_id and f.get("step") == step and
                 p.get("session_id") == session_id and p.get("step") == step and
                 a.get("session_id") == session_id and a.get("step") == step and
                 f.get("image_sha256") == p.get("image_sha256") and
                 p.get("perception_id") == a.get("perception_id"),
                 "capture/perception/plan binding mismatch")
        ActionIntention.from_dict(a)
        if step < len(executed):
            _require(plan_pos < executed[step][0] < len(events) - 2,
                     "action recorded before plan")
    for step in range(len(executed) - 1):
        _require(executed[step][0] < frames[step + 1][0],
                 "next frame precedes prior action receipt")
    if stops and executed:
        _require(executed[-1][0] < stops[0][0],
                 "stop precedes last completed action")
    if len(plans) > len(executed):
        _require(len(plans) == len(executed) + 1 and len(stops) == 1 and
                 stops[0][1]["payload"]["phase"] == "BEFORE_ACTION" and
                 plans[-1][0] < stops[0][0], "unexecuted plan without before-action stop")
    elif stops:
        _require(stops[0][1]["payload"]["phase"] == "BEFORE_CAPTURE",
                 "before-action stop without unexecuted plan")
    batch_sequence = 0
    seen_ids: set[str] = set()
    for step, action in enumerate(actions):
        intention, receipt, batch_sequence = _verify_action(action, session_id, batch_sequence)
        _require(intention.intention_id not in seen_ids, "duplicate intention id")
        seen_ids.add(intention.intention_id)
        if action["kind"] == "RELEASE_ALL":
            _require(intention.step == end["completed_steps"] and
                     events[-2]["payload"] == receipt,
                     "forced release event mismatch")
        else:
            _require(intention.step == step and
                     planned[step]["payload"] == intention.to_dict() and
                     recorded[step]["payload"] == receipt,
                     "planned/executed action mismatch")
    _require(len(planned) <= len(recorded) + 1,
             "extra unexecuted plans")
    return {
        "schema": SCHEMA,
        "status": "DECLARED_DRY_RUN_LEDGER_SELF_CONSISTENT",
        "session_id": session_id,
        "completed_steps": end["completed_steps"],
        "verified_serialized_batches": batch_sequence,
        "terminal_neutral_release_declared_and_byte_checked": True,
        "declared_external_inputs_sent": 0,
        "capture_authenticity_verified": False,
        "live_controller_route_verified": False,
        "controller_causality_verified": False,
        "independent_review": False,
        "claim_ceiling": "CALLER_SUPPLIED_OFFLINE_LEDGER_CONSISTENCY_ONLY",
    }
