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


@dataclass(frozen=True, slots=True)
class Translation2DCheck:
    status: str  # INVALID, TRANSLATED_PAIR_AMBIGUITY, NOT_DETECTED
    shift_x: int | None = None
    shift_y: int | None = None
    compared_pixels: int = 0
    mismatched_pixels: int | None = None


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
    exhaustive overlap verification. The grid can be adversarially poisoned,
    causing a missed match. NOT_DETECTED is *not* evidence of authenticity.
    """
    if (type(width) is not int or type(height) is not int or
            width < 64 or height < 64 or not 1024 <= width * height <= MAX_PIXELS or
            any(type(f) is not bytes or len(f) != 3 * width * height for f in
                (first_before, first_after, second_before, second_after))):
        return Translation2DCheck('INVALID')
    pairs = ((first_before, second_before), (first_after, second_after))
    stride = max(1, isqrt(width * height // 256))
    max_dx = min(MAX_SHIFT, width // 4)
    max_dy = min(MAX_SHIFT, height // 4)
    for dy in range(-max_dy, max_dy + 1):
        y0, y1 = max(0, -dy), min(height, height - dy)
        for dx in range(-max_dx, max_dx + 1):
            x0, x1 = max(0, -dx), min(width, width - dx)
            overlap = (x1 - x0) * (y1 - y0)
            if overlap < width * height * .75:
                continue
            sampled = 0
            bad = 0
            sample_rows = range(y0, y1, stride)
            sample_cols = range(x0, x1, stride)
            expected = len(sample_rows) * len(sample_cols) * 2
            screen_max_bad = max(3, int(expected * .04))
            for y in sample_rows:
                for x in sample_cols:
                    i = 3 * (y * width + x)
                    j = i + 3 * (dy * width + dx)
                    for a, b in pairs:
                        sampled += 1
                        bad += _different(a, b, i, j)
                    if bad > screen_max_bad:
                        break
                if bad > screen_max_bad:
                    break
            if not sampled or bad > screen_max_bad:
                continue
            compared = 2 * overlap
            max_bad = int(compared * MAX_MISMATCH_FRACTION)
            mismatched = 0
            for y in range(y0, y1):
                for x in range(x0, x1):
                    i = 3 * (y * width + x)
                    j = i + 3 * (dy * width + dx)
                    for a, b in pairs:
                        mismatched += _different(a, b, i, j)
                    if mismatched > max_bad:
                        break
                if mismatched > max_bad:
                    break
            if mismatched <= max_bad:
                return Translation2DCheck(
                    'TRANSLATED_PAIR_AMBIGUITY', dx, dy, compared, mismatched)
    return Translation2DCheck('NOT_DETECTED')
