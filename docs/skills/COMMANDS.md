# Skill branch: menu and command state

**Branch:** skill/command-state-evidence-20261013. **Status:** pure UI-state planner, with no controller input, credentials or authenticated server effect.

The module \`vera_ark.skill_commands\` enforces a small finite-state sequence: GAMEPLAY → PAUSE_MENU → ADMIN_BAR → COMMAND_BUTTON_SELECTED → observation after one submit. It also recognizes RESPAWN, TEXT_KEYBOARD, and UNKNOWN as fail-closed states. It only plans an isolated UI operation, with \`automatic_execution_permitted=False\`; a separate authorized controller adapter would still need explicit live binding and a release guarantee.

The username, admin password and any credential-containing text are **not** passed to this module or logged. The only command text eligible for screen comparison is credential-free \`cheat god\`, supplied by the user. A submitted \`cheat god\` **toggles** immunity rather than safely confirming a status, so a second invocation must be blocked after a submission within the same episode. A blank confirmation is **not** evidence of failure, nor reason to resend. User-reported god mode after personal takeover is an input fact; this branch does not claim to have independently verified immunity.

## Actual discovered failure modes

- While the survivor is dead, Options can open a pause overlay, but the admin gesture was not observed to expose the bar.
- PS4 on-screen keyboard focus, capitalization/layout, and controller lifecycle are separate state machines. A lost keyboard means further D-pad/Cross input may reach live gameplay.
- Screenshot observations have to be current and window-scoped. Do not press Cross on an assumed command button based on a stale frame.
- An earlier deliberate user takeover completed the setup; the assistant should not repeat the admin command in pursuit of cosmetic proof.

This module is deliberately independent of movement/camera calibration, the PR #9 local-first trial service, and PR #10 window/temporal perception. It supplies only safe potential *next* UI operations for an external reviewer.
