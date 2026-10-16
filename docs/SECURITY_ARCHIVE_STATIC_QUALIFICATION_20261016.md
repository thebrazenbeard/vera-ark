# Archive-level static qualification (2026-10-16)

Subject: `vera-ark/main@7e4b8469c6c4d5918556e3f80a54f9335238a0c3` compared with isolated containment candidate `37a2fdeb09a634376a76f208628c2a3b3fa83f58`.

The evaluator in `tools/archive_static_gate.py` reads ZIP archives as inert bytes. It never imports repository code, invokes editor tasks, executes assets, or sends controller input.

Usage: `python tools/archive_static_gate.py <main-archive.zip> <candidate-archive.zip> <optional-result.json>`. Download archives for the two exact commits through a trusted channel; do not open affected checkouts in VS Code with automatic tasks enabled.

## Observed local test cut

Windows Lappy, 2026-10-16. Both GitHub commit-addressed archives passed ZIP CRC checks. Main failed four static checks: folder-open task declarations, automatic tasks enabled, a disguised font path present, and invalid WOFF2 signature. The candidate passed the same archive-level checks, including 16 pinned font-directory blob identities. A separate local four-case adversarial suite passed after correcting a demonstrated escaped-JSON-key blind spot in the evaluator. The local adversarial suite has **not** been published in this branch.

This is source/static evaluation, not endpoint integrity, historical execution analysis, independent security review, full font validation, or live gameplay qualification. Font pins come from the candidate source and therefore do not establish trusted origin. No game input was sent.

## Internal hostile review

> The evaluator's JSONC fallback is heuristic and may miss other encoded declarations. It does not cover every editor extension, task trigger, shell integration, or runtime path. A passing ZIP archive can still contain other malicious files. Treat the result as narrow static evidence only.

Stacked on containment candidate; no merge or installation authorized.
