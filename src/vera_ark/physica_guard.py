"""Optional fail-closed Physica collision-candidate guard for dry-run ARK MOVE.

This adapter needs explicit hypothesized world coordinates/calibration.
It does not emit controller input, infer camera orientation, or claim contact.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .models import ActionIntention, ActionType, SchemaError


@dataclass(frozen=True, slots=True)
class MotionGuardDecision:
    status: str
    potential_obstacle_ids: tuple[str, ...] = ()


class MotionGuardBlocked(SchemaError):
    """A possible intersection or unavailable model refuses a MOVE."""


class PhysicaMotionGuard:
    def __init__(self, *, position_m: tuple[float, float],
                 calibration: object, radius_m: float = 0.0,
                 obstacles: Sequence[object] = ()) -> None:
        # Physica is optional; keep offline ARK usable without it.
        from physica.ark_bridge import MotionCalibration
        if not isinstance(calibration, MotionCalibration):
            raise TypeError("explicit Physica MotionCalibration required")
        self.position_m = position_m
        self.calibration = calibration
        self.radius_m = radius_m
        self.obstacles = tuple(obstacles)

    def __call__(self, intention: object) -> MotionGuardDecision:
        if type(intention) is not ActionIntention or intention.dry_run is not True:
            raise MotionGuardBlocked("validated dry-run ActionIntention required")
        if intention.action_type is not ActionType.MOVE:
            return MotionGuardDecision("NOT_APPLICABLE_NON_MOVE")
        from physica.ark_bridge import predict_ark_move
        try:
            candidate = predict_ark_move(
                intention.to_dict(), position_m=self.position_m,
                calibration=self.calibration, radius_m=self.radius_m,
                obstacles=self.obstacles,
            )
        except (ValueError, TypeError, OverflowError) as exc:
            raise MotionGuardBlocked("motion prediction unavailable; MOVE refused") from exc
        if candidate.potential_obstacle_ids:
            raise MotionGuardBlocked(
                "potential obstacle overlap; MOVE refused: "
                + ",".join(candidate.potential_obstacle_ids)
            )
        return MotionGuardDecision("NO_BROAD_PHASE_CANDIDATES")
