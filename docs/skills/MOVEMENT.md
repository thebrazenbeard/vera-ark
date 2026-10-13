# Skill branch: movement (on foot)

**Branch:** skill/movement-evidence-20261013. **Status:** experimental policy source, not live gameplay autonomy.

The module \`vera_ark.skill_movement\` records bounded on-foot movement trials and proposes a next experiment only from reviewed evidence. It requires a verified neutral controller release, an independent fixed scene landmark, and an explicit human or static-landmark review before an outcome can change the movement magnitude/duration. A following triceratops is not a stationary yardstick. This policy neither captures frames nor calls \`vgamepad\`; proposals are never execution authority.

## Live calibration starting evidence

- \`walk01\`: Lappy/Chiaki, DS4 left stick \`x=0, y=-0.25\`, 200 ms; neutral release verified. Mean absolute RGB difference \`[15.18, 14.01, 13.04]\`; actual world displacement **unknown**.
- \`walk02\`: DS4 left stick \`x=0, y=-0.55\`, 250 ms; neutral release verified. Mean absolute RGB difference \`[30.71, 26.94, 23.59]\`; animal moving/following, actual world displacement **unknown**. This live intensity **exceeds** the initial skill policy ceiling of 0.5, and is retained only as historical evidence; no skill API accepts or silently normalizes it.
- Current user-reported god mode is **not** a movement measurement. No saddle or mounted calibration is assumed.

## Next controlled test

Turn toward a fixed distant shoreline/rock landmark, confirm that scene type is gameplay and not a minimized/black capture, then perform one short left-stick action with no nearby obstacles. Release and capture. Classify outcome as \`UNKNOWN\` unless stable landmark displacement provides defensible evidence, and keep progression bounded.

The module returns an experimental \`MovementProposal\` with \`manual_review_required=True\`. No autonomous loop, world-coordinate calibration, controller installation, Physica-derived speed, or runtime binding is claimed. Future integration must import the common trial-evidence contract from the existing trial-controller PR after review, not copy its dispatch authority.
