import unittest

from vera_ark.skill_camera import (
    CameraAssessment, CameraDirection, CameraEvidenceError, CameraProvenance,
    CameraTrial, evidence_consistent_with_yaw, next_camera_proposal,
)


class CameraSkillTests(unittest.TestCase):
    def test_dynamic_dinosaur_not_static_yaw_evidence(self):
        trial = CameraTrial(
            CameraDirection.RIGHT, 0.38, 230, True, False,
            CameraDirection.LEFT, CameraAssessment.OBSERVED_TURN,
            CameraProvenance.SCENE_REVIEW,
        )
        self.assertFalse(evidence_consistent_with_yaw(trial))
        proposal = next_camera_proposal([trial])
        self.assertEqual(proposal.evidence_basis, "UNKNOWN_NO_INDEPENDENT_LANDMARK")
        self.assertFalse(proposal.automatic_execution_permitted)

    def test_reviewed_static_landmark_supports_yaw(self):
        trial = CameraTrial(
            CameraDirection.RIGHT, 0.72, 235, True, True,
            CameraDirection.LEFT, CameraAssessment.OBSERVED_TURN,
            CameraProvenance.SCENE_REVIEW,
        )
        self.assertTrue(evidence_consistent_with_yaw(trial))
        proposal = next_camera_proposal([trial])
        self.assertEqual((proposal.magnitude, proposal.duration_ms), (0.75, 250))

    def test_unreleased_or_wrong_drift_fails_closed(self):
        for released, shift in ((False, CameraDirection.LEFT), (True, CameraDirection.RIGHT)):
            trial = CameraTrial(
                CameraDirection.RIGHT, 0.4, 110, released, True,
                shift, CameraAssessment.OBSERVED_TURN,
                CameraProvenance.HUMAN_REVIEW,
            )
            self.assertFalse(evidence_consistent_with_yaw(trial))

    def test_bounds_and_required_provenance(self):
        for bad in (float("nan"), float("-inf"), True, 0, 0.8):
            with self.subTest(bad=bad), self.assertRaises(CameraEvidenceError):
                CameraTrial(CameraDirection.RIGHT, bad, 200, True, True)
        with self.assertRaises(CameraEvidenceError):
            CameraTrial(
                CameraDirection.RIGHT, 0.3, 100, True, True,
                CameraDirection.LEFT, CameraAssessment.OBSERVED_TURN,
            )
        with self.assertRaises(CameraEvidenceError):
            next_camera_proposal([CameraTrial(CameraDirection.RIGHT, 0.3, 100, True, True)] * 257)


if __name__ == "__main__":
    unittest.main()
