"""Offline exact-byte capture binding for caller-supplied T67 observations.

This is a narrow consistency check. It does not parse image pixels, authenticate
capture origin, validate signed witnesses, or prove controller causality.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import re

SCHEMA = "VERA_ARK_OFFLINE_CAPTURE_BYTE_BINDING_V1"
OBSERVATION_SCHEMA = "VERA_ARK_OFFLINE_OBSERVATION_ENVELOPE_V1"
MAX_CAPTURE_BYTES = 16 * 1024 * 1024
MAX_OBSERVATION_BYTES = 1024 * 1024
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class CaptureByteBindingAssessment:
    schema: str
    experiment_id: str
    trial_id: str
    capture_sha256: str
    capture_length: int
    exact_capture_bytes_match: bool = True
    capture_origin_authenticated: bool = False
    signed_observation_verified: bool = False
    capture_currentness_verified: bool = False
    causal_learning_verified: bool = False
    independent_review_verified: bool = False


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    obj: dict[str, object] = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def _reject_constant(token: str) -> None:
    raise ValueError("non-finite JSON constant")


def _id(value: object, label: str) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise ValueError(f"invalid {label}")
    return value


def verify_capture_byte_binding(
    observation_bytes: bytes,
    capture_bytes: bytes,
    *,
    expected_experiment_id: str,
    expected_trial_id: str,
    expected_capture_sha256: str,
) -> CaptureByteBindingAssessment:
    """Compare actual supplied capture bytes with a declared and expected digest.

    All three artifacts and the expected values are caller supplied. A matching
    fabricated capture passes. Compose with the separate T67 semantic and T65/T66
    signature checks; this function does not elevate their evidence claims.
    """
    if type(observation_bytes) is not bytes or not 0 < len(observation_bytes) <= MAX_OBSERVATION_BYTES:
        raise ValueError("observation bytes size or type invalid")
    if type(capture_bytes) is not bytes or not 0 < len(capture_bytes) <= MAX_CAPTURE_BYTES:
        raise ValueError("capture bytes size or type invalid")
    _id(expected_experiment_id, "expected experiment ID")
    _id(expected_trial_id, "expected trial ID")
    if type(expected_capture_sha256) is not str or not _SHA.fullmatch(expected_capture_sha256):
        raise ValueError("invalid expected capture digest")
    try:
        declared = json.loads(
            observation_bytes.decode("utf-8", "strict"),
            object_pairs_hook=_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, ValueError) as exc:
        raise ValueError("invalid observation JSON") from exc
    if type(declared) is not dict or declared.get("schema") != OBSERVATION_SCHEMA:
        raise ValueError("observation envelope schema mismatch")
    experiment_id = _id(declared.get("experiment_id"), "experiment ID")
    trial_id = _id(declared.get("trial_id"), "trial ID")
    declared_digest = declared.get("capture_sha256")
    if type(declared_digest) is not str or not _SHA.fullmatch(declared_digest):
        raise ValueError("invalid declared capture digest")
    if experiment_id != expected_experiment_id or trial_id != expected_trial_id:
        raise ValueError("observation identity mismatch")
    if not hmac.compare_digest(declared_digest, expected_capture_sha256):
        raise ValueError("declared capture digest differs from expected digest")
    actual_digest = hashlib.sha256(capture_bytes).hexdigest()
    if not hmac.compare_digest(actual_digest, expected_capture_sha256):
        raise ValueError("capture bytes do not match declared digest")
    return CaptureByteBindingAssessment(
        SCHEMA, experiment_id, trial_id, actual_digest, len(capture_bytes)
    )
