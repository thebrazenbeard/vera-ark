"""Qualified offline ABAB entrypoint: refuse cross-frame geometry changes."""
from __future__ import annotations
from struct import unpack
from .visual_trial_gate import Assessment, Observation, assess_abab


def assess_abab_strict(trials: tuple[Observation, ...], *, expected_dx_sign: int) -> Assessment:
    """Only a same-dimension, frame-bound candidate can pass this gate.

    Dimensions are checked after the underlying PNG validator accepts every
    frame. Even this stricter candidate does not authenticate capture origin,
    reported optical flow, neutral release, or a real gameplay effect.
    """
    result = assess_abab(trials, expected_dx_sign=expected_dx_sign)
    if result.status != 'FRAME_BOUND_CANDIDATE':
        return result
    dimensions = {unpack('>II', frame[16:24]) for trial in trials
                  for frame in (trial.before_png, trial.after_png)}
    if len(dimensions) != 1:
        return Assessment('INCONCLUSIVE', 'FRAME_DIMENSION_MISMATCH')
    return result
