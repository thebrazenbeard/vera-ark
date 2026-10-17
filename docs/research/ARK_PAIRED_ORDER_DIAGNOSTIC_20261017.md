# Offline paired-order diagnostic — T32

Scope: source-only synthetic diagnostic for caller-declared baseline/candidate execution order. This document is a candidate; no gameplay, installation, causal-learning qualification, or independent review. The evaluator and tests are not yet published.

Parent: vera-ark main 7e4b8469c6c4d5918556e3f80a54f9335238a0c3. Avoids open PRs #12, #13, #14, #21, #22.

Order imbalance can make candidate reward differences appear favorable even when the first run receives an advantage. The local candidate validates declared per-trial order and outcome-digest bindings, reports order-stratified diagnostics, and leaves standardized score unavailable where a holdout group lacks both orders. All source hashes and rewards are caller controlled; actual execution chronology remains unverified.
