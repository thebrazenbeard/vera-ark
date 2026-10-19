"""T74: fail closed on falsely inward-rounded full-roster score bounds."""
import itertools
import math
import random
import unittest
from fractions import Fraction

from vera_ark.offline_trial_disposition_audit import audit_trial_dispositions


def _rows(scores):
    ids = tuple(f"trial{i}" for i in range(len(scores)))
    rows = tuple({"trial_id": name,
                  "status": "OBSERVED" if score is not None else "MISSING_CAPTURE",
                  "metric": score}
                 for name, score in zip(ids, scores))
    return ids, rows


def _oracle(scores, lo, hi):
    n = len(scores)
    lower = sum((Fraction.from_float(x if x is not None else lo) for x in scores), Fraction()) / n
    upper = sum((Fraction.from_float(x if x is not None else hi) for x in scores), Fraction()) / n
    return lower, upper


class DispositionOutwardBoundsT74(unittest.TestCase):
    def assert_encloses(self, scores, metric_range):
        ids, rows = _rows(scores)
        assessment = audit_trial_dispositions(ids, rows, metric_range=metric_range)
        lower, upper = _oracle(scores, *metric_range)
        self.assertLessEqual(Fraction.from_float(assessment.full_roster_mean_lower_bound), lower)
        self.assertGreaterEqual(Fraction.from_float(assessment.full_roster_mean_upper_bound), upper)
        self.assertLessEqual(assessment.full_roster_mean_lower_bound,
                             assessment.full_roster_mean_upper_bound)
        return assessment

    def test_observed_binary_float_sum_must_not_round_lower_inward(self):
        self.assert_encloses((0.1, 0.2), (0.0, 1.0))

    def test_missing_binary_float_sum_must_not_round_upper_inward(self):
        self.assert_encloses((0.1, None, 0.2), (0.0, 0.9))

    def test_negative_observed_values(self):
        self.assert_encloses((-0.1, -0.2), (-1.0, 0.0))

    def test_subnormal_positive_bound(self):
        tiny = math.ulp(0.0)
        a = self.assert_encloses((tiny, 0.0, 0.0), (0.0, 1.0))
        self.assertEqual(a.full_roster_mean_lower_bound, 0.0)
        self.assertEqual(a.full_roster_mean_upper_bound, tiny)

    def test_subnormal_negative_bound(self):
        tiny = math.ulp(0.0)
        a = self.assert_encloses((-tiny, 0.0, 0.0), (-1.0, 0.0))
        self.assertEqual(a.full_roster_mean_lower_bound, -tiny)
        self.assertEqual(a.full_roster_mean_upper_bound, 0.0)

    def test_32_trial_extremes(self):
        self.assert_encloses(tuple((1e6 if i % 3 == 0 else (-1e6 if i % 3 == 1 else None))
                                   for i in range(32)), (-1e6, 1e6))

    def test_exhaustive_three_trial_decimal_and_missing_oracle(self):
        options = (None, 0.0, 0.1, 0.2, 0.3, 0.5, 0.9, 1.0)
        for scores in itertools.product(options, repeat=3):
            with self.subTest(scores=scores):
                self.assert_encloses(scores, (0.0, 1.0))

    def test_deterministic_random_extreme_value_oracle(self):
        rng = random.Random(7401)
        for _ in range(1000):
            n = rng.randint(1, 32)
            lo, hi = rng.choice(((0.0, 1.0), (-1e6, 1e6), (-1.0, 0.0)))
            options = (None, lo, hi, (lo + hi) / 2, math.nextafter(lo, hi))
            self.assert_encloses(tuple(rng.choice(options) for _ in range(n)), (lo, hi))


if __name__ == "__main__":
    unittest.main()
