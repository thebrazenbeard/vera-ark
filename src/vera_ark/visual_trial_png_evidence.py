"""Bounded offline PNG-sample and presentation-metadata audit.

Only caller-supplied bytes are examined. No capture authentication, rendering,
controller actuation, or gameplay conclusion can follow from this report.
"""
from __future__ import annotations

import binascii
import hashlib
import struct
import zlib

from .visual_trial_frame_binding import audit_frame_byte_binding

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_PIXELS = 4_000_000
MAX_PROFILE_BYTES = 1_048_576
MAX_IMAGE_DATA = 32_000_000
PRESENTATION_CHUNKS = frozenset((b"gAMA", b"sRGB", b"iCCP", b"cHRM", b"sBIT", b"bKGD"))
COLOR_CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}
OUTPUT_SCHEMA = "VERA_ARK_PNG_PRESENTATION_AUDIT_V1"


def _bounded_inflate(compressed: bytes, limit: int, field: str) -> bytes:
    try:
        dec = zlib.decompressobj()
        data = dec.decompress(compressed, limit + 1)
        if len(data) > limit or not dec.eof or dec.unused_data or dec.unconsumed_tail:
            raise ValueError(f"{field}: invalid or excessive decompressed data")
        extra = dec.flush(limit - len(data) + 1)
        if extra:
            data += extra
        if len(data) > limit:
            raise ValueError(f"{field}: decompression limit exceeded")
        return data
    except zlib.error as exc:
        raise ValueError(f"{field}: malformed compression") from exc


def _icc_profile(payload: bytes) -> str:
    parts = payload.split(b"\x00", 1)
    if len(parts) != 2 or not 1 <= len(parts[0]) <= 79:
        raise ValueError("iCCP: invalid profile name")
    name, remaining = parts
    if any(b < 32 or b > 126 for b in name):
        raise ValueError("iCCP: invalid profile name characters")
    if not remaining or remaining[0] != 0:
        raise ValueError("iCCP: invalid compression method")
    data = _bounded_inflate(remaining[1:], MAX_PROFILE_BYTES, "iCCP")
    if len(data) < 128 or struct.unpack(">I", data[:4])[0] != len(data) or data[36:40] != b"acsp":
        raise ValueError("iCCP: invalid ICC profile header")
    return hashlib.sha256(data).hexdigest()


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _pixels(raw: bytes, width: int, height: int, color_type: int) -> bytes:
    channels = COLOR_CHANNELS[color_type]
    stride = width * channels
    expected = height * (1 + stride)
    if len(raw) != expected:
        raise ValueError("IDAT: decompressed scanline size mismatch")
    prior = bytearray(stride)
    rgba = bytearray(width * height * 4)
    pos = out = 0
    for _ in range(height):
        filtering = raw[pos]
        pos += 1
        row = bytearray(raw[pos:pos + stride])
        pos += stride
        if filtering > 4:
            raise ValueError("IDAT: unsupported PNG row filter")
        for i in range(stride):
            a = row[i - channels] if i >= channels else 0
            b = prior[i]
            c = prior[i - channels] if i >= channels else 0
            delta = (0, a, b, (a + b) // 2, _paeth(a, b, c))[filtering]
            row[i] = (row[i] + delta) & 255
        for i in range(0, stride, channels):
            if color_type == 6:
                rgba[out:out + 4] = row[i:i + 4]
            elif color_type == 2:
                rgba[out:out + 4] = bytes((row[i], row[i + 1], row[i + 2], 255))
            elif color_type == 4:
                rgba[out:out + 4] = bytes((row[i], row[i], row[i], row[i + 1]))
            else:
                rgba[out:out + 4] = bytes((row[i], row[i], row[i], 255))
            out += 4
        prior = row
    return bytes(rgba)


def _decode_png(blob: bytes) -> tuple[str, tuple]:
    if not blob.startswith(PNG_MAGIC):
        raise ValueError("invalid PNG signature")
    pos = len(PNG_MAGIC)
    ihdr = None
    idat = bytearray()
    meta: dict[bytes, bytes] = {}
    state = "HEADER"
    while pos < len(blob):
        if len(blob) - pos < 12:
            raise ValueError("truncated PNG chunk")
        size = struct.unpack(">I", blob[pos:pos + 4])[0]
        kind = blob[pos + 4:pos + 8]
        if len(kind) != 4 or any(not (65 <= c <= 90 or 97 <= c <= 122) for c in kind):
            raise ValueError("invalid PNG chunk type")
        if size > len(blob) - pos - 12:
            raise ValueError("truncated PNG chunk payload")
        data = blob[pos + 8:pos + 8 + size]
        checksum = struct.unpack(">I", blob[pos + 8 + size:pos + 12 + size])[0]
        if (binascii.crc32(kind + data) & 0xffffffff) != checksum:
            raise ValueError("PNG CRC mismatch")
        pos += size + 12
        if state == "HEADER":
            if kind != b"IHDR" or size != 13:
                raise ValueError("PNG must start with IHDR")
            ihdr = data
            width, height, depth, ct, comp, filt, interlace = struct.unpack(">IIBBBBB", data)
            if not width or not height or width * height > MAX_PIXELS:
                raise ValueError("PNG dimensions exceed policy")
            if depth != 8 or ct not in COLOR_CHANNELS or comp or filt or interlace:
                raise ValueError("unsupported PNG color format")
            state = "BEFORE_IDAT"
            continue
        if kind == b"IHDR":
            raise ValueError("duplicate IHDR")
        if kind == b"tRNS":
            raise ValueError("tRNS: transparency-key formats are not supported")
        if kind in PRESENTATION_CHUNKS:
            if state != "BEFORE_IDAT" or kind in meta:
                raise ValueError("duplicate or misplaced PNG presentation metadata")
            meta[kind] = data
        elif kind == b"IDAT":
            if state == "AFTER_IDAT":
                raise ValueError("noncontiguous PNG IDAT")
            if len(idat) + size > MAX_IMAGE_DATA:
                raise ValueError("PNG IDAT size budget exceeded")
            idat.extend(data)
            state = "IN_IDAT"
        elif kind == b"IEND":
            if size or state not in ("IN_IDAT", "AFTER_IDAT") or pos != len(blob):
                raise ValueError("invalid PNG IEND or trailing bytes")
            break
        elif kind[0] & 32 == 0:
            raise ValueError("unsupported critical PNG chunk")
        elif state == "IN_IDAT":
            state = "AFTER_IDAT"
    else:
        raise ValueError("PNG missing IEND")
    if b"gAMA" in meta:
        data = meta[b"gAMA"]
        if len(data) != 4 or not 1 <= struct.unpack(">I", data)[0] <= 1_000_000:
            raise ValueError("gAMA: invalid or unsupported gamma")
    if b"sRGB" in meta:
        data = meta[b"sRGB"]
        if len(data) != 1 or data[0] > 3:
            raise ValueError("sRGB: invalid rendering intent")
        if b"iCCP" in meta:
            raise ValueError("sRGB and iCCP profiles conflict")
        if b"gAMA" in meta and meta[b"gAMA"] != struct.pack(">I", 45455):
            raise ValueError("sRGB and gAMA metadata conflict")
    if b"cHRM" in meta and len(meta[b"cHRM"]) != 32:
        raise ValueError("cHRM: invalid chromaticity metadata")
    if b"sRGB" in meta and b"cHRM" in meta:
        srgb_chr = struct.pack(">8I", 31270, 32900, 64000, 33000, 30000, 60000, 15000, 6000)
        if meta[b"cHRM"] != srgb_chr:
            raise ValueError("sRGB and cHRM metadata conflict")
    if b"bKGD" in meta and len(meta[b"bKGD"]) != (2 if ct in (0, 4) else 6):
        raise ValueError("bKGD: invalid background color metadata")
    if b"sBIT" in meta and (len(meta[b"sBIT"]) != COLOR_CHANNELS[ct] or
                              any(not 1 <= x <= 8 for x in meta[b"sBIT"])):
        raise ValueError("sBIT: invalid significant bits")
    if b"iCCP" in meta:
        profile = _icc_profile(meta[b"iCCP"])
        meta[b"iCCP"] = profile.encode("ascii")
    stride = width * COLOR_CHANNELS[ct]
    expected = height * (stride + 1)
    if expected > MAX_IMAGE_DATA:
        raise ValueError("PNG decoded image budget exceeded")
    samples = _pixels(_bounded_inflate(bytes(idat), expected, "IDAT"), width, height, ct)
    digest = hashlib.sha256(struct.pack(">II", width, height) + samples).hexdigest()
    presentation = tuple((k.decode("ascii"), meta[k].hex()) for k in sorted(meta))
    return digest, presentation


def audit_png_presentation(manifest: object, frames: object) -> dict:
    """Bind byte hashes, decode bounded PNGs, and detect sample/metadata disagreement.

    A claim of color-managed display equivalence is never established.
    """
    binding = audit_frame_byte_binding(manifest, frames)
    assert isinstance(frames, dict) and isinstance(manifest, dict)
    decoded = {sha: _decode_png(data) for sha, data in frames.items()}
    groups: dict[str, set[tuple]] = {}
    splits: dict[str, set[str]] = {}
    for case in manifest["cases"]:
        for sha in case["frame_sha256"]:
            pixel_digest, presentation = decoded[sha]
            groups.setdefault(pixel_digest, set()).add(presentation)
            splits.setdefault(pixel_digest, set()).add(case["split"])
    if any(len(values) > 1 for values in splits.values()):
        raise ValueError("decoded pixels cross development/holdout splits")
    disputed = sorted(digest for digest, variants in groups.items() if len(variants) > 1)
    return {
        "schema": OUTPUT_SCHEMA,
        "byte_binding_sha256": binding["binding_sha256"],
        "unique_verified_frame_count": len(decoded),
        "decoded_pixel_group_count": len(groups),
        "presentation_metadata_disagreement_group_count": len(disputed),
        "disagreement_pixel_group_sha256": disputed,
        "display_color_equivalence_verified": False,
        "capture_authenticity_verified": False,
        "controller_causality_verified": False,
        "independent_review": False,
        "status": "CALLER_SUPPLIED_PNG_SAMPLES_AUDITED",
        "claim_ceiling": "OFFLINE_SYNTHETIC_OR_CALLER_SUPPLIED_PNG_EVIDENCE_ONLY",
        "limitations": [
            "Decoded RGBA8 sample equality is not color-managed displayed-color equality.",
            "The caller may fabricate frames and labels; byte binding is not capture attestation.",
            "Only noninterlaced 8-bit grayscale, grayscale-alpha, RGB and RGBA PNG are supported.",
            "Unrecognized ancillary metadata and external rendering transforms remain unverified.",
        ],
    }
