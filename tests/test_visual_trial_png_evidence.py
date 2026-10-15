import binascii
import hashlib
import struct
import zlib

import pytest

from vera_ark.capture import encode_rgba_png
from vera_ark.visual_trial_png_evidence import audit_png_presentation


def chunk(kind, data):
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", binascii.crc32(body) & 0xffffffff)


def add_chunks(image, chunks):
    at = image.index(b"IDAT") - 4
    return image[:at] + b"".join(chunk(k, v) for k, v in chunks) + image[at:]


def gamma(value):
    return (b"gAMA", struct.pack(">I", value))


def image(r=17):
    return encode_rgba_png(1, 1, bytes((r, 42, 73, 255)))


def evidence(*groups):
    cases, frames = [], {}
    for n, (split, images) in enumerate(groups):
        digests = []
        for blob in images:
            digest = hashlib.sha256(blob).hexdigest()
            frames[digest] = blob
            digests.append(digest)
        cases.append({
            "case_id": f"case-{n}", "split": split, "capture_group": f"group-{n}",
            "frame_sha256": [digests[i % len(digests)] for i in range(4)],
            "reference_label": "NON_REPLAY_LIKE", "reference_basis": "SYNTHETIC_CONSTRUCTION",
        })
    return {"schema": "VERA_ARK_REPLAY_BENCHMARK_V1",
            "evaluator_sha256": "a" * 64, "cases": cases}, frames


def test_same_samples_different_gamma_warn_not_display_equivalence():
    a = add_chunks(image(), [gamma(45455)])
    b = add_chunks(image(), [gamma(50000)])
    manifest, frames = evidence(("development", [a, b]))
    result = audit_png_presentation(manifest, frames)
    assert result["decoded_pixel_group_count"] == 1
    assert result["presentation_metadata_disagreement_group_count"] == 1
    assert result["display_color_equivalence_verified"] is False


def test_text_metadata_alone_does_not_trigger_presentation_warning():
    a = add_chunks(image(), [(b"tEXt", b"note\x00a")])
    b = add_chunks(image(), [(b"tEXt", b"note\x00b")])
    result = audit_png_presentation(*evidence(("development", [a, b])))
    assert result["presentation_metadata_disagreement_group_count"] == 0


def test_reencoded_same_pixels_cannot_cross_development_holdout():
    a = image()
    b = add_chunks(image(), [(b"tEXt", b"note\x00b")])
    with pytest.raises(ValueError, match="decoded.*cross"):
        audit_png_presentation(*evidence(("development", [a]), ("holdout", [b])))


@pytest.mark.parametrize("bad", [0, 1_000_001])
def test_invalid_gamma_rejected(bad):
    with pytest.raises(ValueError, match="gAMA"):
        audit_png_presentation(*evidence(("development", [add_chunks(image(), [gamma(bad)])])))


def test_srgb_gamma_conflict_rejected():
    blob = add_chunks(image(), [(b"sRGB", bytes([0])), gamma(50000)])
    with pytest.raises(ValueError, match="sRGB.*gAMA"):
        audit_png_presentation(*evidence(("development", [blob])))


def test_profile_conflict_rejected():
    icc = b"Example\x00\x00" + zlib.compress(bytes(128))
    blob = add_chunks(image(), [(b"sRGB", bytes([0])), (b"iCCP", icc)])
    with pytest.raises(ValueError, match="sRGB.*iCCP"):
        audit_png_presentation(*evidence(("development", [blob])))


def test_malformed_icc_rejected():
    icc = b"Example\x00\x00" + zlib.compress(b"bad")
    with pytest.raises(ValueError, match="iCCP"):
        audit_png_presentation(*evidence(("development", [add_chunks(image(), [(b"iCCP", icc)])])))


def test_icc_decompression_bomb_rejected():
    icc = b"Example\x00\x00" + zlib.compress(b"A" * 1_100_000)
    with pytest.raises(ValueError, match="iCCP"):
        audit_png_presentation(*evidence(("development", [add_chunks(image(), [(b"iCCP", icc)])])))


def test_invalid_crc_rejected():
    blob = bytearray(image())
    blob[-5] ^= 1
    with pytest.raises(ValueError, match="CRC"):
        audit_png_presentation(*evidence(("development", [bytes(blob)])))


def test_trns_must_not_be_ignored_as_opaque_samples():
    a = image()
    # tRNS affects decoding; unsupported alpha-key formats must fail closed.
    b = add_chunks(a, [(b"tRNS", b"\x00\x11")])
    with pytest.raises(ValueError, match="tRNS"):
        audit_png_presentation(*evidence(("development", [b])))


def test_background_chunk_disagreement_counts_as_presentation_metadata():
    a = add_chunks(image(), [(b"bKGD", b"\x00\x01\x00\x02\x00\x03")])
    b = add_chunks(image(), [(b"bKGD", b"\x00\x03\x00\x02\x00\x01")])
    result = audit_png_presentation(*evidence(("development", [a, b])))
    assert result["presentation_metadata_disagreement_group_count"] == 1


def test_srgb_chromaticity_conflict_fails_closed():
    wrong = struct.pack(">8I", 31270, 32900, 64000, 33000, 30000, 60000, 15000, 6200)
    blob = add_chunks(image(), [(b"sRGB", b"\x00"), (b"cHRM", wrong)])
    with pytest.raises(ValueError, match="sRGB.*cHRM"):
        audit_png_presentation(*evidence(("development", [blob])))


def test_srgb_standard_chromaticity_is_consistent():
    standard = struct.pack(">8I", 31270, 32900, 64000, 33000, 30000, 60000, 15000, 6000)
    blob = add_chunks(image(), [(b"sRGB", b"\x00"), (b"cHRM", standard), gamma(45455)])
    assert audit_png_presentation(*evidence(("development", [blob])))["decoded_pixel_group_count"] == 1


@pytest.mark.parametrize("metadata", [
    [(b"sRGB", b"")], [(b"sRGB", b"\x04")],
    [(b"gAMA", b"\x01")], [(b"gAMA", b"\x00\x00\x00\x00")],
    [(b"cHRM", b"x")], [(b"sBIT", b"\x08")],
    [(b"sBIT", b"\x08\x08\x08\x00")], [(b"iCCP", b"bad")],
])
def test_malformed_metadata_rejected(metadata):
    blob = add_chunks(image(), metadata)
    with pytest.raises(ValueError):
        audit_png_presentation(*evidence(("development", [blob])))


@pytest.mark.parametrize("kind", [b"sRGB", b"gAMA", b"cHRM", b"sBIT", b"iCCP"])
def test_duplicate_presentation_chunk_rejected(kind):
    data = {
        b"sRGB": b"\x00", b"gAMA": struct.pack(">I", 45455),
        b"cHRM": struct.pack(">8I", *(0 for _ in range(8))),
        b"sBIT": b"\x08" * 4, b"iCCP": b"Name\x00\x00junk",
    }[kind]
    blob = add_chunks(image(), [(kind, data), (kind, data)])
    with pytest.raises(ValueError, match="duplicate"):
        audit_png_presentation(*evidence(("development", [blob])))


def test_garbage_after_iend_rejected():
    with pytest.raises(ValueError, match="IEND"):
        audit_png_presentation(*evidence(("development", [image() + b"junk"])))


def test_truncated_png_rejected():
    with pytest.raises(ValueError):
        audit_png_presentation(*evidence(("development", [image()[:-7]])))


def test_unsupported_interlace_rejected():
    blob = image()
    header = bytearray(blob[16:29])
    header[-1] = 1
    changed = PNG_SIGNATURE() + chunk(b"IHDR", bytes(header)) + blob[33:]
    with pytest.raises(ValueError, match="unsupported"):
        audit_png_presentation(*evidence(("development", [changed])))


def PNG_SIGNATURE():
    return b"\x89PNG\r\n\x1a\n"


def test_different_rgba_pixels_produce_separate_groups():
    result = audit_png_presentation(*evidence(("development", [image(17), image(18)])))
    assert result["decoded_pixel_group_count"] == 2
    assert result["presentation_metadata_disagreement_group_count"] == 0


def test_cross_split_exact_frame_reuse_fails_binding():
    with pytest.raises(ValueError, match="exact frame hash crosses"):
        audit_png_presentation(*evidence(("development", [image()]), ("holdout", [image()])))


def test_invalid_declared_digest_fails_binding():
    manifest, frames = evidence(("development", [image()]))
    digest = next(iter(frames))
    with pytest.raises(ValueError, match="frame byte SHA-256 mismatch"):
        audit_png_presentation(manifest, {digest: image(18)})


def test_source_claim_never_upgraded_from_synthetic():
    result = audit_png_presentation(*evidence(("development", [image()])))
    assert result["capture_authenticity_verified"] is False
    assert result["controller_causality_verified"] is False
    assert result["independent_review"] is False
    assert result["claim_ceiling"] == "OFFLINE_SYNTHETIC_OR_CALLER_SUPPLIED_PNG_EVIDENCE_ONLY"


def png_8bit(width, height, color_type, rows, filter_type=0):
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]
    encoded = bytearray()
    previous = bytes(width * channels)
    for row in rows:
        encoded.append(filter_type)
        for index, value in enumerate(row):
            a = row[index - channels] if index >= channels else 0
            b = previous[index]
            c = previous[index - channels] if index >= channels else 0
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            predictor = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
            filters = (0, a, b, (a + b) // 2, predictor)
            encoded.append((value - filters[filter_type]) % 256)
        previous = row
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return PNG_SIGNATURE() + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(encoded))) + chunk(b"IEND", b"")


@pytest.mark.parametrize("filter_type", [0, 1, 2, 3, 4])
def test_all_standard_filters_decode_to_same_rgba_samples(filter_type):
    first = bytes((10, 20, 30, 255, 40, 50, 60, 255))
    second = bytes((30, 40, 50, 255, 70, 80, 90, 255))
    reference = encode_rgba_png(2, 2, first + second)
    alternative = png_8bit(2, 2, 6, [first, second], filter_type)
    result = audit_png_presentation(*evidence(("development", [reference, alternative])))
    assert result["decoded_pixel_group_count"] == 1


@pytest.mark.parametrize("color_type,channels", [(0, bytes([77])), (2, bytes([77,77,77])), (4, bytes([77,255]))])
def test_opaque_grayscale_and_rgb_normalize_to_rgba(color_type, channels):
    opaque = encode_rgba_png(1, 1, bytes([77, 77, 77, 255]))
    alternative = png_8bit(1, 1, color_type, [channels])
    assert audit_png_presentation(*evidence(("development", [opaque, alternative])))["decoded_pixel_group_count"] == 1


def test_valid_icc_profile_is_accepted_and_compared():
    profile = bytearray(128)
    profile[:4] = struct.pack(">I", len(profile))
    profile[36:40] = b"acsp"
    a = add_chunks(image(), [(b"iCCP", b"profile\x00\x00" + zlib.compress(bytes(profile)))])
    b = image()
    result = audit_png_presentation(*evidence(("development", [a, b])))
    assert result["presentation_metadata_disagreement_group_count"] == 1


def test_png_unknown_critical_chunk_rejected():
    a = add_chunks(image(), [(b"ABCD", b"")])
    with pytest.raises(ValueError, match="critical"):
        audit_png_presentation(*evidence(("development", [a])))


def test_png_palette_format_not_misdecoded_as_rgba():
    header = struct.pack(">IIBBBBB", 1, 1, 8, 3, 0, 0, 0)
    paletted = PNG_SIGNATURE() + chunk(b"IHDR", header) + chunk(b"PLTE", b"\x01\x02\x03")
    paletted += chunk(b"IDAT", zlib.compress(b"\x00\x00")) + chunk(b"IEND", b"")
    with pytest.raises(ValueError, match="unsupported"):
        audit_png_presentation(*evidence(("development", [paletted])))
