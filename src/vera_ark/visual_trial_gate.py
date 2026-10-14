"""Offline ABAB evidence gate. No controller, runtime or capture authority."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from struct import unpack
from zlib import crc32, decompressobj, error as ZlibError


@dataclass(frozen=True)
class Observation:
    phase: str
    source: str
    scene: str
    window: str
    stick_x: float
    before_ms: int
    start_ms: int
    release_ms: int
    after_ms: int
    duration_ms: int
    neutral_released: bool
    static_reviewed: bool
    tracks: int
    dx: float
    dy: float
    before_png: bytes
    after_png: bytes


@dataclass(frozen=True)
class Assessment:
    status: str
    reason: str
    evidence_digest: str | None = None
    automatic_execution_permitted: bool = False
    verified_game_effect: bool = False
    independent_reviewed: bool = False


def _valid_png(data: bytes) -> bool:
    """Check bounded noninterlaced 8-bit RGB/RGBA PNG, not provenance."""
    if type(data) is not bytes or not 45 <= len(data) <= 8_000_000 or not data.startswith(b'\x89PNG\r\n\x1a\n'):
        return False
    pos = 8
    chunks = 0
    width = height = channels = 0
    saw_ihdr = saw_idat = saw_end = False
    idat_closed = False
    compressed = bytearray()
    while pos < len(data):
        if chunks >= 64 or len(data) - pos < 12:
            return False
        n = unpack('>I', data[pos:pos + 4])[0]
        if n > len(data) - pos - 12:
            return False
        kind = data[pos + 4:pos + 8]
        if not all(65 <= c <= 90 or 97 <= c <= 122 for c in kind) or not 65 <= kind[2] <= 90:
            return False
        end = pos + 8 + n
        if crc32(data[pos + 4:end]) & 0xffffffff != unpack('>I', data[end:end + 4])[0]:
            return False
        payload = data[pos + 8:end]
        pos = end + 4
        chunks += 1
        if kind == b'IHDR':
            if chunks != 1 or saw_ihdr or n != 13:
                return False
            width, height, depth, color, comp, filt, interlace = unpack('>IIBBBBB', payload)
            if not (1 <= width <= 8192 and 1 <= height <= 8192 and width * height <= 8_000_000 and
                    depth == 8 and color in (2, 6) and comp == filt == interlace == 0):
                return False
            channels = 3 if color == 2 else 4
            saw_ihdr = True
        elif kind == b'IDAT':
            if not saw_ihdr or saw_end or idat_closed or len(compressed) + n > 8_000_000:
                return False
            compressed.extend(payload)
            saw_idat = True
        elif kind == b'IEND':
            if not saw_idat or saw_end or n or pos != len(data):
                return False
            saw_end = True
        elif not saw_ihdr or saw_end or not kind[0] & 32:
            return False
        if saw_idat and kind not in (b'IDAT', b'IEND'):
            idat_closed = True
    if not (saw_ihdr and saw_idat and saw_end):
        return False
    row = width * channels + 1
    expected = row * height
    try:
        decoder = decompressobj()
        raw = decoder.decompress(bytes(compressed), expected + 1)
        if len(raw) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            return False
        if decoder.flush():
            return False
    except ZlibError:
        return False
    return all(raw[i * row] <= 4 for i in range(height))


def assess_abab(trials: tuple[Observation, ...], *, expected_dx_sign: int) -> Assessment:
    """Accept only a frame-bound image-shift candidate, never gameplay proof."""
    def fail(reason: str) -> Assessment:
        return Assessment('INCONCLUSIVE', reason)
    if type(expected_dx_sign) is not int or expected_dx_sign not in (-1, 1):
        return fail('INVALID_DIRECTION')
    if type(trials) is not tuple or len(trials) != 4 or any(type(t) is not Observation for t in trials):
        return fail('INVALID_PACKET')
    if tuple(t.phase for t in trials) != ('IDLE', 'ACTION', 'IDLE', 'ACTION'):
        return fail('NOT_ABAB')
    if any(t.source != 'LIVE_CAPTURE' for t in trials):
        return Assessment('SYNTHETIC_OR_UNKNOWN', 'UNTRUSTED_CAPTURE_LABEL')
    if len({(t.scene, t.window) for t in trials}) != 1 or any(not t.scene or not t.window for t in trials):
        return fail('SCENE_OR_WINDOW_MISMATCH')
    if len({t.duration_ms for t in trials}) != 1:
        return fail('DURATION_MISMATCH')
    seen = set()
    for i, t in enumerate(trials):
        if (type(t.duration_ms) is not int or not 1 <= t.duration_ms <= 250 or
                type(t.tracks) is not int or not 80 <= t.tracks <= 1000 or
                type(t.neutral_released) is not bool or not t.neutral_released or
                type(t.static_reviewed) is not bool or not t.static_reviewed):
            return fail('INVALID_CONTROL_OR_REVIEW')
        if any(type(v) is not int or v < 0 for v in (t.before_ms, t.start_ms, t.release_ms, t.after_ms)):
            return fail('INVALID_TIMESTAMPS')
        if not (t.before_ms <= t.start_ms < t.release_ms <= t.after_ms and
                abs(t.release_ms - t.start_ms - t.duration_ms) <= 30 and
                t.start_ms - t.before_ms <= 1500 and t.after_ms - t.release_ms <= 1500):
            return fail('INVALID_TIMING')
        if i and trials[i - 1].after_ms >= t.before_ms:
            return fail('OVERLAPPING_TRIALS')
        if any(type(v) not in (float, int) or not isfinite(v) or abs(v) > 2048 for v in (t.stick_x, t.dx, t.dy)):
            return fail('INVALID_MEASUREMENTS')
        if not (0 <= abs(t.stick_x) <= .75) or (t.phase == 'IDLE') != (t.stick_x == 0):
            return fail('INVALID_INPUT')
        for frame in (t.before_png, t.after_png):
            if not _valid_png(frame):
                return fail('INVALID_PNG')
            digest = sha256(frame).digest()
            if digest in seen:
                return fail('DUPLICATE_FRAME')
            seen.add(digest)
    if trials[1].stick_x != trials[3].stick_x:
        return fail('ACTION_MISMATCH')
    if any(abs(trials[i].dx) > 2 or abs(trials[i].dy) > 2 for i in (0, 2)):
        return fail('UNSTABLE_IDLE')
    if any(abs(trials[i].dy) > 5 or expected_dx_sign * trials[i].dx < 7 for i in (1, 3)):
        return fail('WEAK_OR_INCONSISTENT_ACTION')
    values = [abs(trials[i].dx) for i in (1, 3)]
    if min(values) / max(values) < .35:
        return fail('ASYMMETRIC_ACTION')
    packet_digest = sha256(b''.join(sha256(f).digest() for t in trials for f in (t.before_png, t.after_png))).hexdigest()
    return Assessment('FRAME_BOUND_CANDIDATE', 'REPEATABLE_REPORTED_IMAGE_SHIFT_NOT_CAUSAL_PROOF', packet_digest)
