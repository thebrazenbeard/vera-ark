# Skill branch: camera panning and yaw

**Branch:** skill/camera-yaw-evidence-20261013. **Status:** experimental reviewed camera calibration; no live output.

The module `vera_ark.skill_camera` distinguishes a controller input, a reviewed landmark shift, and a verified game-camera turn. A static landmark should drift opposite the camera yaw direction in the image. The module does **not** infer degrees of rotation from frame RGB change. Dynamic targets, animations, inconsistent drift, missing neutral release and unreviewed changes cannot improve the yaw proposal.

## Observed evidence

- `look01`: right stick `x=+0.38` for 230 ms, neutral released; frame mean RGB delta approximately `[48.86, 44.62, 40.41]`.
- `look02`: right stick `x=+0.75` for 250 ms, neutral released; frame mean RGB delta approximately `[68.86, 66.82, 66.32]`. After this action, the triceratops shifted to the left of the image and a larger section of sea/shoreline became visible. This is **provisional** support for right-stick positive turning the camera right; magnitude-to-degrees remains unknown.
- `look03`: intended right stick negative input while Chiaki had been minimized. The resultant capture was a 160×28 all-black rectangle, **invalid for yaw assessment**. Later restoration recovered a normal 974×1039 game window image and returned the prior minimized state.

## Next experiment

Bind and verify the current Chiaki HWND; restore the window only for bounded observation, and verify a nonblack game-frame crop before any controller action. Compare fixed rocks/shoreline across short pan experiments while avoiding animal-follow animations as the sole evidence. Stop and force neutral on capture or window failure.

This is a pure learning-policy module only. It must not independently construct a live gamepad or change the existing `vera_ark` loopback backend. Proposals carry `automatic_execution_permitted=False`.

## Live camera-response bracketing — subsequent supervised beach session

A new scoped Chiaki-ng capture (1160×1039 window) showed first-person gameplay with the beach, shoreline, fixed rocks, and forest. A small orange creature was at screen-left; it was not approached, attacked or assumed harmless. All subsequent trials were stationary camera controls. Every VDS4 pulse was neutral-released, screenshots passed a non-gray content check, and final game-frame readback showed normal beach gameplay.

A **bidirectional reversal test**, both 240 ms, tracked mostly fixed visual features in a beach ROI:

| Right-stick X | Median fixed-scene X image shift | Median Y shift | Tracks |
| ---: | ---: | ---: | ---: |
| −0.36 | +50.00 px | −0.15 px | 214 |
| +0.36 | −56.45 px | +0.42 px | 196 |

The signs reverse as expected for camera yaw, with negligible median vertical shift. Camera speed in angular units is **unknown**. This does not independently establish that the controller is present across sessions.

A follow-up same-process, same-scene **control-response bracket** used matched 240ms input pulses:

| Right-stick X | Median fixed-scene X shift | Tracks |
| ---: | ---: | ---: |
| −0.20 | 0.00 px | 209 |
| −0.28 | +14.34 px | 210 |
| +0.36 | −56.35 px | 188 |

This places a provisional response transition *somewhere in the tested interval* between 0.20 and 0.28, under the particular Chiaki/game scene and timing. It is **not** proof of a device-wide deadzone, exact threshold, or calibrated angle. The next bounded learning proposal is an **unexecuted** −0.24/240ms test, which would narrow the bracket if both observations remain valid. Historical replay must not promote an image shift without static-scene evidence and neutral release.

The pure policy `skill_camera_response.py` and its dedicated tests are separated from the real controller transport; it performs two tasks: check direction-reversing yaw observations and propose a midpoint under tightly controlled, reviewed weak/strong pulses. No command is issued by the module; every output has `automatic_execution_permitted=False`.

> **HOSTILE REVIEW — PARTIALLY ACCEPTED:** A zero-image-motion short pulse may be caused by controller lifecycle, focus, video latency, a game pause, or measurement sensitivity—not only stick deadzone. Matched duration, a single connected vgamepad process, valid before/after frames and the strong reverse-motion control narrow those alternatives but do not eliminate them. Therefore retain the result as a *scene-specific candidate response bracket* and demand repetition after reconnect or changed terrain before raising confidence.

Raw screenshots and action receipts remain private on Lappy. No secret, server command or autonomous runtime is included in this repository.
