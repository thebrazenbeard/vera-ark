"""Offline design-digest binding; NOT proof of pre-outcome registration.

A digest supplied with the data is self-attested. Only an independently held,
pre-outcome commitment can make this useful as a chronology control. Neither
that independent witness nor observation authenticity is verified here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import math
import re
from typing import Any

SCHEMA = 'VERA_ARK_OFFLINE_DESIGN_BINDING_V1'
_DESIGN_KEYS = frozenset({'trial_id', 'group_id', 'block_id', 'first_arm'})
_OUTCOME_KEYS = frozenset({'paired_delta', 'negative_control_delta'})
_ARMS = ('BASELINE', 'CANDIDATE')
_ID = re.compile(r'[a-z0-9][a-z0-9._-]{0,63}\Z')
_DIGEST = re.compile(r'[0-9a-f]{64}\Z')
_DOMAIN = (SCHEMA + '\n').encode('ascii')


@dataclass(frozen=True, slots=True)
class DesignBindingAudit:
    schema: str
    commitment_sha256: str
    pair_count: int
    group_count: int
    block_count: int
    design_matches_commitment: bool
    observation_authenticity_verified: bool = False
    pre_outcome_commitment_verified: bool = False
    exchangeability_verified: bool = False
    randomization_verified: bool = False
    causal_learning_verified: bool = False
    live_route_verified: bool = False
    independently_reviewed: bool = False


def _design_rows(trials: Any, *, max_pairs: int) -> list[dict[str, str]]:
    if type(max_pairs) is not int or not 4 <= max_pairs <= 8:
        raise ValueError('max_pairs must be an integer in 4..8')
    if type(trials) is not list or not 4 <= len(trials) <= max_pairs:
        raise ValueError('expected 4..max_pairs design trials')
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in trials:
        if type(row) is not dict or row.keys() != _DESIGN_KEYS:
            raise ValueError('invalid design trial schema')
        trial, group, block, arm = (row[k] for k in ('trial_id', 'group_id', 'block_id', 'first_arm'))
        if any(type(s) is not str or not _ID.fullmatch(s) for s in (trial, group, block)):
            raise ValueError('invalid design identifier')
        if trial in seen:
            raise ValueError('duplicate trial_id')
        if type(arm) is not str or arm not in _ARMS:
            raise ValueError('invalid first_arm')
        seen.add(trial)
        result.append(dict(trial_id=trial, group_id=group, block_id=block, first_arm=arm))
    groups = {row['group_id'] for row in result}
    cells = {(row['group_id'], row['first_arm']) for row in result}
    if len(groups) < 2 or cells != {(g, a) for g in groups for a in _ARMS}:
        raise ValueError('at least two groups with both first arms required')
    return sorted(result, key=lambda row: row['trial_id'])


def _manifest_bytes(manifest: Any, *, max_pairs: int) -> bytes:
    if type(manifest) is not dict or manifest.keys() != {'schema', 'trials'} or manifest['schema'] != SCHEMA:
        raise ValueError('invalid design manifest schema')
    trials = _design_rows(manifest['trials'], max_pairs=max_pairs)
    if trials != manifest['trials']:
        raise ValueError('design manifest must be canonical and sorted')
    return json.dumps({'schema': SCHEMA, 'trials': trials},
                      sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def freeze_design(trials: list[dict[str, str]], *, max_pairs: int = 8) -> tuple[dict[str, Any], str]:
    """Produce a canonical design and its digest, without observing outcomes.

    The caller must independently preserve the returned digest BEFORE outcomes;
    this function cannot establish when that happened.
    """
    manifest = {'schema': SCHEMA, 'trials': _design_rows(trials, max_pairs=max_pairs)}
    digest = hashlib.sha256(_DOMAIN + _manifest_bytes(manifest, max_pairs=max_pairs)).hexdigest()
    return manifest, digest


def verify_design_binding(
    rows: list[dict[str, Any]], *, frozen_manifest: dict[str, Any],
    expected_sha256: str, max_pairs: int = 8,
) -> DesignBindingAudit:
    """Fail closed on trial, group, arm or block drift from a digest-bound design.

    This checks internal consistency against a supplied digest, not whether the
    digest was genuinely precommitted or independently witnessed.
    """
    if type(expected_sha256) is not str or not _DIGEST.fullmatch(expected_sha256):
        raise ValueError('expected_sha256 must be 64 lowercase hex characters')
    canonical = _manifest_bytes(frozen_manifest, max_pairs=max_pairs)
    actual = hashlib.sha256(_DOMAIN + canonical).hexdigest()
    if not hmac.compare_digest(actual, expected_sha256):
        raise ValueError('design manifest digest mismatch')
    if type(rows) is not list or not 4 <= len(rows) <= max_pairs:
        raise ValueError('expected 4..max_pairs outcome rows')
    design_rows: list[dict[str, str]] = []
    for row in rows:
        if type(row) is not dict or row.keys() != _DESIGN_KEYS | _OUTCOME_KEYS:
            raise ValueError('invalid outcome row schema')
        for key in _OUTCOME_KEYS:
            value = row[key]
            if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)) or not -1 <= value <= 1:
                raise ValueError('invalid bounded outcome')
        design_rows.append({key: row[key] for key in _DESIGN_KEYS})
    observed = _design_rows(design_rows, max_pairs=max_pairs)
    if observed != frozen_manifest['trials']:
        raise ValueError('observed design differs from committed design')
    return DesignBindingAudit(
        schema=SCHEMA, commitment_sha256=actual, pair_count=len(observed),
        group_count=len({r['group_id'] for r in observed}),
        block_count=len({r['block_id'] for r in observed}),
        design_matches_commitment=True,
    )
