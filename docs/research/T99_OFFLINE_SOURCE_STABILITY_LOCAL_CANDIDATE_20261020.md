# T99 — offline caller-source stability guard (local candidate)

Date: 2026-10-20. Research only; no live game input or runtime admission.

SOURCE: vera-ark main `7e4b8469c6c4d5918556e3f80a54f9335238a0c3`; vera-mono main `16a2828dfa7fb7e6c0e19004f014bc68fc47badf`. Read Mono authority/effect/delegation contracts. Inspected five open Draft PRs #12–14 and #21–22, exact heads and changed paths; no overlapping edits.

TEST: T98 detached-receipt audit accepted an original caller-owned score change occurring after detachment. T99 adds an optional offline source-quiescence wrapper comparing pre/post original declaration fingerprints with the receipt's detached declaration hash. A stored-receipt variant also checks source agreement. No T98 source changed.

Red: 9 new tests errored before implementation; existing T98 accepted the controlled source-mutation counterexample. Green: 10/10 new tests; 618/618 cumulative synthetic tests under normal and optimized Python, including extracted archive; 128 seeded mutations; compileall, ZIP integrity, and 141 file hashes passed.

LOCAL CANDIDATE (not published source):
- `src/vera_ark/offline_paired_source_stability.py` SHA-256 `8e7156ae7b2caf1d9d5e03f31d5f0f5b0d9f2965dcc09680893d23026f853926`
- `tests/test_offline_paired_source_stability_t99.py` SHA-256 `3f448d8e7c4490eadd5102b7a2e006f10702f3be253aede7f4a228c68fd1b861`
- Complete local ZIP SHA-256 `56466f07cc5ffd326f81a8c56a74b75881fded0aa8c59bc50bc297fb333da617`

RUNTIME: Lappy Executor read-only process query found no Chiaki/ARK/Steam/DS4/Remote Play. Current scene and exact controller route unverified; zero gameplay inputs.

INTERNAL HOSTILE REVIEW — GPT-6 (OpenAI): A source writer can mutate and restore values between reads (ABA), and an explicit regression demonstrates this remains undetected. Concurrent writes can yield mixed-time snapshots. Consistent fabricated sources and receipts still pass. Same-evaluator replay is not independent correctness, authentication, controller causality, or gameplay learning. Independent exact-artifact review remains outstanding.

No merge, installation, protected mutation, or gameplay claim. This note documents a local candidate only.