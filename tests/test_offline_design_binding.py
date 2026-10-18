"""T59 offline design-binding adversarial regressions; no live I/O."""
from dataclasses import asdict
import copy
import unittest

from vera_ark.offline_design_binding import (
    SCHEMA, freeze_design, verify_design_binding,
)


def fixture():
    groups = ('g0', 'g0', 'g0', 'g1', 'g1', 'g1')
    arms = ('BASELINE', 'BASELINE', 'CANDIDATE', 'BASELINE', 'CANDIDATE', 'CANDIDATE')
    blocks = ('a', 'a', 'b', 'b', 'a', 'b')
    deltas = (-1., -1., 0., 1., 0., 1.)
    return [dict(trial_id=f't{i}', group_id=groups[i], block_id=blocks[i],
                 first_arm=arms[i], paired_delta=deltas[i], negative_control_delta=0.)
            for i in range(6)]


def design(rows):
    return [{k: r[k] for k in ('trial_id', 'group_id', 'block_id', 'first_arm')} for r in rows]


_UNSET = object()


class OfflineDesignBindingTests(unittest.TestCase):
    def setUp(self):
        self.rows = fixture()
        self.manifest, self.digest = freeze_design(design(self.rows))

    def verify(self, rows=_UNSET, manifest=_UNSET, digest=_UNSET):
        return verify_design_binding(self.rows if rows is _UNSET else rows,
                                     frozen_manifest=self.manifest if manifest is _UNSET else manifest,
                                     expected_sha256=self.digest if digest is _UNSET else digest)

    def test_valid_design_and_known_canonical_digest(self):
        audit = self.verify()
        self.assertEqual((audit.pair_count, audit.group_count, audit.block_count), (6, 2, 2))
        self.assertEqual(audit.schema, SCHEMA)
        self.assertEqual(audit.commitment_sha256, self.digest)
        self.assertEqual(len(self.digest), 64)

    def test_row_order_invariance_and_canonical_manifest_order(self):
        self.assertEqual(freeze_design(list(reversed(design(self.rows)))),
                         (self.manifest, self.digest))
        self.assertEqual(self.verify(list(reversed(self.rows))), self.verify())
        altered = copy.deepcopy(self.manifest)
        altered['trials'].reverse()
        with self.assertRaises(ValueError):
            self.verify(manifest=altered)

    def test_block_refinement_after_commitment_rejected(self):
        rows = copy.deepcopy(self.rows)
        rows[0]['block_id'] = 'new_posthoc_block'
        with self.assertRaisesRegex(ValueError, 'observed design differs'):
            self.verify(rows)

    def test_block_coarsening_after_commitment_rejected(self):
        rows = copy.deepcopy(self.rows)
        for r in rows:
            r['block_id'] = 'merged'
        with self.assertRaisesRegex(ValueError, 'observed design differs'):
            self.verify(rows)

    def test_group_relabeling_rejected(self):
        rows = copy.deepcopy(self.rows)
        rows[0]['group_id'], rows[3]['group_id'] = rows[3]['group_id'], rows[0]['group_id']
        with self.assertRaisesRegex(ValueError, 'observed design differs'):
            self.verify(rows)

    def test_arm_relabeling_rejected(self):
        rows = copy.deepcopy(self.rows)
        rows[0]['first_arm'], rows[2]['first_arm'] = rows[2]['first_arm'], rows[0]['first_arm']
        with self.assertRaises(ValueError):
            self.verify(rows)

    def test_trial_id_relabeling_rejected(self):
        rows = copy.deepcopy(self.rows)
        rows[0]['trial_id'] = 'renamed'
        with self.assertRaisesRegex(ValueError, 'observed design differs'):
            self.verify(rows)

    def test_outcome_values_are_intentionally_not_bound(self):
        rows = copy.deepcopy(self.rows)
        rows[0]['paired_delta'] = 1.
        rows[0]['negative_control_delta'] = -1.
        self.assertEqual(self.verify(rows), self.verify())
        # This proves outcome authenticity is outside the commitment scope.

    def test_manifest_mutation_fails_without_matching_digest(self):
        altered = copy.deepcopy(self.manifest)
        altered['trials'][0]['block_id'] = 'z'
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            self.verify(manifest=altered)

    def test_hostile_self_issued_posthoc_digest_still_passes(self):
        rows = copy.deepcopy(self.rows)
        rows[0]['block_id'] = 'posthoc'
        manifest, digest = freeze_design(design(rows))
        audit = self.verify(rows, manifest, digest)
        self.assertTrue(audit.design_matches_commitment)
        self.assertFalse(audit.pre_outcome_commitment_verified)
        # Without an external pre-outcome witness, this is not preregistration.

    def test_reject_malformed_expected_digests(self):
        for bad in ('', '0' * 63, 'Z' * 64, self.digest.upper(), True, 123, None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.verify(digest=bad)

    def test_reject_manifest_schema_extras_and_duplicate(self):
        for bad in (None, [], {'schema': 'OTHER', 'trials': self.manifest['trials']},
                    {**self.manifest, 'extra': 1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.verify(manifest=bad)
        altered = copy.deepcopy(self.manifest)
        altered['trials'][0]['trial_id'] = altered['trials'][1]['trial_id']
        with self.assertRaises(ValueError):
            self.verify(manifest=altered)

    def test_reject_extra_or_missing_outcome_fields(self):
        for edit in (lambda r: r.update(extra=1), lambda r: r.pop('paired_delta')):
            rows = copy.deepcopy(self.rows)
            edit(rows[0])
            with self.assertRaises(ValueError):
                self.verify(rows)

    def test_reject_nonfinite_or_boolean_outcomes(self):
        for bad in (float('nan'), float('inf'), float('-inf'), True, -1.01, 1.01, '0'):
            rows = copy.deepcopy(self.rows)
            rows[0]['paired_delta'] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.verify(rows)

    def test_reject_duplicate_missing_or_added_trials(self):
        for rows in (self.rows[:-1], self.rows + [dict(self.rows[0], trial_id='extra')],
                     self.rows[:-1] + [dict(self.rows[0])]):
            with self.subTest(n=len(rows)), self.assertRaises(ValueError):
                self.verify(rows)

    def test_reject_bad_design_fields_and_group_arm_coverage(self):
        for field, bad in [('trial_id', True), ('group_id', '!'), ('block_id', ''),
                           ('first_arm', 'OTHER')]:
            rows = copy.deepcopy(self.rows)
            rows[0][field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                freeze_design(design(rows))
        rows = copy.deepcopy(self.rows)
        for r in rows:
            r['group_id'] = 'one'
        with self.assertRaises(ValueError):
            freeze_design(design(rows))

    def test_max_pairs_fail_closed(self):
        for bad in (True, 3, 9, 8.0):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                freeze_design(design(self.rows), max_pairs=bad)
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                verify_design_binding(self.rows, frozen_manifest=self.manifest,
                                      expected_sha256=self.digest, max_pairs=bad)

    def test_no_evidence_flag_elevation(self):
        flags = asdict(self.verify())
        for key in ('observation_authenticity_verified', 'pre_outcome_commitment_verified',
                    'exchangeability_verified', 'randomization_verified',
                    'causal_learning_verified', 'live_route_verified', 'independently_reviewed'):
            self.assertIs(flags[key], False)


if __name__ == '__main__':
    unittest.main()
