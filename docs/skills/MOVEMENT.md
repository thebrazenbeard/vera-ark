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

## Forward/backward reversal with a no-input baseline

After finding the first directional strafe results, a subsequent bounded test used the **same scene, same Chiaki window, and repeated valid-game-frame checks**, with OpenCV Shi–Tomasi corner detection plus pyramidal Lucas–Kanade flow. Track summaries are **image-space estimates**, not real-world positions.

On the first trial, a 650ms no-input baseline tracked 349 image features and showed median motion ~0 pixels in both upper and lower image bands. The survivor then received four neutral-separated left-stick `y=+0.50` pulses, each 245ms. In the post-action image, approximately 314 features tracked; median lower-band optical flow was `(+7.59, -4.53)` pixels, compared with upper-band `(+0.62, +0.81)`.

A second trial used a new ~600ms idle baseline tracking 350 features with ~0 median movement, followed by four neutral-separated `y=-0.50` 245ms pulses. Approximately 324 features were tracked afterward; median lower-band flow was `(-8.25, +6.58)`, versus upper-band `(-0.76, -1.00)`.

The **near-opposite lower-band flow**, the static idle baselines, and the smaller upper-band changes jointly support a reversible vertical-stick movement response. This is stronger than the earlier 100–250ms attempts, which lacked enough detectable motion. The captured frames and raw local receipts remain private on Lappy; no scene location, server credentials, or images are committed here.

`skill_movement_axial.py` is a *pure* checked evaluator for summaries with explicit uncertainty gates. It requires valid captures, verified release, reviewed camera stability, sufficient tracked features, a quiet idle baseline, stronger lower-band than upper-band motion, and nearly opposite action responses. It returns `CANDIDATE_OPPOSED_VERTICAL_MOVEMENT` at most, with `automatic_reward_permitted=False`. `skill_movement_geometry.py` similarly handles reviewed left/right landmark tracks with a matched no-input baseline.

**HOSTILE REVIEW — PARTIALLY ACCEPTED:** Upper/lower image bands are **not calibrated depths**; a moving camera, terrain slope, or independent object animations can also produce spatially varying flow. The current tests exercise correctly bounded *synthetic inputs shaped like the measurements*, not independently measured ARK coordinates. Do not call exact forward/backward velocity, route completion, or real-world RL competence qualified. The next trial should combine a bounded camera turn and a short forward move, observing each stage separately before learning any compound skill.

Research basis: ARK's documented PlayStation [default movement controls](https://ark.wiki.gg/wiki/Hotkeys) agree with the stick actions tested. Hierarchical skill progression follows the separation of initiation, policy and termination in the [options framework](https://doi.org/10.1016/S0004-3702(99)00052-1); this branch does not claim a full options agent or deployed runtime.
