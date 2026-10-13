"""Experimental vertical-stick motion discrimination from pre-reviewed optical flow.

This accepts aggregate observations, not live frames, 3D coordinates or controller
reports. It may propose a movement hypothesis, never gameplay reward or authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite


class AxialEvidenceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FlowBands:
    """Image-space median displacement of upper/lower tracked static features."""
    upper_dx: float
    upper_dy: float
    lower_dx: float
    lower_dy: float
    upper_count: int
    lower_count: int

    def __post_init__(self) -> None:
        for field in ("upper_dx", "upper_dy", "lower_dx", "lower_dy"):
            v = getattr(self, field)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) or abs(v) > 2048:
                raise AxialEvidenceError(field + " must be finite image displacement")
        for field in ("upper_count", "lower_count"):
            v = getattr(self, field)
            if type(v) is not int or not 1 <= v <= 4096:
                raise AxialEvidenceError(field + " must be a bounded feature count")


@dataclass(frozen=True, slots=True)
class AxialEpisode:
    scene_id: str
    image_geometry: tuple[int, int]
    flow: FlowBands
    capture_valid: bool
    neutral_release_verified: bool
    camera_orientation_stable_reviewed: bool
    pulse_duration_ms: int
    pulse_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.scene_id, str) or not 1 <= len(self.scene_id) <= 64:
            raise AxialEvidenceError("scene_id invalid")
        if (not isinstance(self.image_geometry, tuple) or len(self.image_geometry) != 2
                or any(type(v) is not int or not 200 <= v <= 4096 for v in self.image_geometry)):
            raise AxialEvidenceError("image geometry invalid")
        if not isinstance(self.flow, FlowBands):
            raise AxialEvidenceError("flow must be measured FlowBands")
        for name in ("capture_valid", "neutral_release_verified", "camera_orientation_stable_reviewed"):
            if type(getattr(self, name)) is not bool:
                raise AxialEvidenceError(name + " must be boolean")
        if (type(self.pulse_duration_ms) is not int or not 1 <= self.pulse_duration_ms <= 250
                or type(self.pulse_count) is not int or not 0 <= self.pulse_count <= 4):
            raise AxialEvidenceError("pulse bounds exceeded")
        if self.pulse_count == 0 and not self.neutral_release_verified:
            raise AxialEvidenceError("idle baseline must be neutral")


@dataclass(frozen=True, slots=True)
class AxialPairAssessment:
    disposition: str
    basis: str
    forward_near_vector: tuple[float, float] | None = None
    backward_near_vector: tuple[float, float] | None = None
    candidate_only: bool = True
    automatic_reward_permitted: bool = False


def assess_opposite_vertical_input(
    idle: AxialEpisode | None, forward: AxialEpisode, backward: AxialEpisode,
) -> AxialPairAssessment:
    """Evaluate reversed near-field motion relative to an idle baseline.

    Upper/lower image bands approximate different depths but are NOT measured
    object distances. An independently reviewed stable camera is required.
    """
    if not isinstance(forward, AxialEpisode) or not isinstance(backward, AxialEpisode):
        raise AxialEvidenceError("forward/backward episodes required")
    if idle is None:
        return AxialPairAssessment("UNKNOWN", "IDLE_BASELINE_REQUIRED")
    if not isinstance(idle, AxialEpisode):
        raise AxialEvidenceError("idle episode invalid")
    if (len({ep.scene_id for ep in (idle, forward, backward)}) != 1
            or len({ep.image_geometry for ep in (idle, forward, backward)}) != 1):
        return AxialPairAssessment("UNKNOWN", "SCENE_OR_GEOMETRY_MISMATCH")
    if not all(ep.capture_valid and ep.neutral_release_verified and ep.camera_orientation_stable_reviewed
               for ep in (idle, forward, backward)):
        return AxialPairAssessment("UNKNOWN", "CAPTURE_RELEASE_OR_CAMERA_UNVERIFIED")
    if idle.pulse_count != 0 or forward.pulse_count == 0 or backward.pulse_count == 0:
        return AxialPairAssessment("UNKNOWN", "CONTROL_PROTOCOL_MISMATCH")
    if any(ep.flow.upper_count < 60 or ep.flow.lower_count < 60 for ep in (idle, forward, backward)):
        return AxialPairAssessment("UNKNOWN", "TOO_FEW_TRACKED_FEATURES")
    baseline_near = hypot(idle.flow.lower_dx, idle.flow.lower_dy)
    baseline_far = hypot(idle.flow.upper_dx, idle.flow.upper_dy)
    if max(baseline_near, baseline_far) > 1.5:
        return AxialPairAssessment("UNKNOWN", "EXCESSIVE_IDLE_DRIFT")

    def corrected(ep: AxialEpisode) -> tuple[tuple[float, float], float]:
        near = (ep.flow.lower_dx - idle.flow.lower_dx,
                ep.flow.lower_dy - idle.flow.lower_dy)
        far = hypot(ep.flow.upper_dx - idle.flow.upper_dx,
                    ep.flow.upper_dy - idle.flow.upper_dy)
        return near, far

    front, front_far = corrected(forward)
    back, back_far = corrected(backward)
    flen, blen = hypot(*front), hypot(*back)
    if flen < 3.0 or blen < 3.0:
        return AxialPairAssessment("UNKNOWN", "MOTION_BELOW_MEASUREMENT_THRESHOLD", front, back)
    if flen < 1.5 * front_far or blen < 1.5 * back_far:
        return AxialPairAssessment("UNKNOWN", "NO_NEAR_FAR_MOTION_DIFFERENCE", front, back)
    opposition = (front[0] * back[0] + front[1] * back[1]) / (flen * blen)
    if opposition > -0.75:
        return AxialPairAssessment("UNKNOWN", "RESPONSES_NOT_NEAR_OPPOSITE", front, back)
    return AxialPairAssessment(
        "CANDIDATE_OPPOSED_VERTICAL_MOVEMENT",
        "IDLE_CORRECTED_OPPOSED_FOREGROUND_PARALLAX",
        front, back,
    )
