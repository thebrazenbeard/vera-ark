"""Fail-closed console/menu command planning with no live transport or secrets."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CommandEvidenceError(ValueError):
    pass


class MenuStage(StrEnum):
    GAMEPLAY = "GAMEPLAY"
    PAUSE_MENU = "PAUSE_MENU"
    ADMIN_BAR = "ADMIN_BAR"
    COMMAND_BUTTON_SELECTED = "COMMAND_BUTTON_SELECTED"
    TEXT_KEYBOARD = "TEXT_KEYBOARD"
    RESPAWN = "RESPAWN"
    UNKNOWN = "UNKNOWN"


class CommandIntent(StrEnum):
    OPEN_PAUSE = "OPEN_PAUSE"
    OPEN_ADMIN_BAR = "OPEN_ADMIN_BAR"
    SUBMIT_GOD_ONCE = "SUBMIT_GOD_ONCE"


class PlannedOperation(StrEnum):
    PRESS_OPTIONS_ONCE = "PRESS_OPTIONS_ONCE"
    PRESS_ADMIN_GESTURE_ONCE = "PRESS_CROSS_ONCE = PRESS_CROSS_ONCE"
    SELECT_ADMIN_COMMAND_BUTTON = "SELECT_ADMIN_COMMAND_BUTTON"
    HALT_AND_OBSERVE = "HALT_AND_OBSERVE"


@dataclass(frozen=True, slots=True)
class CommandEvidence:
    stage: MenuStage
    reviewed_current_screen: bool
    recognized_command_text: str | None = None
    admin_access_operator_reported: bool = False
    same_episode_command_submitted: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.stage, MenuStage):
            raise CommandEvidenceError("stage must be a recognized MenuStage")
        for field_name in ("reviewed_current_screen", "admin_access_operator_reported", "same_episode_command_submitted"):
            if not isinstance(getattr(self, field_name), bool):
                raise CommandEvidenceError(field_name + " must be boolean")
        if self.recognized_command_text is not None:
            if not isinstance(self.recognized_command_text, str):
                raise CommandEvidenceError("recognized text must be text or None")
            # The command planner does not accept or echo credentials.
            if len(self.recognized_command_text) > 20 or self.recognized_command_text.strip().casefold() not in ("", "cheat god"):
                raise CommandEvidenceError("only the credential-free requested command may be compared")


@dataclass(frozen=True, slots=True)
class CommandProposal:
    operation: PlannedOperation
    evidence_basis: str
    automatic_execution_permitted: bool = False


def next_command_operation(intent: CommandIntent, evidence: CommandEvidence) -> CommandProposal:
    """Plan only a one-shot UI operation; it never issues DS4 input.

    ARK's god command is a toggle. Never infer absence of success from a blank
    notification or retry the same command without a fresh operator instruction.
    """
    if not isinstance(intent, CommandIntent) or not isinstance(evidence, CommandEvidence):
        raise CommandEvidenceError("invalid command intent or evidence")
    if not evidence.reviewed_current_screen or evidence.stage in (MenuStage.UNKNOWN, MenuStage.RESPAWN):
        return CommandProposal(PlannedOperation.HALT_AND_OBSERVE, "STAGE_NOT_VERIFIED_OR_RESPAWN")
    if evidence.stage is MenuStage.TEXT_KEYBOARD:
        return CommandProposal(PlannedOperation.HALT_AND_OBSERVE, "KEYBOARD_REQUIRES_SEPARATE_REVIEW")
    if intent is CommandIntent.OPEN_PAUSE and evidence.stage is MenuStage.GAMEPLAY:
        return CommandProposal(PlannedOperation.PRESS_OPTIONS_ONCE, "CURRENT_GAMEPLAY_SCREEN")
    if intent is CommandIntent.OPEN_ADMIN_BAR and evidence.stage is MenuStage.PAUSE_MENU:
        return CommandProposal(PlannedOperation.PRESS_ADMIN_GESTURE_ONCE, "CURRENT_PAUSE_SCREEN")
    if intent is CommandIntent.SUBMIT_GOD_ONCE:
        if evidence.same_episode_command_submitted:
            return CommandProposal(PlannedOperation.HALT_AND_OBSERVE, "NO_REPEAT_OF_GOD_TOGGLE")
        if not evidence.admin_access_operator_reported:
            return CommandProposal(PlannedOperation.HALT_AND_OBSERVE, "ADMIN_ACCESS_NOT_REPORTED")
        if (evidence.recognized_command_text or "").strip().casefold() != "cheat god":
            return CommandProposal(PlannedOperation.HALT_AND_OBSERVE, "COMMAND_TEXT_MISMATCH")
        if evidence.stage is MenuStage.ADMIN_BAR:
            return CommandProposal(PlannedOperation.SELECT_ADMIN_COMMAND_BUTTON, "TEXT_PRESENT_BUTTON_NOT_SELECTED")
        if evidence.stage is MenuStage.COMMAND_BUTTON_SELECTED:
            return CommandProposal(PlannedOperation.PRESS_CROSS_ONCE, "ONE_SHOT_TOGGLE_REQUEST")
    return CommandProposal(PlannedOperation.HALT_AND_OBSERVE, "NO_SAFE_STAGE_TRANSITION")
