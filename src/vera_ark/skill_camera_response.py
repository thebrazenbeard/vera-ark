"""Pure camera response bracketing from reviewed, same-scene image tracks.

This is a *trial planner*, not a camera-speed estimator, controller, or runtime.
Pixel drift is not angular degrees. Every result requires a separate dispatcher
and observer before executing a new input.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


class YawResponseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class YawObservation:
    scene_id: str
    stick_x: float
    duration_ms: int
    median_static_dx: float
    median_static_dy: float
    valid_tracks: int
    capture_valid: bool
    neutral_release_verified: bool
    static_scene_reviewed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.scene_id, str) or not 1 <= len(self.scene_id) <= 64:
            raise YawResponseError("scene_id must be bounded")
        for name in ("stick_x", "median_static_dx", "median_static_dy"):
            val = getattr(self, name)
            if isinstance(val, bool) or not isinstance(val, (float, int)) or not isfinite(val):
                raise YawResponseError(f"{name} must be finite")
        if not 0 < abs(self.stick_x) <= .75:
            raise YawResponseError("stick_x must be nonzero and <= 0.75")
        if abs(self.median_static_dx) > 2048 or abs(self.median_static_dy) > 2048:
            raise YawResponseError("image shift out of bounds")
        if type(self.duration_ms) is not int or not 1 <= self.duration_ms <= 250:
            raise YawResponseError("duration must be 1..250ms")
        if type(self.valid_tracks) is not int or not 0 <= self.valid_tracks <= 1000:
            raise YawResponseError("track count out of bounds")
        for name in ("capture_valid", "neutral_release_verified", "static_scene_reviewed"):
            if type(getattr(self, name)) is not bool:
                raise YawResponseError(f"{name} must be boolean")


@dataclass(frozen=True, slots=True)
class YawAssessment:
    disposition: str
    reason: str
    experimental_magnitude: float | None = None
    automatic_execution_permitted: bool = False
    angular_degrees_known: bool = False


def _usable(pulse: YawObservation) -> bool:
    return (
        pulse.valid_tracks >= 80 and pulse.capture_valid
        and pulse.neutral_release_verified and pulse.static_scene_reviewed
    )


def assess_yaw_reversal(
    negative_x: YawObservation,
    positive_x: YawObservation,
    *,
    idle_median_dx: float | None = None,
) -> YawAssessment:
    """Reversal strengthens a yaw candidate, but never proves camera angles."""
    if not isinstance(negative_x, YawObservation) or not isinstance(positive_x, YawObservation):
        raise YawResponseError("observations required")
    if negative_x.stick_x >= 0 or positive_x.stick_x <= 0:
        raise YawResponseError("observations must have opposite signed input in order")
    if negative_x.scene_id != positive_x.scene_id:
        return YawAssessment("UNKNOWN", "SCENE_MISMATCH")
    if not (_usable(negative_x) and _usable(positive_x)):
        return YawAssessment("UNKNOWN", "INVALID_OR_UNREVIEWED_FRAME")
    if idle_median_dx is not None:
        if isinstance(idle_median_dx, bool) or not isinstance(idle_median_dx, (int, float)) or not isfinite(idle_median_dx):
            raise YawResponseError("idle drift must be finite")
        if abs(idle_median_dx) > 2:
            return YawAssessment("UNKNOWN", "UNSTABLE_IDLE_REFERENCE")
    dx_neg, dx_pos = negative_x.median_static_dx, positive_x.median_static_dx
    if abs(negative_x.median_static_dy) > 5 or abs(positive_x.median_static_dy) > 5:
        return YawAssessment("UNKNOWN", "VERTICAL_DRIFT_OR_SCENE_CHANGE")
    if dx_neg < 7 or dx_pos > -7:
        return YawAssessment("UNKNOWN", "WEAK_OR_INCONSISTENT_REVERSAL")
    ratio = dx_neg / abs(dx_pos)
    if not .35 <= ratio <= 2.85:
        return YawAssessment("UNKNOWN", "ASYMMETRIC_YAW_OR_CAPTURE_ERROR")
    return YawAssessment("CANDIDATE_REVERSIBLE_YAW", "OPPOSITE_STATIC_IMAGE_SHIFTS")


def next_yaw_response_probe(
    weak: YawObservation,
    strong: YawObservation,
) -> YawAssessment:
    """Bracket observed response amplitude, not a universal controller deadzone."""
    if not isinstance(weak, YawObservation) or not isinstance(strong, YawObservation):
        raise YawResponseError("observations required")
    if weak.scene_id != strong.scene_id or weak.stick_x * strong.stick_x <= 0:
        return YawAssessment("UNKNOWN", "SCENE_OR_AXIS_DIRECTION_MISMATCH")
    if not (_usable(weak) and _usable(strong)):
        return YawAssessment("UNKNOWN", "INVALID_OR_UNREVIEWED_FRAME")
    if weak.duration_ms != strong.duration_ms:
        return YawAssessment("UNKNOWN", "INPUT_DURATION_NOT_CONTROLLED")
    if not 0 < abs(weak.stick_x) < abs(strong.stick_x):
        return YawAssessment("UNKNOWN", "MAGNITUDES_NOT_ORDERED")
    if abs(weak.median_static_dx) > 1.5 or abs(strong.median_static_dx) < 7:
        return YawAssessment("UNKNOWN", "NO_RELIABLE_WEAK_STRONG_BRACKET")
    if abs(weak.median_static_dy) > 5 or abs(strong.median_static_dy) > 5:
        return YawAssessment("UNKNOWN", "VERTICAL_DRIFT_OR_SCENE_CHANGE")
    return YawAssessment(
        "CANDIDATE_INTERMEDIATE_PROBE",
        "REVIEWED_SAME_SCENE_RESPONSE_BRACKET",
        round((abs(weak.stick_x) + abs(strong.stick_x)) / 2, 3),
    )
