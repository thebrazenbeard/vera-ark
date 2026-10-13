import unittest

from vera_ark.skill_movement_axial import (
    AxialEpisode, AxialEvidenceError, FlowBands,
    assess_opposite_vertical_input,
)


def frame(lower, upper, *, scene="BEACH", geometry=(1333, 1039),
          valid=True, release=True, camera=True, count=140, pulses=4):
    return AxialEpisode(
        scene, geometry,
        FlowBands(upper[0], upper[1], lower[0], lower[1], count, count),
        valid, release, camera, 245, pulses,
    )


class AxialMotionTests(unittest.TestCase):
    def setUp(self):
        self.idle = frame((0., 0.), (0., 0.), pulses=0)
        # These are manually transcribed aggregate values for a synthetic
        # regression fixture; NOT independently attested ARK ground truth.
        self.forward = frame((7.59, -4.53), (0.62, 0.81))
        self.backward = frame((-8.25, 6.58), (-0.76, -1.00))

    def test_opposite_live_shaped_aggregate_yields_only_candidate(self):
        result = assess_opposite_vertical_input(self.idle, self.forward, self.backward)
        self.assertEqual(result.disposition, "CANDIDATE_OPPOSED_VERTICAL_MOVEMENT")
        self.assertEqual(result.basis, "IDLE_CORRECTED_OPPOSED_FOREGROUND_PARALLAX")
        self.assertTrue(result.candidate_only)
        self.assertFalse(result.automatic_reward_permitted)
        self.assertEqual(result.forward_near_vector, (7.59, -4.53))

    def test_no_idle_baseline_never_claims_motion(self):
        self.assertEqual(
            assess_opposite_vertical_input(None, self.forward, self.backward).basis,
            "IDLE_BASELINE_REQUIRED",
        )

    def test_scene_and_capture_geometry_mismatch(self):
        for different in (
            frame((-8.25, 6.58), (-0.76, -1), scene="FOREST"),
            frame((-8.25, 6.58), (-0.76, -1), geometry=(1920, 1080)),
        ):
            self.assertEqual(
                assess_opposite_vertical_input(self.idle, self.forward, different).basis,
                "SCENE_OR_GEOMETRY_MISMATCH",
            )

    def test_invalid_frames_release_and_orientation_fail_closed(self):
        for modified in (
            frame((7.59, -4.53), (0.62, 0.81), valid=False),
            frame((7.59, -4.53), (0.62, 0.81), release=False),
            frame((7.59, -4.53), (0.62, 0.81), camera=False),
        ):
            self.assertEqual(
                assess_opposite_vertical_input(self.idle, modified, self.backward).basis,
                "CAPTURE_RELEASE_OR_CAMERA_UNVERIFIED",
            )

    def test_high_idle_drift_is_not_player_motion(self):
        moving_baseline = frame((5, 0), (5, 0), pulses=0)
        self.assertEqual(
            assess_opposite_vertical_input(moving_baseline, self.forward, self.backward).basis,
            "EXCESSIVE_IDLE_DRIFT",
        )

    def test_camera_pan_without_parallax_rejected(self):
        rigid_pan = frame((8, -3), (8, -3))
        self.assertEqual(
            assess_opposite_vertical_input(self.idle, rigid_pan, frame((-8, 3), (-8, 3))).basis,
            "NO_NEAR_FAR_MOTION_DIFFERENCE",
        )

    def test_equal_sign_control_pair_not_reverse(self):
        self.assertEqual(
            assess_opposite_vertical_input(self.idle, self.forward, self.forward).basis,
            "RESPONSES_NOT_NEAR_OPPOSITE",
        )

    def test_tiny_change_not_learned(self):
        forward = frame((1.1, -.3), (.2, .1))
        backward = frame((-1.2, .3), (-.2, -.1))
        self.assertEqual(
            assess_opposite_vertical_input(self.idle, forward, backward).basis,
            "MOTION_BELOW_MEASUREMENT_THRESHOLD",
        )

    def test_no_action_or_too_few_features_rejected(self):
        self.assertEqual(
            assess_opposite_vertical_input(self.idle,
                frame((8, -4), (.5, .8), pulses=0), self.backward).basis,
            "CONTROL_PROTOCOL_MISMATCH",
        )
        self.assertEqual(
            assess_opposite_vertical_input(self.idle,
                frame((8, -4), (.5, .8), count=25), self.backward).basis,
            "TOO_FEW_TRACKED_FEATURES",
        )

    def test_invalid_data_and_nonfinite_values(self):
        for bad in (float("nan"), float("inf"), True, -10000):
            with self.subTest(bad=bad), self.assertRaises(AxialEvidenceError):
                FlowBands(bad, 0., 1., 0., 150, 150)
        with self.assertRaises(AxialEvidenceError):
            frame((1, 0), (0, 0), release=False, pulses=0)
        with self.assertRaises(AxialEvidenceError):
            assess_opposite_vertical_input("idle", self.forward, self.backward)


if __name__ == "__main__":
    unittest.main()
