"""Bounded 2-D translation ambiguity screen for offline image-pair evidence.

This is a replay *falsifier*, not image provenance or gameplay authentication.
It may flag real repeated viewpoints and miss transformed/fabricated evidence.
No capture, controller, network, filesystem or runtime integration occurs here.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isqrt

MAX_PIXELS = 4_000_000
MAX_SHIFT = 24
CHANNEL_TOLERANCE = 2
MAX_MISMATCH_FRACTION = 0.005
MIN_OVERLAP_FRACTION = 0.50  # all shifts within min(24, dimension // 4) qualify
MAX_PIXEL_COMPARISONS = 1_000_000
RANK_GRID_SIDE = 4  # two disjoint spatial samples; rank only, never reject


@dataclass(frozen=True, slots=True)
class Translation2DCheck:
    status: str  # INVALID, TRANSLATED_PAIR_AMBIGUITY, NOT_DETECTED, BUDGET_EXCEEDED
    shift_x: int | None = None
    shift_y: int | None = None
    compared_pixels: int = 0
    mismatched_pixels: int | None = None
    checked_comparisons: int = 0


def _different(a: bytes, b: bytes, i: int, j: int) -> bool:
    return (abs(a[i] - b[j]) > CHANNEL_TOLERANCE or
            abs(a[i + 1] - b[j + 1]) > CHANNEL_TOLERANCE or
            abs(a[i + 2] - b[j + 2]) > CHANNEL_TOLERANCE)


def classify_pair_translation2d(
    first_before: bytes, first_after: bytes,
    second_before: bytes, second_after: bytes,
    width: int, height: int,
) -> Translation2DCheck:
    """Find a shared x/y shift explaining both action frames.

    A cheap fixed-grid screen bounds search cost; a positive result requires
    exhaustive overlap verification. Screening rejects only when observed
    mismatches already exceed the full-overlap mismatch allowance. This
    avoids rejecting valid near-replays merely because the fixed grid was
    disproportionately corrupted. An explicit work budget returns
    BUDGET_EXCEEDED rather than falsely reporting NOT_DETECTED when exhaustive
    checking would be too expensive. The 50% overlap floor covers every
    enumerated bounded shift; the previous 75% floor silently skipped valid
    diagonal and mixed-axis shifts. NOT_DETECTED is not authenticity evidence.
    """
    if (type(width) is not int or type(height) is not int or
            width < 64 or height < 64 or not 1024 <= width * height <= MAX_PIXELS or
            any(type(f) is not bytes or len(f) != 3 * width * height for f in
                (first_before, first_after, second_before, second_after))):
        return Translation2DCheck('INVALID')
    pairs = ((first_before, second_before), (first_after, second_after))
    comparisons = 0
    stride = max(1, isqrt(width * height // 256))
    max_dx = min(MAX_SHIFT, width // 4)
    max_dy = min(MAX_SHIFT, height // 4)
    # Rank *all* shifts using a small spatially distributed sample before
    # spending the budget on expensive exhaustive checks. The rank is only
    # a scheduling heuristic: no candidate is rejected based on it. A large
    # true shift at 512x512 otherwise starves behind thousands of near-zero
    # false shifts, even though its exact verification fits the budget.
    ranked = []
    for dy in range(-max_dy, max_dy + 1):
        for dx in range(-max_dx, max_dx + 1):
            y0, y1 = max(0, -dy), min(height, height - dy)
            x0, x1 = max(0, -dx), min(width, width - dx)
            overlap = (x1 - x0) * (y1 - y0)
            if overlap < width * height * MIN_OVERLAP_FRACTION:
                continue
            # Two differently positioned grids: poisoning the first grid
            # alone must not starve an otherwise valid replay. Ranking is
            # still heuristic; poisoning both grids can defeat it. Taking
            # the lower mismatch count is deliberately optimistic because
            # exhaustive verification, not this rank, decides a match.
            grid_bad = []
            for grid in (0, 1):
                bad = 0
                for iy in range(1, RANK_GRID_SIDE + 1):
                    if grid == 0:
                        y = y0 + (y1 - y0) * iy // (RANK_GRID_SIDE + 1)
                    else:
                        y = y0 + (y1 - y0) * (2 * iy - 1) // (2 * RANK_GRID_SIDE)
                    for ix in range(1, RANK_GRID_SIDE + 1):
                        if grid == 0:
                            x = x0 + (x1 - x0) * ix // (RANK_GRID_SIDE + 1)
                        else:
                            x = x0 + (x1 - x0) * (2 * ix - 1) // (2 * RANK_GRID_SIDE)
                        i = 3 * (y * width + x)
                        j = i + 3 * (dy * width + dx)
                        for a, b in pairs:
                            if comparisons >= MAX_PIXEL_COMPARISONS:
                                return Translation2DCheck('BUDGET_EXCEEDED', checked_comparisons=comparisons)
                            comparisons += 1
                            bad += _different(a, b, i, j)
                grid_bad.append(bad)
            ranked.append((min(grid_bad), abs(dx) + abs(dy), abs(dy), abs(dx), dy, dx))
    ranked.sort()
    for _, _, _, _, dy, dx in ranked:
        y0, y1 = max(0, -dy), min(height, height - dy)
        x0, x1 = max(0, -dx), min(width, width - dx)
        overlap = (x1 - x0) * (y1 - y0)
        if overlap < width * height * MIN_OVERLAP_FRACTION:
            continue
        compared = 2 * overlap
        max_bad = int(compared * MAX_MISMATCH_FRACTION)
        sampled = 0
        bad = 0
        sample_rows = range(y0, y1, stride)
        sample_cols = range(x0, x1, stride)
        # A sample-only percentage is unsound: 25 altered grid pixels
        # can exceed 4% of samples while remaining <0.5% of overlap.
        # A sampled mismatch is also a full-overlap mismatch, so only
        # the absolute global budget permits a sound early rejection.
        screen_max_bad = max_bad
        for y in sample_rows:
            for x in sample_cols:
                i = 3 * (y * width + x)
                j = i + 3 * (dy * width + dx)
                for a, b in pairs:
                    if comparisons >= MAX_PIXEL_COMPARISONS:
                        return Translation2DCheck('BUDGET_EXCEEDED', checked_comparisons=comparisons)
                    sampled += 1
                    comparisons += 1
                    bad += _different(a, b, i, j)
                if bad > screen_max_bad:
                    break
            if bad > screen_max_bad:
                break
        if not sampled or bad > screen_max_bad:
            continue
        mismatched = 0
        for y in range(y0, y1):
            for x in range(x0, x1):
                i = 3 * (y * width + x)
                j = i + 3 * (dy * width + dx)
                for a, b in pairs:
                    if comparisons >= MAX_PIXEL_COMPARISONS:
                        return Translation2DCheck('BUDGET_EXCEEDED', checked_comparisons=comparisons)
                    comparisons += 1
                    mismatched += _different(a, b, i, j)
                if mismatched > max_bad:
                    break
            if mismatched > max_bad:
                break
        if mismatched <= max_bad:
            return Translation2DCheck(
                'TRANSLATED_PAIR_AMBIGUITY', dx, dy, compared, mismatched, comparisons)
    return Translation2DCheck('NOT_DETECTED', checked_comparisons=comparisons)
