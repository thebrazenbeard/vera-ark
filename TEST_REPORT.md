# VERA ARK v0.1 Test Report

## Current-main verification — 2026-09-27

Current canonical main before this report update: `e5ee4a781b52cf0788b19c13d4b067fa33ebb15a`.

A fresh authenticated Lappy Desktop Commander checkout of source head `5dc7eba3fa00172c63d12355023b363e57553930` was verified on Windows / CPython 3.12.10. Git-tree readback confirmed that current main and that tested head are byte-identical across the 14 checked `src/`, `tests/`, `pyproject.toml`, and `setup.ps1` files.

Observed Lappy results:
- editable package build/install: PASS;
- `py -m pytest -q`: PASS, 19/19;
- `py -m compileall -q src tests`: PASS;
- `py -m vera_ark demo --steps 2 --log-dir .vera_ark\\ci-demo`: PASS, two completed steps with terminal release recorded.

The red private-repository GitHub Actions jobs are infrastructure evidence, not source-test failures. GitHub check-run annotations state: `The job was not started because recent account payments have failed or your spending limit needs to be increased.` The failed jobs contain zero executed workflow steps. Do not relabel that billing/spending gate as a code regression or CI PASS.


## Scope

Local verification covers the dry-run vertical slice and the corrected DS4 transport contract: strict data models, deterministic offline perception and planning, semantic-to-DS4 mapping, exact 64-byte report serialization, button masks and byte offsets, axis and trigger ranges, exact neutral state, atomic batch framing, matched press/release, loopback verification, controller non-output, stop handling, forced release, optional-memory failure, missing-OpenAI fallback, CLI capture failure, append-only logs, package build/install, compilation, and offline demo.

## Verified local results

Verification environment: Linux x86-64, CPython 3.13.5. This environment can validate the cross-platform runtime, serializer, loopback transport, package, and Windows capture failure path. It cannot execute the Windows GDI success path, build/install a KMDF driver, inspect a virtual HID device, or test Remote Play.

| Check | Result |
|---|---|
| `python -m pytest` | PASS, 19 passed |
| `python -m compileall -f -q src tests` | PASS |
| `PYTHONPATH=src python -m vera_ark doctor` | PASS; live controller unavailable |
| `PYTHONPATH=src python -m vera_ark demo --steps 2 ...` | PASS; 2 steps and forced release |
| Wheel build and isolated-target install | PASS; `vera_ark-0.1.0-py3-none-any.whl` built and installed |
| Installed-package offline demo | PASS |
| DS4 neutral report | PASS; 64 bytes, report ID `0x01`, sticks `128`, D-pad `8`, triggers `0` |
| DS4 masks and offsets | PASS against assignment sequence 1373 |
| DS4 atomic submission batch | PASS; exact serialize/deserialize loopback |
| Press/release invariant | PASS; non-neutral batch without final neutral is rejected |
| Unknown report or batch version | PASS; rejected closed |
| Action ledger terminal record | PASS; final kind `RELEASE_ALL` |
| External inputs sent | PASS; always 0 |

## Reproducible commands

```text
python -m pytest
python -m compileall -f -q src tests
PYTHONPATH=src python -m vera_ark doctor
PYTHONPATH=src python -m vera_ark demo --steps 2 --log-dir <temporary-directory>
python -m pip install --no-build-isolation --no-deps --target <target-directory> .
PYTHONPATH=<target-directory> python -m vera_ark demo --steps 1 --log-dir <temporary-directory>
```

The GitHub workflow independently installs and tests Python 3.11 on `windows-latest` and `ubuntu-latest`. No same-head workflow result existed at local handoff time.

## Transport decision

- Selected future backend: `VERA_ARK_MICROSOFT_VHF_KMDF_DS4_V1`, version 1.
- Windows framework: Microsoft Virtual HID Framework (VHF), KMDF source driver.
- Driver API: device interface `{8F78C4F8-1D21-4C5C-BBAA-2D907D98C721}`, IOCTL `0x0022A004`, METHOD_BUFFERED, FILE_WRITE_DATA.
- User-to-driver payload: `VERA_ARK_VHF_DS4_SUBMISSION_BATCH_V1`.
- HID payload: `VERA_ARK_DS4_USB_INPUT_REPORT_V1`.
- Current executable backend: `VERA_ARK_DS4_LOOPBACK_V1` only.
- Live output: not implemented, installed, or authorized.

The choice avoids adopting retired ViGEm as new infrastructure. VHF is selected as the supported Windows framework, but a custom signed kernel driver and separate authority are still required.

## Acceptance invariants observed

- Invalid ranges, non-finite values, unknown fields, and `dry_run=false` fail closed.
- The heuristic planner produces a valid bounded intention.
- Semantic actions map separately into DS4 transport states.
- Named controls serialize to the exact assigned masks and offsets.
- Any non-neutral batch must end with the exact neutral report.
- Batch magic, version, report size, count, offsets, report ID, reserved bytes, and length are strict.
- The controller sends no keyboard, mouse, gamepad, Remote Play, VHF, or other external input.
- A preexisting stop file halts before capture and still records forced neutral release.
- Runtime exit records and verifies `RELEASE_ALL`.
- Corrupted optional memory is ignored and cannot provide an action.
- A missing OpenAI key falls back to the local heuristic.
- Capture errors return a nonzero code with a clear message.
- No OpenAI key or Supabase service is required.

## Known limitations and unresolved risks

- Actual Windows monitor capture was not executable in the Linux verification environment; native Windows CI and first-machine testing remain required.
- The selected VHF driver is a frozen interface decision only. No driver source, binary, signature, installation, device enumeration, or live transport exists in this milestone.
- Loopback proves serializer and envelope consistency, not Windows HID enumeration or Remote Play compatibility.
- Real monitor capture uses Windows GDI and requires an interactive desktop.
- The offline perception engine does not identify ARK objects, hazards, inventory, or UI state.
- The heuristic planner is deterministic scaffolding, not a trained survivor policy.
- The OpenAI adapter is optional and network-dependent; availability and model behavior are not guaranteed.
- Supabase mirroring is best-effort and disabled unless explicitly configured. The migration was not deployed.
- There is no live keyboard, mouse, gamepad, Remote Play, or ARK controller backend.
- The stop file preempts the next action boundary; it cannot cancel a Windows capture call already in progress.
## 2026-09-25 Lappy exact-main verification

After current-main integration, the exact source subject was reconstructed on the connected Lappy Desktop Commander execution host and verified with CPython 3.12.10:

- editable install: PASS;
- `py -m pytest -q`: **19/19 PASS**;
- `py -m compileall -q src tests`: PASS;
- `py -m vera_ark demo --steps 2 --log-dir .vera_ark\\local-verify`: PASS;
- completed steps: 2;
- forced release recorded: true;
- no live controller backend was introduced or exercised.

The repository's private GitHub Actions jobs were observed failing before any workflow step executed; that result is not treated as source-test evidence either way. Local Lappy verification is the execution evidence for this integration cut.
