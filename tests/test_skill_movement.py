import unittest

from vera_ark.skill_movement import (
    AssessmentProvenance, MovementAssessment, MovementDirection,
    MovementEvidenceError, MovementTrial, next_movement_proposal,
    supports_movement_adjustment,
)


class MovementSkillTests(unittest.TestCase):
    def test_unanchored_following_triceratops_does_not_score(self):
        trial = MovementTrial(
            MovementDirection.BACKWARD, 0.25, 200, True,
            MovementAssessment.PROGRESS,
            AssessmentProvenance.HUMAN_REVIEW,
            False, True,
        )
        self.assertFalse(supports_movement_adjustment(trial))
        proposal = next_movement_proposal([trial], desired_direction=MovementDirection.BACKWARD)
        self.assertEqual(proposal.outcome_basis, "UNKNOWN_NO_STATIC_LANDMARK_EVIDENCE")
        self.assertEqual(proposal.magnitude, 0.25)
        self.assertTrue(proposal.manual_review_required)

    def test_independent_progress_adjusts_next_trial_with_cap(self):
        trial = MovementTrial(
            MovementDirection.FORWARD, 0.49, 240, True,
            MovementAssessment.PROGRESS,
            AssessmentProvenance.STATIC_LANDMARK_REVIEW,
            True, False,
        )
        proposal = next_movement_proposal([trial])
        self.assertEqual((proposal.magnitude, proposal.duration_ms), (0.5, 250))
        self.assertEqual(proposal.outcome_basis, "REVIEWED_PROGRESS_PROVISIONAL")

    def test_regression_reduces_trial_not_repeats_hazard(self):
        trial = MovementTrial(
            MovementDirection.FORWARD, 0.45, 220, True,
            MovementAssessment.REGRESSION,
            AssessmentProvenance.HUMAN_REVIEW, True, False,
        )
        proposal = next_movement_proposal((trial,))
        self.assertEqual((proposal.magnitude, proposal.duration_ms), (0.15, 100))

    def test_unreleased_and_unknown_trials_do_not_train(self):
        unreleased = MovementTrial(
            MovementDirection.FORWARD, 0.3, 100, False,
            MovementAssessment.PROGRESS,
            AssessmentProvenance.HUMAN_REVIEW, True, False,
        )
        self.assertEqual(next_movement_proposal([unreleased]).magnitude, 0.25)
        self.assertEqual(next_movement_proposal([]).outcome_basis, "UNKNOWN_NO_STATIC_LANDMARK_EVIDENCE")

    def test_bounds_and_review_evidence(self):
        for bad in (float("nan"), float("inf"), True, -0.1, 0.51):
            with self.subTest(bad=bad), self.assertRaises(MovementEvidenceError):
                MovementTrial(MovementDirection.FORWARD, bad, 100, True)
        with self.assertRaises(MovementEvidenceError):
            MovementTrial(MovementDirection.FORWARD, 0.2, 251, True)
        with self.assertRaises(MovementEvidenceError):
            MovementTrial(MovementDirection.FORWARD, 0.2, 100, True, MovementAssessment.PROGRESS)
        with self.assertRaises(MovementEvidenceError):
            next_movement_proposal([MovementTrial(MovementDirection.FORWARD, 0.2, 100, True)] * 257)


if __name__ == "__main__":
    unittest.main()
