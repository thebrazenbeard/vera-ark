"""Exact-byte binding for offline replay benchmark evidence, without file/device I/O.

This checks whether each caller-declared frame SHA-256 is actually the SHA-256
of supplied immutable frame bytes. It is not screenshot provenance, image
similarity, an attestation, or evidence of controller causality.
"""
from __future__ import annotations

import hashlib
import json
import re

SCHEMA = "VERA_ARK_REPLAY_BENCHMARK_V1"
OUTPUT_SCHEMA = "VERA_ARK_FRAME_BYTE_BINDING_V1"
SHA = re.compile(r"[0-9a-f]{64}\Z")
IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
CASE_FIELDS = frozenset(("case_id", "split", "capture_group", "frame_sha256", "reference_label", "reference_basis"))
SPLITS = frozenset(("development", "holdout"))
LABELS = frozenset(("REPLAY_LIKE", "NON_REPLAY_LIKE"))
BASES = frozenset(("SYNTHETIC_CONSTRUCTION", "DECLARED_CAPTURE_REVIEW"))
MAX_CASES = 10_000
MAX_UNIQUE_FRAMES = 40_000
MAX_FRAME_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024


def _sha(value: object, field: str) -> str:
    if type(value) is not str or SHA.fullmatch(value) is None:
        raise ValueError(f"invalid {field}")
    return value


def _ident(value: object, field: str) -> str:
    if type(value) is not str or IDENT.fullmatch(value) is None:
        raise ValueError(f"invalid {field}")
    return value


def _canonical_sha(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


def audit_frame_byte_binding(manifest: object, frame_bytes: object) -> dict:
    """Validate exact supplied bytes for every declared frame, fail closed.

    Frame digests are of *encoded frame-file bytes* (not decoded RGB pixels).
    All bytes must be supplied in a SHA-256-keyed dict; no filesystem paths,
    URLs, device reads, or controller operations are accepted. A passing result
    binds declarations to supplied bytes, NOT to their asserted capture origin.
    """
    if type(manifest) is not dict or set(manifest) != {"schema", "evaluator_sha256", "cases"}:
        raise ValueError("invalid manifest fields")
    if manifest["schema"] != SCHEMA:
        raise ValueError("unsupported manifest schema")
    _sha(manifest["evaluator_sha256"], "evaluator_sha256")
    cases = manifest["cases"]
    if type(cases) is not list or not 1 <= len(cases) <= MAX_CASES:
        raise ValueError("invalid case count")
    if type(frame_bytes) is not dict or len(frame_bytes) > MAX_UNIQUE_FRAMES:
        raise ValueError("invalid frame byte mapping")

    ids: set[str] = set()
    groups: dict[str, str] = {}
    referenced: set[str] = set()
    frame_splits: dict[str, str] = {}
    frame_occurrence_counts: dict[str, int] = {}
    frame_case_ids: dict[str, set[str]] = {}
    for index, case in enumerate(cases):
        if type(case) is not dict or set(case) != CASE_FIELDS:
            raise ValueError(f"case[{index}]: invalid fields")
        ident = _ident(case["case_id"], "case_id")
        if ident in ids:
            raise ValueError("duplicate case_id")
        ids.add(ident)
        split = case["split"]
        if type(split) is not str or split not in SPLITS:
            raise ValueError("invalid split")
        group = _ident(case["capture_group"], "capture_group")
        if group in groups and groups[group] != split:
            raise ValueError("capture group crosses development/holdout")
        groups[group] = split
        if type(case["reference_label"]) is not str or case["reference_label"] not in LABELS:
            raise ValueError("invalid reference label")
        if type(case["reference_basis"]) is not str or case["reference_basis"] not in BASES:
            raise ValueError("invalid reference basis")
        frames = case["frame_sha256"]
        if type(frames) is not list or len(frames) != 4:
            raise ValueError("expected four ordered frame hashes")
        for value in frames:
            sha = _sha(value, "frame_sha256")
            if sha in frame_splits and frame_splits[sha] != split:
                raise ValueError("exact frame hash crosses development/holdout")
            frame_splits[sha] = split
            referenced.add(sha)
            frame_occurrence_counts[sha] = frame_occurrence_counts.get(sha, 0) + 1
            frame_case_ids.setdefault(sha, set()).add(ident)

    if set(frame_bytes) != referenced:
        raise ValueError("frame bytes missing or unreferenced")
    total_bytes = 0
    for sha, data in frame_bytes.items():
        _sha(sha, "frame byte key")
        if type(data) is not bytes or not 1 <= len(data) <= MAX_FRAME_BYTES:
            raise ValueError("invalid frame byte payload")
        total_bytes += len(data)
        if total_bytes > MAX_TOTAL_BYTES:
            raise ValueError("frame byte budget exceeded")
        if hashlib.sha256(data).hexdigest() != sha:
            raise ValueError("frame byte SHA-256 mismatch")

    manifest_sha = _canonical_sha(manifest)
    # Length-tagged sorted hashes give a deterministic, bounded freeze
    # identifier for the supplied set; bytes have already been verified.
    inventory = [[sha, len(frame_bytes[sha])] for sha in sorted(referenced)]
    return {
        "schema": OUTPUT_SCHEMA,
        "manifest_sha256": manifest_sha,
        "verified_byte_inventory_sha256": _canonical_sha(inventory),
        "binding_sha256": _canonical_sha([OUTPUT_SCHEMA, manifest_sha, inventory]),
        "case_count": len(cases),
        "unique_verified_frame_count": len(referenced),
        "verified_frame_bytes": total_bytes,
        "frame_occurrences": sum(frame_occurrence_counts.values()),
        "reused_exact_frame_count": sum(count > 1 for count in frame_occurrence_counts.values()),
        "cross_case_reused_exact_frame_count": sum(len(ids) > 1 for ids in frame_case_ids.values()),
        "within_case_repeated_exact_frame_count": sum(
            frame_occurrence_counts[sha] > len(ids) for sha, ids in frame_case_ids.items()
        ),
        "status": "DECLARED_FRAME_BYTES_MATCH_SHA256",
        "capture_authenticity_verified": False,
        "controller_causality_verified": False,
        "independent_review": False,
        "claim_ceiling": "CALLER_SUPPLIED_EXACT_BYTE_BINDING_ONLY",
        "limitations": [
            "The caller can fabricate both bytes and manifest; matching hashes do not authenticate a capture.",
            "Identical image content in different encodings can evade exact-file-byte matching.",
            "Repeated frame evidence cannot be treated as independent observations.",
            "Frame bytes are treated as opaque; no image format or visual content is validated.",
            "This audit does not verify reference labels, image semantics, gameplay, or controller effects.",
        ],
    }
