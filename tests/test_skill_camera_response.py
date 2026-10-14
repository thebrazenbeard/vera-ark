import unittest

from vera_ark.skill_camera_response import (
    YawObservation, YawResponseError, assess_yaw_reversal,
    next_yaw_response_probe,
)


def observed(x, dx, *, dy=0, scene="BEACH", duration=240, tracks=200,
             capture=True, neutral=True, static=True):
    return YawObservation(
        scene, x, duration, dx, dy, tracks,
        capture, neutral, static,
    )


class YawResponseTests(unittest.TestCase):
    def test_reversed_sign_and_static_shift_is_candidate_only(self):
        left = observed(-.36, +50, dy=-.15, tracks=214)
        right = observed(+.36, -56.45, dy=.42, tracks=196)
        result = assess_yaw_reversal(left, right, idle_median_dx=0.0)
        self.assertEqual(result.disposition, "CANDIDATE_REVERSIBLE_YAW")
        self.assertFalse(result.automatic_execution_permitted)
        self.assertFalse(result.angular_degrees_known)

    def test_weak_and_strong_pair_brackets_next_trial_not_deadzone(self):
        weak = observed(-.20, 0, duration=240)
        strong = observed(-.36, 50, duration=240)
        result = next_yaw_response_probe(weak, strong)
        self.assertEqual(result.disposition, "CANDIDATE_INTERMEDIATE_PROBE")
        self.assertEqual(result.experimental_magnitude, .28)
        self.assertFalse(result.automatic_execution_permitted)

    def test_bracket_narrows_after_measured_intermediate_response(self):
        weak = observed(-.20, 0, duration=240, tracks=209)
        strong = observed(-.28, 14.34, duration=240, tracks=210)
        next_trial = next_yaw_response_probe(weak, strong)
        self.assertEqual(next_trial.experimental_magnitude, .24)
        self.assertFalse(next_trial.automatic_execution_permitted)

    def test_second_midpoint_narrows_response_range_again(self):
        weak = observed(-.24, 0, duration=240, tracks=203)
        strong = observed(-.28, 14.34, duration=240, tracks=210)
        proposed = next_yaw_response_probe(weak, strong)
        self.assertEqual(proposed.experimental_magnitude, .26)
        self.assertFalse(proposed.automatic_execution_permitted)

    def test_mismatched_context_is_unknown(self):
        result = assess_yaw_reversal(
            observed(-.36, 50, scene="BEACH"),
            observed(+.36, -56, scene="FOREST"),
        )
        self.assertEqual(result.reason, "SCENE_MISMATCH")
        self.assertEqual(next_yaw_response_probe(
            observed(-.20, 0, scene="BEACH"),
            observed(-.36, 50, scene="FOREST"),
        ).reason, "SCENE_OR_AXIS_DIRECTION_MISMATCH")

    def test_capture_and_neutral_gates(self):
        for changes in ({"capture": False}, {"neutral": False},
                        {"static": False}, {"tracks": 12}):
            weak = observed(-.36, 50, **changes)
            self.assertEqual(
                assess_yaw_reversal(weak, observed(+.36, -52)).disposition, "UNKNOWN"
            )

    def test_idle_drift_or_large_vertical_shift_fails_closed(self):
        self.assertEqual(assess_yaw_reversal(
            observed(-.36, 50), observed(+.36, -52),
            idle_median_dx=8.0,
        ).reason, "UNSTABLE_IDLE_REFERENCE")
        self.assertEqual(assess_yaw_reversal(
            observed(-.36, 50, dy=8), observed(+.36, -52),
        ).reason, "VERTICAL_DRIFT_OR_SCENE_CHANGE")

    def test_wrong_direction_and_weak_or_asymmetric_shift(self):
        self.assertEqual(assess_yaw_reversal(
            observed(-.36, -50), observed(+.36, +52),
        ).reason, "WEAK_OR_INCONSISTENT_REVERSAL")
        self.assertEqual(assess_yaw_reversal(
            observed(-.36, 150), observed(+.36, -10),
        ).reason, "ASYMMETRIC_YAW_OR_CAPTURE_ERROR")
        self.assertEqual(assess_yaw_reversal(
            observed(-.2, 0), observed(+.36, -52),
        ).reason, "WEAK_OR_INCONSISTENT_REVERSAL")

    def test_probe_rejects_noncontrolled_duration(self):
        r = next_yaw_response_probe(
            observed(-.2, 0, duration=100),
            observed(-.36, 50, duration=240),
        )
        self.assertEqual(r.reason, "INPUT_DURATION_NOT_CONTROLLED")

    def test_probe_rejects_unreversed_strength_order_and_dynamic_scene(self):
        self.assertEqual(next_yaw_response_probe(
            observed(-.36, 50), observed(-.20, 0),
        ).reason, "MAGNITUDES_NOT_ORDERED")
        self.assertEqual(next_yaw_response_probe(
            observed(-.2, 15), observed(-.36, 50),
        ).reason, "NO_RELIABLE_WEAK_STRONG_BRACKET")
        self.assertEqual(next_yaw_response_probe(
            observed(-.2, 0, static=False),
            observed(-.36, 50),
        ).reason, "INVALID_OR_UNREVIEWED_FRAME")

    def test_invalid_numeric_input(self):
        for bad in (float("nan"), float("inf"), True, -4.0, 0):
            with self.subTest(bad=bad), self.assertRaises(YawResponseError):
                observed(bad, 50)
        with self.assertRaises(YawResponseError):
            observed(-.36, float("nan"))
        with self.assertRaises(YawResponseError):
            observed(-.36, 50, duration=251)
        with self.assertRaises(YawResponseError):
            observed(-.36, 50, tracks=-1)
        with self.assertRaises(YawResponseError):
            assess_yaw_reversal(observed(+.36, 50), observed(-.36, -50))
        with self.assertRaises(YawResponseError):
            assess_yaw_reversal(observed(-.36, 50), observed(+.36, -50),
                                idle_median_dx=float("inf"))


if __name__ == "__main__":
    unittest.main()
