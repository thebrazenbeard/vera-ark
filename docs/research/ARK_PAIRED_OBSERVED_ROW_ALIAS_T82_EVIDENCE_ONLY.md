# T82 observed-row alias audit — evidence-only marker

Date: 2026-10-19. Scope: offline source-level ARK paired comparison evaluation.

Fresh source: vera-ark main 7e4b8469c6c4d5918556e3f80a54f9335238a0c3; vera-mono main 16a2828dfa7fb7e6c0e19004f014bc68fc47badf. Reviewed open Draft PRs #12, #13, #14, #21, #22 and their changed-file scopes.

Finding: the unpublished T81 paired evaluator accepts the same mutable Mapping object as an observed baseline and candidate row. T82's local candidate rejects shared observed-row identities before scoring, but allows shared missing placeholders and independent equal-content dictionaries. The same check is applied to paired comparison, uncertainty, and missingness diagnostics.

Local verification: original red test failed; after repair, 7 new tests and 509 cumulative synthetic unittest tests passed, plus optimized focused tests, compilation, archive integrity, and extracted-archive retest. Local full-candidate SHA-256: b87430ab5c6c57085dcb56daf5056c3a35c8cbc9e215a2cc521d8b405203e391.

IMPORTANT: This research branch was created from T74 commit 344387989d36032311668000c1af0173f3ac71e5. The T75–T82 implementation and tests are NOT published by this marker. Do not claim this branch contains the tested fix or use it for a merge. The local ZIP and patch are separate. No GitHub CI or independent review claimed.

Lappy connected; no matching Chiaki/ARK/Steam/DS4/Remote Play process. No live route verified; zero gameplay inputs. No main merge, installation, protected mutation, or autonomous gameplay.

Internal hostile review — GPT-6/OpenAI: object identity isolation does not authenticate data or prevent forged independent dictionaries or concurrent mutation. Gameplay learning and independent review remain unverified.
