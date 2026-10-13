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
