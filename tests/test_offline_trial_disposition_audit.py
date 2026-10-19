"""T72 offline fixed-denominator falsifiers; all examples are synthetic."""
import itertools
import math
import unittest

from vera_ark.offline_trial_disposition_audit import (
    MAX_TRIALS, SCHEMA, audit_trial_dispositions,
)


def row(trial_id, status="OBSERVED", metric=0.5):
    return {"trial_id": trial_id, "status": status, "metric": metric}


class TrialDispositionTests(unittest.TestCase):
    def audit(self, ids=("a", "b", "c"), rows=None, limits=(0.0, 1.0)):
        if rows is None:
            rows = (row("a", metric=0.2), row("b", "MISSING_CAPTURE", None), row("c", metric=0.8))
        return audit_trial_dispositions(ids, rows, metric_range=limits)

    def test_one_missing_preserves_denominator(self):
        a = self.audit()
        self.assertEqual((a.planned_count, a.observed_count, a.missing_capture_count), (3, 2, 1))
        self.assertAlmostEqual(a.full_roster_mean_lower_bound, 1 / 3)
        self.assertAlmostEqual(a.full_roster_mean_upper_bound, 2 / 3)
        self.assertAlmostEqual(a.observed_mean, 0.5)
        self.assertFalse(a.all_trial_outcomes_observed)
        self.assertFalse(a.causal_learning_verified)

    def test_complete_observed_bounds_collapse(self):
        a = self.audit(rows=(row("a", metric=0.0), row("b", metric=0.5), row("c", metric=1.0)))
        self.assertEqual(a.full_roster_mean_lower_bound, a.full_roster_mean_upper_bound)
        self.assertEqual(a.observed_mean, 0.5)
        self.assertTrue(a.all_trial_outcomes_observed)
        self.assertFalse(a.capture_origin_authenticated)

    def test_all_missing_is_not_zero_mean(self):
        a = self.audit(rows=(row("a", "STOPPED", None), row("b", "INVALID_EVIDENCE", None), row("c", "MISSING_CAPTURE", None)))
        self.assertIsNone(a.observed_mean)
        self.assertEqual((a.full_roster_mean_lower_bound, a.full_roster_mean_upper_bound), (0, 1))
        self.assertEqual((a.stopped_count, a.invalid_evidence_count), (1, 1))

    def test_one_trial_allowed(self):
        a = self.audit(ids=("x",), rows=(row("x", "STOPPED", None),), limits=(-2, 3))
        self.assertEqual((a.full_roster_mean_lower_bound, a.full_roster_mean_upper_bound), (-2, 3))

    def test_negative_range_bounds(self):
        a = self.audit(rows=(row("a", metric=-2), row("b", "MISSING_CAPTURE", None), row("c", metric=1)), limits=(-5, 2))
        self.assertAlmostEqual(a.full_roster_mean_lower_bound, -2)
        self.assertAlmostEqual(a.full_roster_mean_upper_bound, 1 / 3)

    def test_missing_row_rejected(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.audit(rows=(row("a"), row("b")))

    def test_extra_row_rejected(self):
        with self.assertRaisesRegex(ValueError, "oversized"):
            self.audit(rows=(row("a"), row("b"), row("c"), row("d")))

    def test_reordered_row_rejected(self):
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            self.audit(rows=(row("b"), row("a"), row("c")))

    def test_duplicate_row_rejected(self):
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            self.audit(rows=(row("a"), row("a"), row("c")))

    def test_non_tuple_rows_rejected(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.audit(rows=[row("a"), row("b"), row("c")])

    def test_non_tuple_roster_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid expected trial roster"):
            self.audit(ids=["a", "b", "c"])

    def test_empty_roster_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid expected trial roster"):
            self.audit(ids=(), rows=())

    def test_roster_limit_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid expected trial roster"):
            self.audit(ids=tuple(str(i) for i in range(MAX_TRIALS + 1)), rows=())

    def test_duplicate_roster_id_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate expected trial ID"):
            self.audit(ids=("a", "a", "c"))

    def test_confusable_roster_id_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid expected trial ID"):
            self.audit(ids=("a", "b", "с"))

    def test_extra_row_field_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid disposition row fields"):
            self.audit(rows=(dict(row("a"), hidden=1), row("b"), row("c")))

    def test_missing_row_field_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid disposition row fields"):
            self.audit(rows=({"trial_id": "a", "status": "OBSERVED"}, row("b"), row("c")))

    def test_unknown_status_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid trial disposition status"):
            self.audit(rows=(row("a", "EXCLUDED", None), row("b"), row("c")))

    def test_boolean_metric_rejected(self):
        with self.assertRaisesRegex(ValueError, "not bool"):
            self.audit(rows=(row("a", metric=True), row("b"), row("c")))

    def test_nan_and_infinity_rejected(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "finite"):
                self.audit(rows=(row("a", metric=value), row("b"), row("c")))

    def test_large_integer_rejected_without_overflow(self):
        with self.assertRaisesRegex(ValueError, "finite"):
            self.audit(rows=(row("a", metric=10**1000), row("b"), row("c")))

    def test_metric_outside_range_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside declared"):
            self.audit(rows=(row("a", metric=1.1), row("b"), row("c")))

    def test_missing_with_fabricated_score_rejected(self):
        for status in ("STOPPED", "MISSING_CAPTURE", "INVALID_EVIDENCE"):
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "null metric"):
                self.audit(rows=(row("a", status, 0.9), row("b"), row("c")))

    def test_observed_without_score_rejected(self):
        with self.assertRaisesRegex(ValueError, "finite"):
            self.audit(rows=(row("a", "OBSERVED", None), row("b"), row("c")))

    def test_invalid_range_rejected(self):
        for limits in ((1, 1), (2, 1), (float("nan"), 1), (0, float("inf")), (0, 10**1000)):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                self.audit(limits=limits)

    def test_range_bool_rejected(self):
        with self.assertRaisesRegex(ValueError, "not bool"):
            self.audit(limits=(False, 1))

    def test_range_list_rejected(self):
        with self.assertRaisesRegex(ValueError, "two-element tuple"):
            self.audit(limits=[0, 1])

    def test_nonnumeric_status_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid trial disposition status"):
            self.audit(rows=(row("a", 0, None), row("b"), row("c")))

    def test_extreme_bounds_finite(self):
        ids = tuple(f"x{i}" for i in range(32))
        rows = tuple(row(i, "MISSING_CAPTURE", None) for i in ids)
        a = self.audit(ids, rows, (-1e6, 1e6))
        self.assertTrue(math.isfinite(a.full_roster_mean_lower_bound))
        self.assertEqual((a.full_roster_mean_lower_bound, a.full_roster_mean_upper_bound), (-1e6, 1e6))

    def test_small_exhaustive_bound_oracle(self):
        # For all disposition patterns of three trials, brute-force all endpoints
        # for missing values and verify the returned exact min/max envelope.
        ids = ("a", "b", "c")
        for pattern in itertools.product(("OBSERVED", "MISSING_CAPTURE", "STOPPED", "INVALID_EVIDENCE"), repeat=3):
            rows = tuple(row(ids[i], s, 0.25 if s == "OBSERVED" else None) for i, s in enumerate(pattern))
            a = self.audit(ids, rows, (0.0, 1.0))
            missing_indices = [i for i, s in enumerate(pattern) if s != "OBSERVED"]
            means = []
            for values in itertools.product((0.0, 1.0), repeat=len(missing_indices)):
                score = [0.25 if s == "OBSERVED" else None for s in pattern]
                for i, value in zip(missing_indices, values):
                    score[i] = value
                means.append(sum(score) / 3)
            self.assertAlmostEqual(a.full_roster_mean_lower_bound, min(means))
            self.assertAlmostEqual(a.full_roster_mean_upper_bound, max(means))

    def test_fabricated_complete_rows_still_pass_but_not_authentic(self):
        a = self.audit(rows=(row("a", metric=1), row("b", metric=1), row("c", metric=1)))
        self.assertTrue(a.all_trial_outcomes_observed)
        self.assertFalse(a.roster_precommitment_independently_verified)
        self.assertFalse(a.selection_bias_ruled_out)
        self.assertFalse(a.causal_learning_verified)
        self.assertFalse(a.independent_review_verified)


if __name__ == "__main__":
    unittest.main()
