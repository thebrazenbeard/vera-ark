# T59 offline design-binding evaluation

Exact base: vera-ark main 7e4b8469c6c4d5918556e3f80a54f9335238a0c3.
Scope: new pure offline design-binding module and adversarial tests.
The SHA-256 digest binds trial IDs, group IDs, block IDs, and first-arm declarations. It does not bind outcome values.

Verification: 18 focused tests and 153 cumulative T50-T59 synthetic tests passed locally on the candidate source; Python compilation passed. Published source and test blob hashes match the locally tested files. These results are not gameplay evidence or independent review.

Limitations: a digest can be minted after observing outcomes; an independently preserved pre-outcome commitment is still required. Caller-supplied observations are unauthenticated. Block exchangeability, causal learning, gameplay route, and controller release are unverified.

Internal adversarial review: a post-hoc modified design with a freshly generated digest passes. That falsifier is included in the regression suite. No runtime integration, controller input, installation, or main merge is proposed.
