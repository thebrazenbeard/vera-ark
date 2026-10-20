"""Fail-closed verification of a *stored* offline byte snapshot.

This verifies only internal receipt consistency, optionally against an
independently supplied expected digest and byte count. Neither the stored
receipt nor a caller-provided expectation authenticates capture origins.
The source seqlock writer's protocol is not verified here. No I/O or effects.
"""
from __future__ import annotations

from hashlib import sha256
from hmac import compare_digest
import re

from .offline_seqlock_byte_binding import OfflineByteSnapshot

_SHA256_LOWER = re.compile(r"[0-9a-f]{64}\Z")
_MAX_BYTES = 16 * 1024 * 1024
_MAX_EPOCH = (1 << 64) - 1


def _canonical_digest(value: object) -> bool:
    return type(value) is str and _SHA256_LOWER.fullmatch(value) is not None


def verify_offline_byte_snapshot(
    snapshot: OfflineByteSnapshot,
    *,
    expected_sha256_hex: str | None = None,
    expected_byte_count: int | None = None,
) -> None:
    """Reject malformed or corrupted receipts; return None on consistency.

    Expectations must come from a separately justified provenance path to
    add any assurance beyond self-consistency. Coordinated fabrication can
    still pass even when both expectations are provided by the same actor.
    """
    if type(snapshot) is not OfflineByteSnapshot:
        raise ValueError("snapshot must be an exact OfflineByteSnapshot")
    if type(snapshot.epoch) is not int or not 0 <= snapshot.epoch <= _MAX_EPOCH or snapshot.epoch & 1:
        raise ValueError("snapshot epoch must be an exact even uint64")
    if type(snapshot.data) is not bytes:
        raise ValueError("snapshot data must be exact bytes")
    if type(snapshot.byte_count) is not int or not 0 <= snapshot.byte_count <= _MAX_BYTES:
        raise ValueError("snapshot byte_count must be an exact bounded int")
    if not _canonical_digest(snapshot.sha256_hex):
        raise ValueError("snapshot digest must be lowercase SHA-256 hex")
    if expected_sha256_hex is not None and not _canonical_digest(expected_sha256_hex):
        raise ValueError("expected_sha256_hex must be lowercase SHA-256 hex")
    if expected_byte_count is not None and (type(expected_byte_count) is not int or
                                            not 0 <= expected_byte_count <= _MAX_BYTES):
        raise ValueError("expected_byte_count must be an exact bounded int")
    if len(snapshot.data) != snapshot.byte_count:
        raise ValueError("snapshot byte count mismatch")
    actual = sha256(snapshot.data).hexdigest()
    if not compare_digest(actual, snapshot.sha256_hex):
        raise ValueError("snapshot digest mismatch")
    if expected_byte_count is not None and expected_byte_count != snapshot.byte_count:
        raise ValueError("expected byte count mismatch")
    if expected_sha256_hex is not None and not compare_digest(actual, expected_sha256_hex):
        raise ValueError("expected digest mismatch")
