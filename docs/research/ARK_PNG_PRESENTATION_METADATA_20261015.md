# ARK offline PNG presentation metadata audit — 2026-10-15

Source cut: vera-ark/main `7e4b8469c6c4d5918556e3f80a54f9335238a0c3`; vera-mono/main `16a2828dfa7fb7e6c0e19004f014bc68fc47badf`.

Scope: supplementary, pure-Python caller-supplied PNG evidence analysis. This is not a live controller route, capture attestation, or gameplay observation. The isolated research base includes frame-byte binding at `9176f4086a41f51571f8d9b7b0377e4b4e9acc17`.

Experiment: identical decoded RGBA8 samples can be paired with differing `gAMA`, `sRGB`, or `iCCP` chunks. Decoded sample equality must not be presented as display-color equality. An offline candidate now reports the number of decoded-pixel groups with disagreement in selected raw presentation metadata, without weakening cross-split duplicate rejection. `tEXt` differences do not trigger this warning.

Local synthetic test evidence: 47 focused tests passed, four subtests passed; Python compilation passed. Tests use generated 1×1 and 2×2 PNGs, not Chiaki captures. The complete source/tests are not asserted to be in this branch until verified by GitHub readback.

Internal hostile review (GPT-6/OpenAI): raw metadata comparison is not ICC color management, cannot establish rendering equality, and can miss undocumented presentation transformations. Fabricated frames and labels remain possible. Internal review is not independent review. No gameplay input was sent.
