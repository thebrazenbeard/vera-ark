"""Offline pixel-content replay gate for ABAB visual-trial candidates.

PNG file hashes distinguish *encodings*, not images. This gate checks that
all eight already-validated frames decode to distinct opaque RGB images. It never
attests capture origin, image displacement, controller effects, or game state.
No image libraries, controller backend, file I/O, or network access are used.
"""
from __future__ import annotations

from hashlib import sha256
from struct import unpack
from zlib import decompressobj, error as ZlibError

from .visual_trial_gate import Assessment, Observation
from .visual_trial_gate_strict import assess_abab_strict


_MAX_PIXELS = 4_000_000  # offline resource budget; 2560x1440 fits


def _unfiltered_pixel_digest(data: bytes) -> bytes | None:
    """Hash normalized pixels, ignoring PNG metadata, compression and filters.

    Called only after assess_abab_strict has checked CRCs, chunk order, PNG
    parameters, scanline bounds and dimensions. This is deliberately private:
    it is not a stand-alone PNG decoder or untrusted-file parser.
    """
    width, height, depth, color, _, _, interlace = unpack('>IIBBBBB', data[16:29])
    if (width * height > _MAX_PIXELS or depth != 8 or color not in (2, 6)
            or interlace != 0):
        return None
    bpp = 3 if color == 2 else 4
    stride = width * bpp
    expected = (stride + 1) * height
    pos = 8
    compressed = bytearray()
    while pos < len(data):
        size = unpack('>I', data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        if kind == b'IDAT':
            compressed.extend(data[pos + 8:pos + 8 + size])
        pos += 12 + size
    try:
        decoder = decompressobj()
        raw = decoder.decompress(bytes(compressed), expected + 1)
        if (len(raw) != expected or not decoder.eof or decoder.unused_data
                or decoder.unconsumed_tail or decoder.flush()):
            return None
    except (ZlibError, ValueError):
        return None

    h = sha256()
    h.update(data[16:24])  # width and height
    # Canonicalize opaque RGBA to RGB, so an RGB->RGBA re-encoding cannot
    # evade replay detection. A screenshot with nonopaque alpha is ambiguous
    # without a specified compositing background; fail closed.
    previous = bytearray(stride)
    for row_index in range(height):
        offset = row_index * (stride + 1)
        filter_kind = raw[offset]
        current = bytearray(raw[offset + 1:offset + 1 + stride])
        if filter_kind == 1:  # Sub
            for i in range(bpp, stride):
                current[i] = (current[i] + current[i - bpp]) & 255
        elif filter_kind == 2:  # Up
            for i in range(stride):
                current[i] = (current[i] + previous[i]) & 255
        elif filter_kind == 3:  # Average
            for i in range(stride):
                left = current[i - bpp] if i >= bpp else 0
                current[i] = (current[i] + ((left + previous[i]) // 2)) & 255
        elif filter_kind == 4:  # Paeth
            for i in range(stride):
                a = current[i - bpp] if i >= bpp else 0
                b = previous[i]
                c = previous[i - bpp] if i >= bpp else 0
                p = a + b - c
                da, db, dc = abs(p - a), abs(p - b), abs(p - c)
                predictor = a if da <= db and da <= dc else b if db <= dc else c
                current[i] = (current[i] + predictor) & 255
        elif filter_kind != 0:
            return None
        if bpp == 4:
            if any(a != 255 for a in current[3::4]):
                return None
            h.update(bytes(current[i] for i in range(stride) if i % 4 != 3))
        else:
            h.update(current)
        previous = current
    return h.digest()


def assess_abab_pixel_bound(
    trials: tuple[Observation, ...], *, expected_dx_sign: int,
) -> Assessment:
    """Reject re-encoded/re-filtered image replay; return candidate at most.

    This check is a necessary evidence hygiene condition, not optical flow
    measurement. An attacker can fabricate distinct moving-looking frames.
    """
    result = assess_abab_strict(trials, expected_dx_sign=expected_dx_sign)
    if result.status != 'FRAME_BOUND_CANDIDATE':
        return result
    fingerprints: set[bytes] = set()
    for trial in trials:
        for frame in (trial.before_png, trial.after_png):
            digest = _unfiltered_pixel_digest(frame)
            if digest is None:
                return Assessment('INCONCLUSIVE', 'PIXEL_DECODING_OR_RESOURCE_LIMIT')
            if digest in fingerprints:
                return Assessment('INCONCLUSIVE', 'REENCODED_OR_IDENTICAL_PIXEL_REPLAY')
            fingerprints.add(digest)
    return Assessment('PIXEL_DISTINCT_CANDIDATE',
                      'DISTINCT_OPAQUE_PIXELS_REPORTED_SHIFT_NOT_CAUSAL_PROOF',
                      result.evidence_digest)
