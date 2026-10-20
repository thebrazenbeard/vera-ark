"""Bounded, immutable byte snapshot under an externally maintained seqlock.

This is an *offline* consistency experiment. A cooperating writer must publish
an odd epoch before every source mutation, a new even epoch after the mutation,
and linearizable/ordered epoch reads. This module cannot verify those promises.
The digest is a reproducibility checksum, not a signature or observation proof.
No retries, file/device access, network calls, or controller output.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Callable

from .offline_seqlock_snapshot import capture_with_seqlock_epoch

_MAX_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class OfflineByteSnapshot:
    """Immutable copy and its *conditional* seqlock epoch/digest evidence."""

    epoch: int
    data: bytes
    sha256_hex: str
    byte_count: int


def capture_offline_bytes_with_seqlock(
    read_epoch: Callable[[], int],
    capture: Callable[[], bytes | bytearray],
    *,
    max_bytes: int = 1024 * 1024,
) -> OfflineByteSnapshot:
    """Copy caller bytes inside one stable-even seqlock check, without retry.

    Rejects unsupported data, oversized snapshots, bad callbacks, and invalid
    epochs. A frozen/dishonest counter can still yield an inconsistent result.
    The returned immutable bytes can be retained even if the source changes
    later; this does not establish source authenticity or a real atomic read.
    """
    if type(max_bytes) is not int or not 1 <= max_bytes <= _MAX_BYTES:
        raise ValueError("max_bytes must be an exact int from 1 to 16777216")
    if not callable(read_epoch):
        raise ValueError("read_epoch must be callable")
    if not callable(capture):
        raise ValueError("capture must be callable")

    epochs: list[int] = []

    def observed_epoch() -> int:
        epoch = read_epoch()
        epochs.append(epoch)
        return epoch

    def copy_capture() -> bytes:
        source = capture()
        if type(source) not in (bytes, bytearray):
            raise ValueError("capture must return exact bytes or bytearray")
        if len(source) > max_bytes:
            raise ValueError("capture exceeds max_bytes")
        frozen = bytes(source)
        # A concurrent bytearray resize during copy is not trusted.
        if len(frozen) > max_bytes:
            raise ValueError("capture exceeds max_bytes")
        return frozen

    frozen = capture_with_seqlock_epoch(observed_epoch, copy_capture)
    return OfflineByteSnapshot(
        epoch=epochs[0], data=frozen, sha256_hex=sha256(frozen).hexdigest(),
        byte_count=len(frozen),
    )
