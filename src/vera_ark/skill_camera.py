"""Evidence-bounded camera calibration for ARK, with no controller side effects."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Sequence


class CameraEvidenceError(ValueError):
    pass


class CameraDirection(StrEnum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"


class CameraAssessment(StrEnum):
    UNKNOWN = "UNKNOWN"
    OBSERVED_TURN = "OBSERVED_TURN"
    NO_TURN = "NO_TURN"
    WRONG_DIRECTION = "WRONG_DIRECTION"


class CameraProvenance(StrEnum):
    NONE = "NONE"
    SCENE_REVIEW = "SCENE_REVIEW"
    HUMAN_REVIEW = "HUMAN_REVIEW"


@dataclass(frozen=True, slots=True)
class CameraTrial:
    input_direction: CameraDirection
    magnitude: float
    duration_ms: int
    neutral_release_verified: bool
    landmark_is_static: bool
    landmark_shift_direction: CameraDirection | None = None
    assessment: CameraAssessment = CameraAssessment.UNKNOWN
    provenance: CameraProvenance = CameraProvenance.NONE

    def __post_init__(self) -> None:
        if not isinstance(self.input_direction, CameraDirection):
            raise CameraEvidenceError("invalid input direction")
        if isinstance(self.magnitude, bool) or not isinstance(self.magnitude, (int, float)):
            raise CameraEvidenceError("magnitude must be numeric")
        if not isfinite(self.magnitude) or not 0 < self.magnitude <= 0.75:
            raise CameraEvidenceError("magnitude must be finite and within (0, 0.75]")
        if isinstance(self.duration_ms, bool) or not isinstance(self.duration_ms, int):
            raise CameraEvidenceError("duration_ms must be an integer")
        if not 1 <= self.duration_ms <= 250:
            raise CameraEvidenceError("duration_ms must be 1..250")
        if not isinstance(self.neutral_release_verified, bool) or not isinstance(self.landmark_is_static, bool):
            raise CameraEvidenceError("boolean verification fields required")
        if self.landmark_shift_direction is not None and not isinstance(self.landmark_shift_direction, CameraDirection):
            raise CameraEvidenceError("landmark shift must be LEFT, RIGHT, or None")
        if not isinstance(self.assessment, CameraAssessment) or not isinstance(self.provenance, CameraProvenance):
            raise CameraEvidenceError("unknown assessment/provenance")
        if self.assessment is not CameraAssessment.UNKNOWN and self.provenance is CameraProvenance.NONE:
            raise CameraEvidenceError("assessment requires review provenance")


@dataclass(frozen=True, slots=True)
class CameraProposal:
    direction: CameraDirection
    magnitude: float
    duration_ms: int
    evidence_basis: str
    automatic_execution_permitted: bool = False


def evidence_consistent_with_yaw(trial: CameraTrial) -> bool:
    """A static landmark drifts opposite the direction of camera rotation."""
    return (
        trial.neutral_release_verified
        and trial.landmark_is_static
        and trial.provenance is not CameraProvenance.NONE
        and trial.assessment is CameraAssessment.OBSERVED_TURN
        and trial.landmark_shift_direction is not None
        and trial.landmark_shift_direction is not trial.input_direction
    )


def next_camera_proposal(
    trials: Sequence[CameraTrial],
    *,
    desired_direction: CameraDirection = CameraDirection.RIGHT,
) -> CameraProposal:
    """Adapt a short yaw trial only after static-landmark evidence.

    Frame RGB delta cannot prove yaw, quantify degrees, or identify collisions.
    """
    if not isinstance(desired_direction, CameraDirection):
        raise CameraEvidenceError("invalid desired camera direction")
    if not isinstance(trials, (list, tuple)) or len(trials) > 256:
        raise CameraEvidenceError("trials must be bounded list/tuple")
    for trial in trials:
        if not isinstance(trial, CameraTrial):
            raise CameraEvidenceError("invalid camera trial")
    reliable = [
        trial for trial in trials
        if trial.input_direction is desired_direction
        and evidence_consistent_with_yaw(trial)
    ]
    if not reliable:
        return CameraProposal(desired_direction, 0.35, 100, "UNKNOWN_NO_INDEPENDENT_LANDMARK")
    last = reliable[-1]
    return CameraProposal(
        desired_direction,
        round(min(0.75, last.magnitude + 0.05), 2),
        min(250, last.duration_ms + 20),
        "REVIEWED_STATIC_LANDMARK_YAW_PROVISIONAL",
    )
