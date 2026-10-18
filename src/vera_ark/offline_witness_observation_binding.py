"""Bind caller-supplied observation bytes to an offline signed witness pair.

Exact-byte consistency is not observation authenticity, external time, or
pre-outcome registration. No network, controller, capture, or filesystem I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from typing import Mapping

from .offline_witness_pair import WitnessReceipt, WitnessPairAssessment, verify_witness_pair

SCHEMA = "VERA_ARK_OFFLINE_WITNESS_OBSERVATION_BINDING_V1"
MAX_OBSERVATION_BYTES = 1_048_576


@dataclass(frozen=True, slots=True)
class WitnessObservationBindingAssessment:
    schema: str
    witness_pair: WitnessPairAssessment
    observation_sha256: str
    observation_length: int
    signed_payload_digest_matches: bool = True
    observation_origin_authenticated: bool = False
    capture_currentness_verified: bool = False
    external_clock_verified: bool = False
    pre_outcome_registration_verified: bool = False
    causal_learning_verified: bool = False
    independent_review_verified: bool = False


def verify_witness_observation_binding(
    commitment: WitnessReceipt,
    first_observation: WitnessReceipt,
    *,
    observation_bytes: bytes,
    trusted_public_keys: Mapping[str, bytes],
    expected_witness_id: str,
    expected_experiment_id: str,
    expected_design_sha256: str,
    expected_analysis_sha256: str,
    expected_source_set_sha256: str,
) -> WitnessObservationBindingAssessment:
    """Verify signature pair and exact observation bytes; reject mismatches.

    `observation_bytes` must be the exact serialized artifact whose digest the
    witness signed. The caller supplies these bytes and the trust pin; neither
    source authenticity nor independent custody can be inferred from them.
    """
    if type(observation_bytes) is not bytes or not 0 < len(observation_bytes) <= MAX_OBSERVATION_BYTES:
        raise ValueError("observation_bytes must be nonempty bytes within size limit")
    pair = verify_witness_pair(
        commitment, first_observation,
        trusted_public_keys=trusted_public_keys,
        expected_witness_id=expected_witness_id,
        expected_experiment_id=expected_experiment_id,
        expected_design_sha256=expected_design_sha256,
        expected_analysis_sha256=expected_analysis_sha256,
        expected_source_set_sha256=expected_source_set_sha256,
    )
    observed_digest = hashlib.sha256(observation_bytes).hexdigest()
    if not hmac.compare_digest(observed_digest, first_observation.observation_sha256):
        raise ValueError("signed observation digest does not match supplied observation bytes")
    return WitnessObservationBindingAssessment(
        SCHEMA, pair, observed_digest, len(observation_bytes)
    )
