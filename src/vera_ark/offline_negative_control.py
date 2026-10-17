"""Offline negative-control sensitivity for caller-declared paired ARK holdouts.

A negative-control outcome should be unaffected by the candidate policy but
sensitive to the same confounders. This module does not establish that premise,
authenticate outcomes, or justify subtracting the control as a causal estimate.
No capture, network, controller, or runtime effects.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any

_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")

SCHEMA = "VERA_ARK_NEGATIVE_CONTROL_DIAGNOSTIC_V1"


class NegativeControlError(ValueError):
    """Malformed paired rows or incomplete order/group support."""


@dataclass(frozen=True, slots=True)
class NegativeControlReport:
    schema: str
    holdout_pair_count: int
    holdout_group_count: int
    order_standardized_primary_delta: float
    order_standardized_negative_control_delta: float
    descriptive_primary_minus_control: float
    negative_control_same_direction: bool | None
    negative_control_dominates_primary: bool | None
    leave_one_group_out_min_primary_minus_control: float
    leave_one_group_out_max_primary_minus_control: float
    leave_one_group_out_direction_stable: bool | None
    negative_control_validity_verified: bool = False
    outcome_authenticity_verified: bool = False
    execution_order_verified: bool = False
    causal_learning_verified: bool = False
    independent_reviewed: bool = False


def evaluate_negative_control(rows: list[dict[str, Any]]) -> NegativeControlReport:
    """Compare primary and negative-control differences on *identical* pairs.

    Each row has exactly trial_id, group_id, first_arm, paired_delta,
    negative_control_delta. Both differences must be finite in [-1,1].
    Every declared group needs both execution-order cells, and at least two
    groups are required. Group and order cells are equally weighted.

    The primary-minus-control value is only a descriptive falsification probe:
    it is NOT a difference-in-differences causal estimator absent externally
    justified control validity, timing, randomization and exchangeability.
    """
    if not isinstance(rows, list) or not 1 <= len(rows) <= 4096:
        raise NegativeControlError("expected 1..4096 paired rows")
    group_values: dict[str, dict[str, list[tuple[float, float]]]] = {}
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "trial_id", "group_id", "first_arm", "paired_delta", "negative_control_delta",
        }:
            raise NegativeControlError("invalid negative-control paired row fields")
        tid, gid, arm = row["trial_id"], row["group_id"], row["first_arm"]
        if not isinstance(tid, str) or not _ID.fullmatch(tid) or tid in seen:
            raise NegativeControlError("invalid or duplicate trial_id")
        if not isinstance(gid, str) or not _ID.fullmatch(gid):
            raise NegativeControlError("invalid group_id")
        if not isinstance(arm, str) or arm not in ("BASELINE", "CANDIDATE"):
            raise NegativeControlError("invalid first_arm")
        values = []
        for key in ("paired_delta", "negative_control_delta"):
            value = row[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise NegativeControlError(f"{key} must be finite numeric")
            try:
                value = float(value)
            except (ValueError, OverflowError) as exc:
                raise NegativeControlError(f"{key} must be finite numeric") from exc
            if not math.isfinite(value) or not -1 <= value <= 1:
                raise NegativeControlError(f"{key} outside [-1,1]")
            values.append(value)
        seen.add(tid)
        arms = group_values.setdefault(gid, {"BASELINE": [], "CANDIDATE": []})
        arms[arm].append(tuple(values))
    if len(group_values) < 2:
        raise NegativeControlError("at least two groups required")
    if any(not arms[arm] for arms in group_values.values()
           for arm in ("BASELINE", "CANDIDATE")):
        raise NegativeControlError("both first-arm cells required in every group")

    def group_macro(column: int) -> float:
        return math.fsum(
            math.fsum(
                math.fsum(pair[column] for pair in arms[arm]) / len(arms[arm])
                for arm in ("BASELINE", "CANDIDATE")
            ) / 2
            for _, arms in sorted(group_values.items())
        ) / len(group_values)

    p, c = group_macro(0), group_macro(1)
    residuals = []
    for gid in sorted(group_values):
        arms = group_values[gid]
        # Pairwise subtraction first avoids subtracting separately rounded means.
        residuals.append(math.fsum(
            math.fsum(a - b for a, b in arms[arm]) / len(arms[arm])
            for arm in ("BASELINE", "CANDIDATE")
        ) / 2)
    n = len(residuals)
    residual = math.fsum(residuals) / n
    leave_one = [math.fsum(residuals[:i] + residuals[i+1:]) / (n-1) for i in range(n)]
    minimum, maximum = min(leave_one), max(leave_one)
    if residual > 0:
        stable = minimum > 0
    elif residual < 0:
        stable = maximum < 0
    else:
        stable = None
    # Direction and magnitude are different propositions. A smaller
    # same-sign control is still directionally concordant.
    same_direction = None if p == 0 or c == 0 else ((p > 0) == (c > 0))
    dominates = None if p == 0 else (same_direction is True and abs(c) >= abs(p))
    return NegativeControlReport(
        schema=SCHEMA,
        holdout_pair_count=len(rows), holdout_group_count=n,
        order_standardized_primary_delta=p,
        order_standardized_negative_control_delta=c,
        descriptive_primary_minus_control=residual,
        negative_control_same_direction=same_direction,
        negative_control_dominates_primary=dominates,
        leave_one_group_out_min_primary_minus_control=minimum,
        leave_one_group_out_max_primary_minus_control=maximum,
        leave_one_group_out_direction_stable=stable,
    )
