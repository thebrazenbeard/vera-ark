# Skill branch: movement (on foot)

**Branch:** skill/movement-evidence-20261013. **Status:** experimental policy source, not live gameplay autonomy.

The module `vera_ark.skill_movement` records bounded on-foot movement trials and proposes a next experiment only from reviewed evidence. It requires a verified neutral controller release, an independent fixed scene landmark, and an explicit human or static-landmark review before an outcome can change the movement magnitude/duration. A following triceratops is not a stationary yardstick. This policy neither captures frames nor calls `vgamepad`; proposals are never execution authority.

## Live calibration starting evidence

- `walk01`: Lappy/Chiaki, DS4 left stick `x=0, y=-0.25`, 200 ms; neutral release verified. Mean absolute RGB difference `[15.18, 14.01, 13.04]`; actual world displacement **unknown**.
- `walk02`: DS4 left stick `x=0, y=-0.55`, 250 ms; neutral release verified. Mean absolute RGB difference `[30.71, 26.94, 23.59]`; animal moving/following, actual world displacement **unknown**. This live intensity **exceeds** the initial skill policy ceiling of 0.5, and is retained only as historical evidence; no skill API accepts or silently normalizes it.
- Current user-reported god mode is **not** a movement measurement. No saddle or mounted calibration is assumed.

## Next controlled test

Turn toward a fixed distant shoreline/rock landmark, confirm that scene type is gameplay and not a minimized/black capture, then perform one short left-stick action with no nearby obstacles. Release and capture. Classify outcome as `UNKNOWN` unless stable landmark displacement provides defensible evidence, and keep progression bounded.

The module returns an experimental `MovementProposal` with `manual_review_required=True`. No autonomous loop, world-coordinate calibration, controller installation, Physica-derived speed, or runtime binding is claimed. Future integration must import the common trial-evidence contract from the existing trial-controller PR after review, not copy its dispatch authority.

## Live left/right strafe reversal evidence (later 2026-10-13)

The previously unresolved forward/backward control trials are **still unknown**: repeated left-stick Y-positive/Y-negative pulses yielded zero or approximately one-pixel fixed-rock shifts. A separate right-stick X-positive input created a large, clearly visible camera rotation, confirming controller input can reach the game without proving left-stick movement.

Two subsequent **on-foot lateral** experiments used the same safe beach and static rock landmarks. Each direction used three discrete 230ms stick pulses, with a neutral release after every pulse, and before/after scoped Chiaki screenshots. The raw frames and local action receipts remain private on Lappy.

| Trial | Left-stick X | Five fixed-landmark X shifts (pixels) | Interpretation |
| --- | ---: | --- | --- |
| STRAFE01 | -0.50 | +7, +4, +10, +26, +5 | Left strafe provisionally supported |
| STRAFE02 | +0.50 | -6, -3, -17, -24, -4 | Opposite strafe provisionally supported |

Template correlations were roughly 0.79–0.99. The closest foreground rocks exhibited substantially larger apparent shifts than distant rocks, consistent with translational parallax; the **sign reversal on opposite controls** argues against an animation-only explanation. This is credible direct gameplay evidence for lateral movement, **not** an exact world-distance/velocity calibration, automated competence qualification, human-independent attestation, or evidence that left-stick Y has been calibrated. Two directions tested against the same location do not prove terrain generalization.

The future measurement module should baseline no-input landmark drift, reject camera pan during movement measurement, require several independently anchored features (not a following tame), and compare per-distance parallax in fixed ROIs. A reliable result should feed a `STATIC_LANDMARK_REVIEW` provenance entry through the experimental learning interface without silently declaring real-world coordinates, physics parameters, or acquired skill mastery.

Recorded privately in local Blotter at episode sequences 202–206. Do not add public/raw image content or credentials to this branch.
