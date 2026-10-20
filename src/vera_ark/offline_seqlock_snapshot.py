"""Bounded offline read protocol for an externally maintained seqlock epoch.

The cooperating writer MUST publish an odd epoch before changing any source
field, publish the next even epoch only after all changes are visible, and
make epoch reads linearizable with respect to those writes. No epoch wrap may
occur during a capture. This helper cannot enforce those writer guarantees.

A stable even epoch supports only a *conditional source-consistency* claim.
It does not authenticate trial declarations, guarantee cross-process memory
ordering, attest to an external observation, prove gameplay causality, or
independently verify the supplied capture function. No retries or I/O here.
"""
from __future__ import annotations

from typing import Callable, TypeVar

_T = TypeVar("_T")
_MAX_EPOCH = (1 << 64) - 1


def _read_epoch(read_epoch: Callable[[], int]) -> int:
    try:
        value = read_epoch()
    except Exception as exc:
        raise RuntimeError("offline seqlock epoch read failed") from exc
    if type(value) is not int or not 0 <= value <= _MAX_EPOCH:
        raise ValueError("offline seqlock epoch must be an exact uint64")
    return value


def capture_with_seqlock_epoch(
    read_epoch: Callable[[], int],
    capture: Callable[[], _T],
) -> _T:
    """Run capture once only when the surrounding epoch is unchanged/even.

    This is an opt-in offline wrapper, not a synchronization primitive: the
    external writer must obey the documented odd/write/even publication
    protocol. A non-cooperating or malicious writer can make this check pass
    for an inconsistent snapshot. On any failed check, no result is returned.
    """
    if not callable(read_epoch):
        raise ValueError("read_epoch must be callable")
    if not callable(capture):
        raise ValueError("capture must be callable")
    before = _read_epoch(read_epoch)
    if before & 1:
        raise RuntimeError("offline seqlock writer active before capture")
    result = capture()
    after = _read_epoch(read_epoch)
    if before != after:
        raise RuntimeError("offline seqlock epoch changed during capture")
    if after & 1:
        raise RuntimeError("offline seqlock writer active after capture")
    return result
