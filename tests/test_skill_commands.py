import unittest

from vera_ark.skill_commands import (
    CommandEvidence, CommandEvidenceError, CommandIntent,
    MenuStage, PlannedOperation, next_command_operation,
)


class CommandSkillTests(unittest.TestCase):
    def test_never_submit_without_observed_selected_button(self):
        for stage in (MenuStage.UNKNOWN, MenuStage.RESPAWN, MenuStage.TEXT_KEYBOARD, MenuStage.GAMEPLAY):
            proposal = next_command_operation(
                CommandIntent.SUBMIT_GOD_ONCE,
                CommandEvidence(stage, True, "cheat god", True),
            )
            self.assertIs(proposal.operation, PlannedOperation.HALT_AND_OBSERVE)

    def test_one_shot_command_when_operator_reports_admin(self):
        evidence = CommandEvidence(MenuStage.ADMIN_BAR, True, "Cheat god", True)
        proposal = next_command_operation(CommandIntent.SUBMIT_GOD_ONCE, evidence)
        self.assertIs(proposal.operation, PlannedOperation.SELECT_ADMIN_COMMAND_BUTTON)
        selected = CommandEvidence(MenuStage.COMMAND_BUTTON_SELECTED, True, "cheat god", True)
        proposal = next_command_operation(CommandIntent.SUBMIT_GOD_ONCE, selected)
        self.assertIs(proposal.operation, PlannedOperation.PRESS_CROSS_ONCE)
        self.assertFalse(proposal.automatic_execution_permitted)

    def test_never_toggle_again_after_submission(self):
        evidence = CommandEvidence(MenuStage.COMMAND_BUTTON_SELECTED, True, "cheat god", True, True)
        proposal = next_command_operation(CommandIntent.SUBMIT_GOD_ONCE, evidence)
        self.assertIs(proposal.operation, PlannedOperation.HALT_AND_OBSERVE)
        self.assertEqual(proposal.evidence_basis, "NO_REPEAT_OF_GOD_TOGGLE")

    def test_secret_fails_closed_and_no_unconfirmed_admin(self):
        with self.assertRaises(CommandEvidenceError):
            CommandEvidence(MenuStage.ADMIN_BAR, True, "enablecheats password", True)
        evidence = CommandEvidence(MenuStage.COMMAND_BUTTON_SELECTED, True, "cheat god", False)
        self.assertIs(
            next_command_operation(CommandIntent.SUBMIT_GOD_ONCE, evidence).operation,
            PlannedOperation.HALT_AND_OBSERVE,
        )

    def test_menu_navigation_requires_current_screen(self):
        gameplay = CommandEvidence(MenuStage.GAMEPLAY, True)
        paused = CommandEvidence(MenuStage.PAUSE_MENU, True)
        self.assertIs(
            next_command_operation(CommandIntent.OPEN_PAUSE, gameplay).operation,
            PlannedOperation.PRESS_OPTIONS_ONCE,
        )
        self.assertIs(
            next_command_operation(CommandIntent.OPEN_ADMIN_BAR, paused).operation,
            PlannedOperation.PRESS_ADMIN_GESTURE_ONCE,
        )
        stale = CommandEvidence(MenuStage.GAMEPLAY, False)
        self.assertIs(
            next_command_operation(CommandIntent.OPEN_PAUSE, stale).operation,
            PlannedOperation.HALT_AND_OBSERVE,
        )


if __name__ == "__main__":
    unittest.main()
