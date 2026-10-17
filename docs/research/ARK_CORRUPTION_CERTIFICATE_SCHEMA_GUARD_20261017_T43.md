# T43 — offline corruption certificate type integrity

Evidence: REPOSITORY_SOURCE + LOCAL SYNTHETIC TESTS only.

Source basis: vera-ark/main@7e4b8469c6c4d5918556e3f80a54f9335238a0c3; T40 source branch@2b4af5c; T42 exhaustive oracle local candidate, not yet published as source. Vera Mono main@16a2828dfa7fb7e6c0e19004f014bc68fc47badf.

Problem reproduced: Python dataclass annotations do not enforce runtime types. T42's exhaustive report crosscheck accepted `False` as a 0.0 score, `4.0` as integer pair_count 4, and falsey non-boolean attestation fields such as `[]`, `0`, `None`, and `""`. This incorrectly marked malformed evidence reports `valid=True`.

Candidate fix: exact float checks for scores/capacities, exact integer layout counts, exact boolean survival flag, and strict `is False` boolean-only unsupported attestations.

RED: 9/14 new tests failed against T42 candidate before fix. GREEN: 14/14 new tests and 386/386 cumulative synthetic tests passed; compileall passed. Local Linux Python test environment, not Lappy, not GitHub CI.

Internal hostile review — GPT-6 / OpenAI: type integrity does not authenticate rewards, establish causal learning, or independently review a frozen artifact. Exhaustive oracle shares the same macro estimator with greedy and is limited to 8 paired rows; floating near-zero boundaries remain unresolved.

Local candidate archive: vera_ark_corruption_certificate_type_guard_candidate_20261017_t43.zip
SHA-256: fb8acdd142f4cfcb9ce7303bc3420e127ac7cc11b06b6e0f292a15c8790dc8fa

No gameplay, controller, install, protected effects, or main mutation. Remote source/tests and Draft PR require separate verified publication.
