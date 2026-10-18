"""Offline exact group-label sensitivity conditional on *declared* exchangeability blocks.

A block is caller supplied and is NOT evidence of authentic scene identity,
randomization, or chronological exchangeability. No controller or runtime path.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations, product
import math
import re
from typing import Any, Iterator

SCHEMA = "VERA_ARK_BLOCKED_GROUP_REASSIGNMENT_V1"
_KEYS = frozenset({"trial_id", "group_id", "block_id", "first_arm", "paired_delta", "negative_control_delta"})
_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_ARMS = ("BASELINE", "CANDIDATE")


@dataclass(frozen=True, slots=True)
class BlockedReassignmentAudit:
    schema: str
    pair_count: int
    group_count: int
    block_count: int
    assignments_examined: int
    declared_fraction: str
    worst_case_fraction: str
    best_case_fraction: str
    declared_sign: int
    minimum_label_changes_to_erase_direction: int | None
    worst_case_changed_trial_ids: tuple[str, ...]
    best_case_changed_trial_ids: tuple[str, ...]
    minimum_erasure_changed_trial_ids: tuple[str, ...]
    observation_authenticity_verified: bool = False
    exchangeability_verified: bool = False
    randomization_verified: bool = False
    causal_learning_verified: bool = False
    independently_reviewed: bool = False


def _parse(rows: Any, max_pairs: int) -> list[tuple[str, str, str, str, Fraction]]:
    if type(max_pairs) is not int or not 4 <= max_pairs <= 8:
        raise ValueError("max_pairs must be an integer in 4..8")
    if type(rows) is not list or not 4 <= len(rows) <= max_pairs:
        raise ValueError("expected 4..max_pairs rows")
    parsed = []
    seen = set()
    for row in rows:
        if type(row) is not dict or row.keys() != _KEYS:
            raise ValueError("invalid row schema")
        tid, group, block, arm = (row[k] for k in ("trial_id", "group_id", "block_id", "first_arm"))
        if any(type(x) is not str or not _ID.fullmatch(x) for x in (tid, group, block)):
            raise ValueError("invalid trial, group or block identifier")
        if tid in seen:
            raise ValueError("duplicate trial_id")
        if type(arm) is not str or arm not in _ARMS:
            raise ValueError("invalid first_arm")
        values = []
        for key in ("paired_delta", "negative_control_delta"):
            v = row[key]
            if type(v) not in (int, float) or not -1 <= v <= 1 or (type(v) is float and not math.isfinite(v)):
                raise ValueError("invalid numeric field: " + key)
            values.append(Fraction(v))
        parsed.append((tid, group, block, arm, values[0] - values[1]))
        seen.add(tid)
    groups = {r[1] for r in parsed}
    cells = {(r[1], r[3]) for r in parsed}
    if len(groups) < 2 or cells != {(g, a) for g in groups for a in _ARMS}:
        raise ValueError("at least two groups with both first arms required")
    return sorted(parsed)


def _allocations(ids: tuple[str, ...], quotas: tuple[tuple[str, int], ...]) -> Iterator[dict[str, str]]:
    if not quotas:
        if ids:
            raise ValueError("quota mismatch")
        yield {}
        return
    group, n = quotas[0]
    for chosen in combinations(ids, n):
        remaining = tuple(t for t in ids if t not in chosen)
        for tail in _allocations(remaining, quotas[1:]):
            yield {**tail, **dict.fromkeys(chosen, group)}


def audit_blocked_reassignment(rows: list[dict[str, Any]], *, max_pairs: int = 8) -> BlockedReassignmentAudit:
    """Enumerate only within declared (block_id, first_arm) strata, preserving counts."""
    parsed = _parse(rows, max_pairs)
    groups = sorted({r[1] for r in parsed})
    blocks = sorted({r[2] for r in parsed})
    counts = {(g, a): sum(1 for _, gg, _, aa, _ in parsed if (gg, aa) == (g, a))
              for g in groups for a in _ARMS}
    options = []
    for block in blocks:
        for arm in _ARMS:
            part = [r for r in parsed if r[2] == block and r[3] == arm]
            if not part:
                continue
            ids = tuple(r[0] for r in part)
            quotas = tuple((g, sum(r[1] == g for r in part)) for g in groups if any(r[1] == g for r in part))
            options.append(tuple(_allocations(ids, quotas)))
    declared = sum((delta / (2 * len(groups) * counts[(g, a)])
                    for _, g, _, a, delta in parsed), Fraction())
    sign = (declared > 0) - (declared < 0)
    low = high = None
    low_key = high_key = None
    erasure = None
    seen = 0
    for choices in product(*options):
        assignment = {tid: g for chunk in choices for tid, g in chunk.items()}
        score = sum((delta / (2 * len(groups) * counts[(assignment[tid], arm)])
                     for tid, _, _, arm, delta in parsed), Fraction())
        changed = tuple(tid for tid, g, _, _, _ in parsed if assignment[tid] != g)
        assignment_key = tuple((tid, assignment[tid]) for tid, _, _, _, _ in parsed)
        key = (changed, assignment_key)
        if low is None or score < low or (score == low and key < low_key):
            low, low_key = score, key
        if high is None or score > high or (score == high and key < high_key):
            high, high_key = score, key
        if sign and (score <= 0 if sign > 0 else score >= 0):
            candidate = (len(changed), changed, assignment_key)
            if erasure is None or candidate < erasure:
                erasure = candidate
        seen += 1
    assert low is not None and high is not None
    return BlockedReassignmentAudit(
        schema=SCHEMA, pair_count=len(parsed), group_count=len(groups), block_count=len(blocks),
        assignments_examined=seen, declared_fraction=str(declared),
        worst_case_fraction=str(low), best_case_fraction=str(high), declared_sign=sign,
        minimum_label_changes_to_erase_direction=erasure[0] if erasure else None,
        worst_case_changed_trial_ids=low_key[0], best_case_changed_trial_ids=high_key[0],
        minimum_erasure_changed_trial_ids=erasure[1] if erasure else (),
    )
