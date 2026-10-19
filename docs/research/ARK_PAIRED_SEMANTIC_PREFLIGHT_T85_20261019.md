# T85 — Paired semantic preflight (offline candidate)

Evidence class: LOCAL SYNTHETIC TEST; not a runtime/gameplay observation.

Base: vera-ark main `7e4b8469c6c4d5918556e3f80a54f9335238a0c3`; prior T74 published research commit `344387989d36032311668000c1af0173f3ac71e5`. This branch is an isolated evidence placeholder until the accumulated T75–T85 source and tests can be published. **The code and tests described below are not present on this branch.**

T84 validated only roster tuple shapes before reading caller-controlled Mapping rows. Invalid roster ID syntax, duplicate IDs, and malformed metric ranges could still trigger arbitrary Mapping reads before validation. T85 extracts the existing canonical roster/range validation into a shared helper, and performs semantic preflight before touching any row mapping in the three offline paired evaluators.

Red: 39 adversarial subcases failed before repair (untrusted row touched). Green: 4 new test methods, 524/524 cumulative offline synthetic tests pass, normal/optimized/extracted archive; compileall and ZIP integrity pass.

Local artifact: `vera_ark_paired_semantic_preflight_full_candidate_20261019_t85.zip` SHA-256 `70b10415c744c0f069cf2a312620a8956f3fdc96fb386952b0abf0c99de6556d`.

Lappy Executor observed connected, but no matching Chiaki/ARK/Steam/DS4/Remote Play process. No live scene/controller route verification and **zero gameplay inputs**. No deployment, merge, source publication, authenticated observations, causal learning, or independent review.

Internal hostile review: Semantic preflight closes this demonstrated malformed-declaration access path, but valid hostile Mapping objects can still execute arbitrary Python during snapshot. It does not authenticate data provenance, establish atomic capture, or prove gameplay learning. Independent exact-head review remains required once code is published.
