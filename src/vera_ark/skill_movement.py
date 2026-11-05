"""Pure, opt-in on-foot movement trial selection.

This module does not send controller reports, capture frames, or install a runtime.
It is intentionally independent of the trial-controller and perception Draft PRs.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Sequence


class MovementEvidenceError(ValueError):
    pass


class MovementDirection(StrEnum):
    FORWARD = "FORWARD"
    BACKWARD = "BACKWARD"
    LEFT = "LEFT"
    RIGHT = "RIGHT"


class MovementAssessment(StrEnum):
    UNKNOWN = "UNKNOWN"
    PROGRESS = "PROGRESS"
    NO_PROGRESS = "NO_PROGRESS"
    REGRESSION = "REGRESSION"


class AssessmentProvenance(StrEnum):
    NONE = "NONE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    STATIC_LANDMARK_REVIEW = "STATIC_LANDMARK_REVIEW"


@dataclass(frozen=True, slots=True)
class MovementTrial:
    """A reviewed trial, not a device receipt or measured world displacement."""

    direction: MovementDirection
    magnitude: float
    duration_ms: int
    neutral_release_verified: bool
    assessment: MovementAssessment = MovementAssessment.UNKNOWN
    provenance: AssessmentProvenance = AssessmentProvenance.NONE
    scene_contains_independent_landmark: bool = False
    moving_subject_is_primary_reference: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.direction, MovementDirection):
            raise MovementEvidenceError("unknown movement direction")
        if isinstance(self.magnitude, bool) or not isinstance(self.magnitude, (int, float)):
            raise MovementEvidenceError("magnitude must be numeric")
        if not isfinite(self.magnitude) or not 0 < self.magnitude <= 0.5:
            raise MovementEvidenceError("magnitude must be finite in (0, 0.5]")
        if isinstance(self.duration_ms, bool) or not isinstance(self.duration_ms, int):
            raise MovementEvidenceError("duration_ms must be an integer")
        if not 1 <= self.duration_ms <= 250:
            raise MovementEvidenceError("trial duration must be 1..250 milliseconds")
        if not isinstance(self.neutral_release_verified, bool):
            raise MovementEvidenceError("neutral release verification must be boolean")
        if not isinstance(self.assessment, MovementAssessment):
            raise MovementEvidenceError("unknown movement assessment")
        if not isinstance(self.provenance, AssessmentProvenance):
            raise MovementEvidenceError("unknown provenance")
        if not isinstance(self.scene_contains_independent_landmark, bool):
            raise MovementEvidenceError("independent landmark status must be boolean")
        if not isinstance(self.moving_subject_is_primary_reference, bool):
            raise MovementEvidenceError("primary moving reference status must be boolean")
        if self.assessment is not MovementAssessment.UNKNOWN and self.provenance is AssessmentProvenance.NONE:
            raise MovementEvidenceError("scored outcomes require review provenance")


@dataclass(frozen=True, slots=True)
class MovementProposal:
    direction: MovementDirection
    magnitude: float
    duration_ms: int
    outcome_basis: str
    manual_review_required: bool = True


def supports_movement_adjustment(trial: MovementTrial) -> bool:
    """Permit learning only from observed, released, independently anchored trials."""
    return (
        trial.neutral_release_verified
        and trial.scene_contains_independent_landmark
        and not trial.moving_subject_is_primary_reference
        and trial.provenance is not AssessmentProvenance.NONE
        and trial.assessment is not MovementAssessment.UNKNOWN
    )


def next_movement_proposal(
    trials: Sequence[MovementTrial],
    *,
    desired_direction: MovementDirection = MovementDirection.FORWARD,
) -> MovementProposal:
    """Return an experimental proposal, never permission to control ARK.

    A user-following dinosaur is not a fixed reference frame. Unknown and
    unanchored image changes cannot increase action magnitude or score.
    """
    if not isinstance(desired_direction, MovementDirection):
        raise MovementEvidenceError("desired_direction must be a MovementDirection")
    if not isinstance(trials, (tuple, list)):
        raise MovementEvidenceError("trials must be a bounded list or tuple")
    if len(trials) > 256:
        raise MovementEvidenceError("too many trials; summarize a prior episode first")
    for trial in trials:
        if not isinstance(trial, MovementTrial):
            raise MovementEvidenceError("trials contains an invalid record")
    matched = [
        trial for trial in trials
        if trial.direction is desired_direction and supports_movement_adjustment(trial)
    ]
    if not matched:
        return MovementProposal(desired_direction, 0.25, 100, "UNKNOWN_NO_STATIC_LANDMARK_EVIDENCE")
    last = matched[-1]
    if last.assessment is MovementAssessment.PROGRESS:
        return MovementProposal(
            desired_direction,
            round(min(0.5, last.magnitude + 0.05), 2),
            min(250, last.duration_ms + 20),
            "REVIEWED_PROGRESS_PROVISIONAL",
        )
    if last.assessment is MovementAssessment.REGRESSION:
        return MovementProposal(desired_direction, 0.15, 100, "REVIEWED_REGRESSION_REDUCE")
    return MovementProposal(desired_direction, 0.25, 100, "REVIEWED_NO_PROGRESS_RECALIBRATE")
