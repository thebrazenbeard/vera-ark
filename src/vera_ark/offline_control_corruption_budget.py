"""Bounded adversarial outcome-corruption sensitivity for offline ARK pairs.

Caller-declared, offline-only paired differences. This diagnostic asks how much
an adversary *could* change a reported primary-minus-control macro comparison
by replacing up to k complete paired outcome rows with any legal values.
It neither identifies actual corruption nor authenticates trials or learning.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from .offline_negative_control import evaluate_negative_control

SCHEMA = "VERA_ARK_CONTROL_CORRUPTION_BUDGET_V1"


@dataclass(frozen=True, slots=True)
class ControlCorruptionBudgetReport:
    schema: str
    group_count: int
    pair_count: int
    corruption_budget_pairs: int
    declared_primary_minus_control: float
    worst_case_primary_minus_control: float
    best_case_primary_minus_control: float
    minimum_pair_edits_to_erase_declared_direction: int
    declared_direction_survives_budget: bool
    largest_single_pair_downward_capacity: float
    largest_single_pair_upward_capacity: float
    worst_case_witness_trial_ids: tuple[str, ...]
    best_case_witness_trial_ids: tuple[str, ...]
    minimum_erasure_witness_trial_ids: tuple[str, ...]
    outcome_authenticity_verified: bool = False
    randomization_verified: bool = False
    causal_learning_verified: bool = False
    independent_reviewed: bool = False


def _min_edits_to_erase(value: float, capacities: list[float]) -> int:
    """Find minimum replacements needed to reach zero or reverse sign."""
    if value == 0:
        return 0
    for k in range(1, len(capacities) + 1):
        if math.fsum(capacities[:k]) >= abs(value):
            return k
    # Every row can be replaced with the opposite extremum, so unreachable
    # indicates a numerical or implementation defect, not a robustness result.
    raise ArithmeticError("bounded replacement capacity failed to reach zero")


def audit_control_corruption_budget(
    rows: list[dict[str, Any]], *, budget_pairs: int
) -> ControlCorruptionBudgetReport:
    """Compute sharp k-row outcome-replacement bounds for a frozen cell layout.

    A row's primary and control deltas are independently bounded [-1,1], so
    its residual lies in [-2,2]. Replacement changes neither trial/group/order
    identifiers nor group/order cell membership. Weight of a row is
    1 / (2 * number_of_groups * rows_in_its_order_cell).

    Greedy selection of k largest downward/upward capacities is exact because
    each row is independently replaceable and the macro estimator is linear.
    The budget is chosen by the caller, not independently pre-registered.
    """
    validated = evaluate_negative_control(rows)
    if isinstance(budget_pairs, bool) or not isinstance(budget_pairs, int):
        raise ValueError("budget_pairs must be an integer, not bool")
    if not 0 <= budget_pairs <= len(rows):
        raise ValueError("budget_pairs outside 0..number of paired rows")

    cell_counts: dict[tuple[str, str], int] = {}
    for row in rows:
        cell = (row["group_id"], row["first_arm"])
        cell_counts[cell] = cell_counts.get(cell, 0) + 1

    downward_ranked: list[tuple[float, str]] = []
    upward_ranked: list[tuple[float, str]] = []
    groups = validated.holdout_group_count
    for row in rows:
        cell = (row["group_id"], row["first_arm"])
        weight = 1.0 / (2 * groups * cell_counts[cell])
        residual = float(row["paired_delta"]) - float(row["negative_control_delta"])
        downward_ranked.append((weight * (residual + 2.0), row["trial_id"]))
        upward_ranked.append((weight * (2.0 - residual), row["trial_id"]))
    # Exact-capacity ties use trial_id rather than input iteration order.
    # Witnesses name caller-declared rows, not authenticated observations.
    downward_ranked.sort(key=lambda item: (-item[0], item[1]))
    upward_ranked.sort(key=lambda item: (-item[0], item[1]))
    downward = [capacity for capacity, _ in downward_ranked]
    upward = [capacity for capacity, _ in upward_ranked]

    value = validated.descriptive_primary_minus_control
    minimum = value - math.fsum(downward[:budget_pairs])
    maximum = value + math.fsum(upward[:budget_pairs])
    # Clip harmless roundoff beyond the true feasible estimator bounds.
    minimum = max(-2.0, minimum)
    maximum = min(2.0, maximum)
    if value > 0:
        edits = _min_edits_to_erase(value, downward)
        erasure_witness = tuple(trial_id for _, trial_id in downward_ranked[:edits])
        survives = minimum > 0
    elif value < 0:
        edits = _min_edits_to_erase(value, upward)
        erasure_witness = tuple(trial_id for _, trial_id in upward_ranked[:edits])
        survives = maximum < 0
    else:
        edits = 0
        erasure_witness = ()
        survives = False
    return ControlCorruptionBudgetReport(
        schema=SCHEMA,
        group_count=groups,
        pair_count=len(rows),
        corruption_budget_pairs=budget_pairs,
        declared_primary_minus_control=value,
        worst_case_primary_minus_control=minimum,
        best_case_primary_minus_control=maximum,
        minimum_pair_edits_to_erase_declared_direction=edits,
        declared_direction_survives_budget=survives,
        largest_single_pair_downward_capacity=downward[0],
        largest_single_pair_upward_capacity=upward[0],
        worst_case_witness_trial_ids=tuple(
            trial_id for _, trial_id in downward_ranked[:budget_pairs]
        ),
        best_case_witness_trial_ids=tuple(
            trial_id for _, trial_id in upward_ranked[:budget_pairs]
        ),
        minimum_erasure_witness_trial_ids=erasure_witness,
    )
