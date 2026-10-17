"""Synthetic, caller-declared examples only; no observed gameplay or causality."""
from itertools import combinations
import random

import pytest

from vera_ark.offline_control_corruption_budget import (
    SCHEMA, audit_control_corruption_budget,
)
from vera_ark.offline_negative_control import NegativeControlError


def rows_for(arms):
    result = []
    for group, order_cells in arms.items():
        for arm, values in order_cells.items():
            for i, (p, c) in enumerate(values):
                result.append({"trial_id": f"{group}-{arm.lower()}-{i}",
                               "group_id": group, "first_arm": arm,
                               "paired_delta": p, "negative_control_delta": c})
    return result


def balanced(p, c=0):
    return rows_for({g: {arm: [(p, c)] for arm in ("BASELINE", "CANDIDATE")}
                     for g in ("g1", "g2")})


def test_zero_budget_preserves_declared_estimate():
    r = audit_control_corruption_budget(balanced(0.4, 0.1), budget_pairs=0)
    assert r.schema == SCHEMA
    assert r.declared_primary_minus_control == pytest.approx(0.3)
    assert r.worst_case_primary_minus_control == pytest.approx(0.3)
    assert r.best_case_primary_minus_control == pytest.approx(0.3)
    assert r.minimum_pair_edits_to_erase_declared_direction == 1
    assert r.declared_direction_survives_budget


def test_one_row_can_erase_apparent_advantage():
    r = audit_control_corruption_budget(balanced(0.4, 0.1), budget_pairs=1)
    assert r.worst_case_primary_minus_control == pytest.approx(0.3 - 2.3 / 4)
    assert r.best_case_primary_minus_control == pytest.approx(0.3 + 1.7 / 4)
    assert not r.declared_direction_survives_budget


def test_negative_declared_direction_uses_upward_capacities():
    r = audit_control_corruption_budget(balanced(-0.4, 0.1), budget_pairs=1)
    assert r.declared_primary_minus_control == pytest.approx(-0.5)
    assert r.worst_case_primary_minus_control == pytest.approx(-0.5 - 1.5 / 4)
    assert r.best_case_primary_minus_control == pytest.approx(-0.5 + 2.5 / 4)
    assert r.minimum_pair_edits_to_erase_declared_direction == 1
    assert not r.declared_direction_survives_budget


def test_zero_declared_difference_is_not_directionally_robust():
    r = audit_control_corruption_budget(balanced(0, 0), budget_pairs=0)
    assert r.minimum_pair_edits_to_erase_declared_direction == 0
    assert not r.declared_direction_survives_budget


def test_extreme_positive_requires_two_rows_to_erase():
    r = audit_control_corruption_budget(balanced(1, -1), budget_pairs=3)
    assert r.declared_primary_minus_control == 2
    assert r.minimum_pair_edits_to_erase_declared_direction == 2
    assert r.worst_case_primary_minus_control == pytest.approx(-1)
    assert not r.declared_direction_survives_budget


def test_sparse_order_cell_is_high_leverage_despite_replication_elsewhere():
    many = [(0.2, 0)] * 50
    r = audit_control_corruption_budget(rows_for({
        "g1": {"BASELINE": many, "CANDIDATE": [(0.2, 0)]},
        "g2": {"BASELINE": many, "CANDIDATE": many},
    }), budget_pairs=1)
    assert r.pair_count == 151
    assert r.minimum_pair_edits_to_erase_declared_direction == 1
    assert r.largest_single_pair_downward_capacity == pytest.approx(2.2 / 4)
    assert r.worst_case_primary_minus_control < 0


def test_caller_chosen_budget_monotone_and_bounded():
    rows = balanced(0.2, -0.1)
    reports = [audit_control_corruption_budget(rows, budget_pairs=k)
               for k in range(len(rows) + 1)]
    assert all(a.worst_case_primary_minus_control >= b.worst_case_primary_minus_control
               for a, b in zip(reports, reports[1:]))
    assert all(a.best_case_primary_minus_control <= b.best_case_primary_minus_control
               for a, b in zip(reports, reports[1:]))
    assert reports[-1].worst_case_primary_minus_control == pytest.approx(-2)
    assert reports[-1].best_case_primary_minus_control == pytest.approx(2)


def test_input_shuffle_and_nonmutation():
    rows = balanced(0.3, -0.1)
    snapshot = [dict(x) for x in rows]
    a = audit_control_corruption_budget(rows, budget_pairs=2)
    b = audit_control_corruption_budget(list(reversed(rows)), budget_pairs=2)
    assert a == b
    assert rows == snapshot


def test_false_evidence_flags():
    r = audit_control_corruption_budget(balanced(0.3), budget_pairs=1)
    assert not r.outcome_authenticity_verified
    assert not r.randomization_verified
    assert not r.causal_learning_verified
    assert not r.independent_reviewed


@pytest.mark.parametrize("budget", [-1, 5, True, False, 1.0, "1", None])
def test_invalid_budget_fails_closed(budget):
    with pytest.raises(ValueError):
        audit_control_corruption_budget(balanced(0.2), budget_pairs=budget)


@pytest.mark.parametrize("mutation", [
    lambda rows: rows[0].update(paired_delta=float('nan')),
    lambda rows: rows[0].update(negative_control_delta=float('inf')),
    lambda rows: rows[0].update(trial_id=rows[1]['trial_id']),
    lambda rows: rows[0].update(first_arm="UNKNOWN"),
    lambda rows: rows[0].update(extra="bad"),
    lambda rows: rows[0].pop("group_id"),
])
def test_malformed_rows_fail_closed(mutation):
    rows = balanced(0.2)
    mutation(rows)
    with pytest.raises(NegativeControlError):
        audit_control_corruption_budget(rows, budget_pairs=1)


def test_incomplete_order_support_rejected():
    rows = [r for r in balanced(0.2) if r['trial_id'] != 'g1-baseline-0']
    with pytest.raises(NegativeControlError):
        audit_control_corruption_budget(rows, budget_pairs=1)


def test_bruteforce_exactness_small_randomized_layouts():
    rng = random.Random(39)
    for _ in range(35):
        arms = {}
        for g in ('g1', 'g2'):
            arms[g] = {}
            for arm in ('BASELINE', 'CANDIDATE'):
                arms[g][arm] = [(rng.uniform(-1, 1), rng.uniform(-1, 1))
                                for _ in range(rng.choice((1, 2)))]
        rows = rows_for(arms)
        for budget in range(min(3, len(rows)) + 1):
            report = audit_control_corruption_budget(rows, budget_pairs=budget)
            all_scores = []
            for subset in combinations(range(len(rows)), budget):
                for extreme in (-2, 2):
                    changed = [dict(row) for row in rows]
                    for i in subset:
                        changed[i]['paired_delta'] = extreme / 2
                        changed[i]['negative_control_delta'] = -extreme / 2
                    from vera_ark.offline_negative_control import evaluate_negative_control
                    all_scores.append(evaluate_negative_control(changed).descriptive_primary_minus_control)
            assert report.worst_case_primary_minus_control == pytest.approx(min(all_scores), abs=1e-12)
            assert report.best_case_primary_minus_control == pytest.approx(max(all_scores), abs=1e-12)


def test_tiny_positive_difference_remains_positive_at_zero_budget():
    r = audit_control_corruption_budget(balanced(1e-15), budget_pairs=0)
    assert r.declared_primary_minus_control > 0
    assert r.declared_direction_survives_budget


def test_maximum_supported_row_count():
    rows = rows_for({
        "g1": {"BASELINE": [(0.2, 0)] * 1024, "CANDIDATE": [(0.2, 0)] * 1024},
        "g2": {"BASELINE": [(0.2, 0)] * 1024, "CANDIDATE": [(0.2, 0)] * 1024},
    })
    r = audit_control_corruption_budget(rows, budget_pairs=100)
    assert r.pair_count == 4096
    assert r.declared_direction_survives_budget
    assert r.minimum_pair_edits_to_erase_declared_direction > 100
