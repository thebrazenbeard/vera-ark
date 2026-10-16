# Suspicious VS Code auto-run task and non-font asset — quarantine

Scope: isolated security candidate based on `vera-ark/main@7e4b8469c6c4d5918556e3f80a54f9335238a0c3`. This is **not** an assertion that any workstation executed the payload.

## Repository-source evidence

- `.vscode/tasks.json` declared a hidden `runOn: folderOpen` shell task which invoked Node on `public/fonts/fa-solid-500.woff2`.
- `.vscode/settings.json` explicitly allowed automatic tasks.
- `fa-solid-500.woff2` was 28,066 bytes and did **not** begin with the WOFF2 `wOF2` signature; static inspection found obfuscated JavaScript with network calls, `eval`, and detached process creation.
- The three other `.woff2` files had the expected `wOF2` signature.
- These facts establish a dangerous source-level auto-execution path, **not** observed execution, exfiltration, or host compromise.

## Proposed containment

Remove the executable-disguised asset and its auto-run task; explicitly disable VS Code automatic tasks; add byte-signature and auto-task regression tests. No executable payload is reproduced in this document.

## Claim ceiling / follow-up

This branch is draft-only and not deployed. Existing clones, editor trust decisions, historical copies, and any earlier execution remain outside this source patch. A separate endpoint investigation and independent review are required before declaring the environment clean. Do not open affected clones in VS Code or enable automatic tasks before containment.
