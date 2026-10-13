import unittest

from vera_ark.skill_movement_geometry import (
    DepthBand, GeometryEvidenceError, LandmarkFramePair, LateralAction,
    TrackedLandmark, assess_lateral_motion, assess_reversed_lateral_pair,
)


_NAMES = ("NEAR_A", "NEAR_B", "NEAR_C", "FAR_A", "FAR_B")
_BANDS = (DepthBand.NEAR,) * 3 + (DepthBand.FAR,) * 2


def frame(xs, *, ys=None, scene="BEACH", geometry=(1333, 1039),
          valid=True, neutral=True, yaw=True, reviewed=True,
          correlation=0.94):
    if ys is None:
        ys = (0,) * 5
    return LandmarkFramePair(
        scene_id=scene,
        image_geometry=geometry,
        tracks=tuple(
            TrackedLandmark(name, band, float(x), float(y), correlation, reviewed)
            for name, band, x, y in zip(_NAMES, _BANDS, xs, ys)
        ),
        valid_before_after=valid,
        neutral_release_verified=neutral,
        camera_orientation_stable_reviewed=yaw,
    )


class LandmarkMotionTests(unittest.TestCase):
    def setUp(self):
        self.baseline = frame((0, 0, 0, 0, 0))
        # Approximate magnitude patterns from the live reversible strafe
        # trial. These are simulated reviewed inputs, NOT re-attested frames.
        self.left = frame((26, 10, 7, 4, 5))
        self.right = frame((-24, -17, -6, -3, -4))

    def test_live_pattern_left_and_right_is_only_candidate(self):
        left = assess_lateral_motion(LateralAction.STRAFE_LEFT, self.left, self.baseline)
        right = assess_lateral_motion(LateralAction.STRAFE_RIGHT, self.right, self.baseline)
        self.assertEqual(left.disposition, "CANDIDATE_LATERAL_TRANSLATION")
        self.assertEqual(right.disposition, "CANDIDATE_LATERAL_TRANSLATION")
        self.assertEqual(left.usable_landmarks, 5)
        self.assertTrue(assess_reversed_lateral_pair(left, right))
        self.assertFalse(left.autonomous_reward_permitted)
        self.assertFalse(right.autonomous_reward_permitted)

    def test_no_input_baseline_required(self):
        result = assess_lateral_motion(LateralAction.STRAFE_LEFT, self.left, None)
        self.assertEqual(result.evidence_basis, "NO_NO_INPUT_BASELINE")

    def test_baseline_correction_cancels_camera_idle_drift(self):
        baseline = frame((3, 3, 3, 3, 3))
        # Entire observation shifted equally due capture drift.
        static = frame((3, 3, 3, 3, 3))
        result = assess_lateral_motion(LateralAction.STRAFE_LEFT, static, baseline)
        self.assertEqual(result.evidence_basis, "INCONSISTENT_DIRECTION")

    def test_rigid_camera_pan_not_confused_with_translation(self):
        result = assess_lateral_motion(
            LateralAction.STRAFE_LEFT,
            frame((10, 10, 10, 10, 10)),
            self.baseline,
        )
        self.assertEqual(result.evidence_basis, "PARALLAX_NOT_SEPARABLE_FROM_PAN_OR_NOISE")

    def test_wrong_direction_does_not_qualify(self):
        result = assess_lateral_motion(LateralAction.STRAFE_LEFT, self.right, self.baseline)
        self.assertEqual(result.evidence_basis, "INCONSISTENT_DIRECTION")

    def test_scene_or_window_geometry_change_fails_closed(self):
        scene = frame((26, 10, 7, 4, 5), scene="FOREST")
        geometry = frame((26, 10, 7, 4, 5), geometry=(1920, 1080))
        for observation in (scene, geometry):
            self.assertEqual(
                assess_lateral_motion(LateralAction.STRAFE_LEFT, observation, self.baseline).evidence_basis,
                "SCENE_OR_GEOMETRY_MISMATCH",
            )

    def test_gray_frame_unreleased_pad_and_camera_yaw_fail_closed(self):
        for observation in (
            frame((26, 10, 7, 4, 5), valid=False),
            frame((26, 10, 7, 4, 5), neutral=False),
            frame((26, 10, 7, 4, 5), yaw=False),
        ):
            result = assess_lateral_motion(LateralAction.STRAFE_LEFT, observation, self.baseline)
            self.assertEqual(result.evidence_basis, "CAPTURE_RELEASE_OR_YAW_UNVERIFIED")

    def test_unreviewed_or_low_quality_landmarks_fail_closed(self):
        for observation in (
            frame((26, 10, 7, 4, 5), reviewed=False),
            frame((26, 10, 7, 4, 5), correlation=0.40),
        ):
            result = assess_lateral_motion(LateralAction.STRAFE_LEFT, observation, self.baseline)
            self.assertEqual(result.evidence_basis, "INSUFFICIENT_REVIEWED_DEPTH_DIVERSITY")

    def test_large_vertical_camera_shift_not_lateral_translation(self):
        result = assess_lateral_motion(LateralAction.STRAFE_LEFT,
            frame((26, 10, 7, 4, 5), ys=(8, 7, 9, 8, 6)), self.baseline)
        self.assertEqual(result.evidence_basis, "EXCESSIVE_VERTICAL_IMAGE_SHIFT")

    def test_invalid_records(self):
        for bad in (float("nan"), float("inf"), 4096, True):
            with self.subTest(bad=bad), self.assertRaises(GeometryEvidenceError):
                TrackedLandmark("ROCK", DepthBand.NEAR, bad, 0, .9, True)
        with self.assertRaises(GeometryEvidenceError):
            TrackedLandmark("ROCK", DepthBand.NEAR, 0, 0, 1.1, True)
        with self.assertRaises(GeometryEvidenceError):
            LandmarkFramePair("BEACH", (1333, 1039),
                (TrackedLandmark("A", DepthBand.NEAR, 1, 0, 0.9, True),) * 2,
                True, True, True)
        with self.assertRaises(GeometryEvidenceError):
            assess_lateral_motion("STRAFE_LEFT", self.left, self.baseline)


if __name__ == "__main__":
    unittest.main()
