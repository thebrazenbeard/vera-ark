# ARK PNG offline evidence hardening — resumed 2026-10-15

Base: `research/ark-png-color-metadata-policy-20261015@63037ab7b359b8a458118fd2602f066cf41a3041`.
This is a **new source implementation**, not a byte-for-byte recovery of the prior unpublished candidate ZIP.

## Source boundary

`src/vera_ark/visual_trial_png_evidence.py` composes the existing exact-frame SHA-256 binding with bounded PNG parsing and 8-bit noninterlaced sample normalization. It checks chunk CRC/order, zlib completion, row filters, RGB/RGBA/grayscale samples, color-profile metadata, ICC header/compression bounds, and alternate encodings. Unsupported formats and alpha-key transparency fail closed.

It rejects equal decoded samples crossing development/holdout even where encoded files differ, and warns when identical decoded samples have differing selected presentation metadata. Raw presentation disagreement is not a color-managed rendering verdict.

## Local qualification

Windows Lappy, Python 3.12.10; Physica dependency from isolated checkout `thebrazenbeard/physica@9cc1ae9c04f728c10d6bdd9f3b277083eb46a834` exposed only via `PYTHONPATH`.
Observed red: first public audit test raised `NotImplementedError`; later tRNS adversarial test detected a missing fail-closed check.
Focused PNG suite: **45 passed**. Complete ARK suite: **70 passed**. `compileall` and `git diff --check`: passed on this worktree. Collected with Python 3.12.10.

Read-only offline compatibility probe: four existing local private Chiaki PNG files decoded, four distinct decoded sample groups, zero raw presentation-metadata disagreement groups in that sample. No private PNGs or screen content are committed.

## Claim boundary

This does not authenticate capture source or reference labels, prove replay causality, establish display-color equivalence, establish controller/input release in live gameplay, or constitute independent review. No controller input, game-state mutation, deployment, merge, or training effect was performed.

> HOSTILE CHALLENGE: PNG byte integrity is not chain-of-custody. A caller can fabricate valid images and labels, and unmodeled renderer/EXIF behavior may affect presentation.
>
> RESPONSE: The report explicitly records authentication, color equivalence, controller causality, and independent-review fields as false. Only offline caller-supplied evidence may be claimed.
