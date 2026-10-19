"""T72: offline, fixed-denominator trial disposition and missingness bounds.

The caller supplies the roster, dispositions, score range, and all values. This
module neither observes trials nor verifies pre-registration, scene provenance,
controller effects, or learning. It never silently drops missing/invalid trials.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
import re
from typing import Mapping

SCHEMA = "VERA_ARK_OFFLINE_TRIAL_DISPOSITION_AUDIT_V1"
MAX_TRIALS = 32
MAX_ABS_METRIC = 1_000_000.0
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z", re.ASCII)
_MISSING = frozenset(("MISSING_CAPTURE", "STOPPED", "INVALID_EVIDENCE"))


@dataclass(frozen=True, slots=True)
class TrialDispositionAssessment:
    schema: str
    trial_ids: tuple[str, ...]
    planned_count: int
    observed_count: int
    missing_capture_count: int
    stopped_count: int
    invalid_evidence_count: int
    observed_mean: float | None
    full_roster_mean_lower_bound: float
    full_roster_mean_upper_bound: float
    fixed_denominator_used: bool = True
    every_roster_id_accounted_for: bool = True
    all_trial_outcomes_observed: bool = False
    stop_or_invalid_status_authenticated: bool = False
    roster_precommitment_independently_verified: bool = False
    capture_origin_authenticated: bool = False
    selection_bias_ruled_out: bool = False
    controller_causality_verified: bool = False
    causal_learning_verified: bool = False
    independent_review_verified: bool = False


def _finite_metric(value: object, label: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a finite numeric scalar, not bool")
    try:
        numeric = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{label} must be finite and bounded") from exc
    if not math.isfinite(numeric) or abs(numeric) > MAX_ABS_METRIC:
        raise ValueError(f"{label} must be finite and bounded")
    return numeric


def _outward_mean(total: Fraction, count: int, *, lower: bool) -> float:
    """Represent the exact rational mean with a conservative binary64 endpoint.

    math.fsum minimizes rounding error but does not guarantee interval bounds.
    This checks the converted endpoint against the exact binary-input rational.
    """
    exact = total / count
    approximate = float(exact)
    rounded = Fraction.from_float(approximate)
    if lower and rounded > exact:
        return math.nextafter(approximate, -math.inf)
    if not lower and rounded < exact:
        return math.nextafter(approximate, math.inf)
    return approximate


def audit_trial_dispositions(
    expected_trial_ids: tuple[str, ...],
    trial_rows: tuple[Mapping[str, object], ...],
    *,
    metric_range: tuple[float, float],
) -> TrialDispositionAssessment:
    """Compute conservative full-roster score bounds without outcome deletion.

    A row has exactly trial_id, status, metric. OBSERVED requires a measured
    score in the declared closed metric range. MISSING_CAPTURE, STOPPED, and
    INVALID_EVIDENCE require metric=None and all contribute to the denominator.
    This audit rejects absent/extra/reordered rows instead of imputing them.

    The caller-supplied metric range is not authenticated as predeclared.
    Lower/upper bounds concern the *declared scores*, not causal effects.
    """
    if type(expected_trial_ids) is not tuple or not 1 <= len(expected_trial_ids) <= MAX_TRIALS:
        raise ValueError("invalid expected trial roster")
    if any(type(x) is not str or not _ID.fullmatch(x) for x in expected_trial_ids):
        raise ValueError("invalid expected trial ID")
    if len(set(expected_trial_ids)) != len(expected_trial_ids):
        raise ValueError("duplicate expected trial ID")
    if type(metric_range) is not tuple or len(metric_range) != 2:
        raise ValueError("metric_range must be a two-element tuple")
    low = _finite_metric(metric_range[0], "metric minimum")
    high = _finite_metric(metric_range[1], "metric maximum")
    if not low < high:
        raise ValueError("metric range must be strictly increasing")
    if type(trial_rows) is not tuple or len(trial_rows) != len(expected_trial_ids):
        raise ValueError("incomplete or oversized trial dispositions")

    counts = {"OBSERVED": 0, "MISSING_CAPTURE": 0, "STOPPED": 0, "INVALID_EVIDENCE": 0}
    values: list[float] = []
    for expected_id, row in zip(expected_trial_ids, trial_rows):
        if not isinstance(row, Mapping) or set(row) != {"trial_id", "status", "metric"}:
            raise ValueError("invalid disposition row fields")
        if type(row["trial_id"]) is not str or row["trial_id"] != expected_id:
            raise ValueError("disposition trial order or identity mismatch")
        status = row["status"]
        if type(status) is not str or status not in counts:
            raise ValueError("invalid trial disposition status")
        metric = row["metric"]
        if status == "OBSERVED":
            score = _finite_metric(metric, "observed metric")
            if not low <= score <= high:
                raise ValueError("observed metric outside declared range")
            values.append(score)
        elif status in _MISSING and metric is not None:
            raise ValueError("non-observed trial must have null metric")
        counts[status] += 1

    n = len(expected_trial_ids)
    unobserved = n - counts["OBSERVED"]
    observed_sum = math.fsum(values)
    # Preserve exact binary-input arithmetic until the final outward rounding.
    # This prevents a rounded "lower bound" from exceeding the exact minimum,
    # or an "upper bound" from falling below the exact maximum.
    exact_observed_sum = sum((Fraction.from_float(v) for v in values), Fraction(0))
    lower = _outward_mean(exact_observed_sum + unobserved * Fraction.from_float(low),
                          n, lower=True)
    upper = _outward_mean(exact_observed_sum + unobserved * Fraction.from_float(high),
                          n, lower=False)
    return TrialDispositionAssessment(
        schema=SCHEMA,
        trial_ids=expected_trial_ids,
        planned_count=n,
        observed_count=counts["OBSERVED"],
        missing_capture_count=counts["MISSING_CAPTURE"],
        stopped_count=counts["STOPPED"],
        invalid_evidence_count=counts["INVALID_EVIDENCE"],
        observed_mean=observed_sum / counts["OBSERVED"] if values else None,
        full_roster_mean_lower_bound=lower,
        full_roster_mean_upper_bound=upper,
        all_trial_outcomes_observed=(unobserved == 0),
    )
