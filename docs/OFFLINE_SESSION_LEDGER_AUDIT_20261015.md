# Offline dry-run session ledger audit — 2026-10-15

Subject: one declared `vera-ark` v0.1 session, from caller-supplied parsed `events.jsonl` and `actions.jsonl` records. No filesystem, device, Remote Play, or controller route access in the evaluator.

Base: `vera-ark/main@7e4b8469c6c4d5918556e3f80a54f9335238a0c3`. Vera Mono source contract: `main@16a2828dfa7fb7e6c0e19004f014bc68fc47badf`.

New `src/vera_ark/offline_session_audit.py` checks:
- contiguous record sequences and single-session start/end/release envelope;
- frame/perception/plan/action ordering, session/step/perception/hash references;
- executed action counts and stop-before-capture/action declarations;
- exact serialized DS4 report and atomic VHF batch bytes, digests, offsets, decoded state;
- loopback-only transport receipts, zero declared external inputs, exact terminal neutral release;
- conservative claim ceiling: **caller-supplied offline ledger self-consistency only**.

Verification: Windows Lappy Python 3.14, `PYTHONPATH=src python -m pytest -q tests` returned **50 passed** (25 existing + 25 new); `compileall` passed. Six new chronology/capture-chain adversarial tests reproduced false acceptance before correction and passed after. The suite uses synthetic `vera-ark demo` records, not authenticated game captures.

> INTERNAL HOSTILE REVIEW — GPT-6 (OpenAI): A malicious caller can fabricate two mutually consistent ledgers and every serialized receipt. There is no signature, trusted capture attestation, external controller observation, real-time timing guarantee, or independent review. The auditor checks declarations and bytes, not actual physical release or gameplay learning. Clock timestamps and log-file chain of custody remain unverified.

No Chiaki/RemotePlay/DS4 process was observed during the read-only Lappy check. No game inputs were sent. PRs #12, #13, #14, and #21 remain untouched. No protected effects or main mutation.
