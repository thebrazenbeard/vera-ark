# ARK T36 — offline negative-control diagnostic (research only)

Base: `vera-ark/main@7e4b8469c6c4d5918556e3f80a54f9335238a0c3`.
Open Draft collision audit: #12 movement, #13 camera, #14 commands, #21 PNG, #22 session ledger. No delegated subject touched.

The standalone local candidate validates matched primary/negative-control paired deltas, unique trial IDs, finite bounded rewards, two or more scene groups, and both declared first-arm cells in every group. It reports equal-group/equal-order macro deltas, descriptive primary-minus-control, and leave-one-group-out sensitivity.

Synthetic counterexample: primary +0.20, negative control +0.30, descriptive difference -0.10. The apparent advantage does not survive subtraction. **This is not a causal adjustment or proof of a valid negative control.**

Local Python 3.13 tests: 41/41 focused; 263/263 cumulative; 41/41 standalone minimal package; compilation and extracted ZIP retest passed. New source SHA-256: `6549972c4a581ee7bead6d2a67c5f19d70e69b3e5ab3c3640d83cf7ede0d6263`. Candidate ZIP SHA-256: `50cc312e8e6a4b377b0c5a8931ea9c0097e3bc3dca503c08732c874d82eb8457`.

**Publication:** source and tests were blocked from GitHub publication and remain local. This note does not qualify deployment or gameplay.

> INTERNAL HOSTILE REVIEW — GPT-6 / OpenAI: Caller-controlled outcomes, grouping, chronology, and negative-control definition remain forgeable. A negative control that responds to the candidate can manufacture false reversals. Complete order cells are not randomized execution. No authentic gameplay, independent review, statistical significance, or causal learning established.

No game inputs, merges, installations, credential changes, protected mutations, or autonomous gameplay.
