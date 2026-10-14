"""Pure fixed-landmark motion-evidence checks for bounded ARK movement trials.

This module does not inspect pixels, run optical flow, control a gamepad or
assert world-space velocity. Inputs are reviewed tracking measurements.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from statistics import median


class GeometryEvidenceError(ValueError):
    pass


class LateralAction(StrEnum):
    STRAFE_LEFT = "STRAFE_LEFT"
    STRAFE_RIGHT = "STRAFE_RIGHT"


class DepthBand(StrEnum):
    NEAR = "NEAR"
    FAR = "FAR"


@dataclass(frozen=True, slots=True)
class TrackedLandmark:
    landmark_id: str
    depth_band: DepthBand
    dx_pixels: float
    dy_pixels: float
    template_correlation: float
    static_reference_reviewed: bool = False

    def __post_init__(self) -> None:
        if (not isinstance(self.landmark_id, str)
                or not 1 <= len(self.landmark_id) <= 64
                or not all(c.isalnum() or c == "_" for c in self.landmark_id)):
            raise GeometryEvidenceError("landmark_id must be a bounded label")
        if not isinstance(self.depth_band, DepthBand):
            raise GeometryEvidenceError("unknown landmark depth band")
        for name in ("dx_pixels", "dy_pixels", "template_correlation"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
                raise GeometryEvidenceError(name + " must be finite")
        if abs(self.dx_pixels) > 2048 or abs(self.dy_pixels) > 2048:
            raise GeometryEvidenceError("landmark displacement out of bounds")
        if not 0 <= self.template_correlation <= 1:
            raise GeometryEvidenceError("template correlation out of range")
        if type(self.static_reference_reviewed) is not bool:
            raise GeometryEvidenceError("reviewed flag must be boolean")


@dataclass(frozen=True, slots=True)
class LandmarkFramePair:
    scene_id: str
    image_geometry: tuple[int, int]
    tracks: tuple[TrackedLandmark, ...]
    valid_before_after: bool
    neutral_release_verified: bool
    camera_orientation_stable_reviewed: bool

    def __post_init__(self) -> None:
        if (not isinstance(self.scene_id, str) or not 1 <= len(self.scene_id) <= 64
                or not all(c.isalnum() or c == "_" for c in self.scene_id)):
            raise GeometryEvidenceError("scene_id must be a bounded label")
        if (not isinstance(self.image_geometry, tuple) or len(self.image_geometry) != 2
                or any(type(v) is not int or not 200 <= v <= 4096 for v in self.image_geometry)):
            raise GeometryEvidenceError("image geometry invalid")
        if not isinstance(self.tracks, tuple) or not 1 <= len(self.tracks) <= 32:
            raise GeometryEvidenceError("tracks must be a bounded tuple")
        if any(not isinstance(track, TrackedLandmark) for track in self.tracks):
            raise GeometryEvidenceError("unknown track")
        if len({track.landmark_id for track in self.tracks}) != len(self.tracks):
            raise GeometryEvidenceError("duplicate landmark_id")
        for field in ("valid_before_after", "neutral_release_verified", "camera_orientation_stable_reviewed"):
            if type(getattr(self, field)) is not bool:
                raise GeometryEvidenceError(field + " must be boolean")


@dataclass(frozen=True, slots=True)
class MotionEvaluation:
    disposition: str
    evidence_basis: str
    median_near_dx: float | None = None
    median_far_dx: float | None = None
    usable_landmarks: int = 0
    autonomous_reward_permitted: bool = False


def assess_lateral_motion(
    action: LateralAction,
    observation: LandmarkFramePair,
    baseline: LandmarkFramePair | None,
) -> MotionEvaluation:
    """Compare fixed-landmark shifts to no-input drift; never issue a reward.

    A moving dinosaur is not a landmark. The camera may pan independently,
    and depth tags are human/reviewer-supplied, not recovered 3D positions.
    """
    if not isinstance(action, LateralAction) or not isinstance(observation, LandmarkFramePair):
        raise GeometryEvidenceError("invalid action or observation")
    if baseline is None:
        return MotionEvaluation("UNKNOWN", "NO_NO_INPUT_BASELINE")
    if not isinstance(baseline, LandmarkFramePair):
        raise GeometryEvidenceError("invalid baseline")
    if (observation.scene_id != baseline.scene_id
            or observation.image_geometry != baseline.image_geometry):
        return MotionEvaluation("UNKNOWN", "SCENE_OR_GEOMETRY_MISMATCH")
    if not all((observation.valid_before_after, observation.neutral_release_verified,
                observation.camera_orientation_stable_reviewed,
                baseline.valid_before_after, baseline.neutral_release_verified,
                baseline.camera_orientation_stable_reviewed)):
        return MotionEvaluation("UNKNOWN", "CAPTURE_RELEASE_OR_YAW_UNVERIFIED")

    refs = {track.landmark_id: track for track in baseline.tracks}
    corrected: list[tuple[DepthBand, float, float]] = []
    for track in observation.tracks:
        ref = refs.get(track.landmark_id)
        if (ref is None or track.depth_band is not ref.depth_band
                or not track.static_reference_reviewed or not ref.static_reference_reviewed
                or min(track.template_correlation, ref.template_correlation) < 0.75):
            continue
        corrected.append((
            track.depth_band, track.dx_pixels - ref.dx_pixels,
            track.dy_pixels - ref.dy_pixels,
        ))
    near = [dx for band, dx, _ in corrected if band is DepthBand.NEAR]
    far = [dx for band, dx, _ in corrected if band is DepthBand.FAR]
    if len(near) < 2 or len(far) < 2:
        return MotionEvaluation("UNKNOWN", "INSUFFICIENT_REVIEWED_DEPTH_DIVERSITY",
                                usable_landmarks=len(corrected))
    if median(abs(y) for _, _, y in corrected) > 5.0:
        return MotionEvaluation("UNKNOWN", "EXCESSIVE_VERTICAL_IMAGE_SHIFT",
                                usable_landmarks=len(corrected))
    n = float(median(near))
    f = float(median(far))
    expected_sign = 1 if action is LateralAction.STRAFE_LEFT else -1
    matching = sum(dx * expected_sign > 0 for _, dx, _ in corrected)
    if matching < len(corrected) * 0.8:
        return MotionEvaluation("UNKNOWN", "INCONSISTENT_DIRECTION",
                                n, f, len(corrected))
    if (abs(n) < 3.0 or abs(f) < 1.0 or abs(n) < abs(f) * 1.5
            or abs(n) - abs(f) < 2.5):
        return MotionEvaluation("UNKNOWN", "PARALLAX_NOT_SEPARABLE_FROM_PAN_OR_NOISE",
                                n, f, len(corrected))
    return MotionEvaluation(
        "CANDIDATE_LATERAL_TRANSLATION", "REVIEWED_REVERSED_DEPTH_PARALLAX",
        n, f, len(corrected),
    )


def assess_reversed_lateral_pair(
    left: MotionEvaluation, right: MotionEvaluation,
) -> bool:
    """Two opposite results strengthen a candidate; cannot prove world velocity."""
    if not isinstance(left, MotionEvaluation) or not isinstance(right, MotionEvaluation):
        raise GeometryEvidenceError("invalid evaluations")
    return (
        left.disposition == "CANDIDATE_LATERAL_TRANSLATION"
        and right.disposition == "CANDIDATE_LATERAL_TRANSLATION"
        and left.median_near_dx is not None and right.median_near_dx is not None
        and left.median_near_dx > 0 and right.median_near_dx < 0
        and not left.autonomous_reward_permitted and not right.autonomous_reward_permitted
    )
