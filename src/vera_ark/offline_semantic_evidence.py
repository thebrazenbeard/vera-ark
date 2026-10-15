"""Offline semantic/DS4 evidence oracle. Never accesses a controller.

Second contract implementation; not an independent reviewer.
"""
from __future__ import annotations

from .controller import VHFDS4SubmissionBatchV1
from .models import ActionIntention, ActionType
from .offline_session_audit import audit_offline_session

_NEUTRAL = bytes.fromhex("018080808008" + "00" * 58)


def _axis(value: float, *, invert: bool = False) -> int:
    if invert:
        value = -value
    return max(0, min(255, round((value + 1.0) * 127.5)))


def contract_expected_reports(intention: ActionIntention) -> tuple[tuple[bytes, int], ...]:
    """Build exact serialized reports from the published DS4 v1 contract."""
    if intention.action_type is ActionType.RELEASE_ALL:
        raise ValueError("terminal release belongs to session audit")
    if intention.action_type is ActionType.NOOP:
        return ((_NEUTRAL, 0),)
    active = bytearray(_NEUTRAL)
    if intention.action_type is ActionType.MOVE:
        active[1] = _axis(intention.x)
        active[2] = _axis(intention.y, invert=True)
    elif intention.action_type is ActionType.LOOK:
        active[3] = _axis(intention.x)
        active[4] = _axis(intention.y, invert=True)
    elif intention.action_type is ActionType.INTERACT:
        active[5] = 0x28  # D-pad neutral | Cross
    else:
        raise ValueError("unsupported semantic action")
    return ((bytes(active), 0), (_NEUTRAL, max(1, intention.duration_ms)))


def audit_offline_semantic_binding(events: object, actions: object) -> dict:
    """Verify declared actions against raw reports; no device-effect claim."""
    result = audit_offline_session(events, actions)
    checked_actions = 0
    nonneutral_batches_checked = 0
    for row in actions:
        if row["kind"] == "RELEASE_ALL":
            continue
        intention = ActionIntention.from_dict(row["payload"]["intention"])
        expected = contract_expected_reports(intention)
        first = row["payload"]["transport_receipts"][0]
        _, observed = VHFDS4SubmissionBatchV1.deserialize(
            bytes.fromhex(first["submission_hex"])
        )
        if observed != expected:
            raise ValueError("semantic action does not match serialized DS4 bytes")
        checked_actions += 1
        if any(report != _NEUTRAL for report, _ in expected):
            nonneutral_batches_checked += 1
    return {
        **result,
        "semantic_report_byte_binding_verified": checked_actions > 0,
        "semantic_actions_checked": checked_actions,
        "nonneutral_report_batches_checked": nonneutral_batches_checked,
        "nonneutral_report_binding_checked": nonneutral_batches_checked > 0,
        "semantic_binding_status": ("CHECKED" if checked_actions else "NOT_APPLICABLE_NO_ACTIONS"),
        "semantic_oracle": "CONTRACT_DERIVED_SECOND_IMPLEMENTATION_V1",
        "independent_review": False,
    }
