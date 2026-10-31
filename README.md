> **License:** Source-visible, not open source. The original material is proprietary. Private, noncommercial evaluation is permitted under [LICENSE](LICENSE); redistribution, commercial use, hosted deployment, and commercial derivatives require written permission. See [COMMERCIAL_LICENSE.md](COMMERCIAL_LICENSE.md). Third-party material retains its own rights.

# VERA ARK — bounded perception-to-intention runtime

**A Python research toolkit for capturing or synthesizing a visual frame, producing a validated high-level action intention, and examining what a gamepad report *would* contain—without transmitting controller input.**

VERA ARK v0.1 implements a deliberately limited vertical slice for experiments involving ARK gameplay and PlayStation-style controls. Its reusable components include strict action schemas, an offline heuristic planner, an optional visual-model adapter, DS4 report serialization, a loopback-only transport, JSONL evidence logs, and an optional spatial motion guard. It is **not** an autonomous game-playing agent or a live controller.

## What works today

| Component | Implemented behavior | Boundary |
| --- | --- | --- |
| Synthetic demo | Offline image → perception → planning → action validation → DS4 serialization → local loopback verification | Runs without Windows capture, OpenAI, Supabase, or a controller |
| Monitor capture | Windows GDI capture of an explicitly selected display to PNG | Requires an interactive Windows desktop; no screen capture on Linux/macOS |
| Planning | Deterministic heuristic, or optional OpenAI vision proposal with local validation and fallback | No trained ARK survival policy; model output is untrusted |
| DS4 transport | Exact 64-byte USB report and versioned atomic report-batch envelope | **Loopback only**; no HID, keyboard, mouse, Remote Play, or gamepad output |
| State and safety | Strict schema/range/step checks, stop-file checks, validated JSONL append, forced neutral release evidence | A recorded release does not prove a physical device was released |
| Physica guard | Optional broad-phase collision-candidate veto for a dry-run `MOVE` | Requires explicit hypothetical coordinates/calibration and Physica 0.3.0+ |

The current controller backend is `VERA_ARK_DS4_LOOPBACK_V1`. A Microsoft VHF/KMDF driver interface is **specified, not implemented or installed**; the selected `VERA_ARK_MICROSOFT_VHF_KMDF_DS4_V1` contract cannot grant permission to create or operate one.

## Quick start — offline and portable

Python **3.11+** is required; the core package has no mandatory third-party runtime dependencies. In a checkout:

```sh
python -m venv .venv
python -m pip install -e .
python -m vera_ark doctor
python -m vera_ark demo --steps 2 --log-dir ./demo-output
```

Activate the virtual environment first if your Python installation requires it. The `demo` command uses a deterministic synthetic image and a local heuristic; it does not need a game, a display, a controller, or credentials.

Inspect `demo-output/events.jsonl` and `demo-output/actions.jsonl`. The result should report `release_recorded: true`; the action ledger ends in `RELEASE_ALL`, and dry-run receipts record zero external inputs. The log directory is an output artifact, not a host authorization or immutable audit store.

For Windows display capture and a bounded visual dry run:

```powershell
python -m vera_ark capture --monitor 0 --output .vera_ark/capture.png
python -m vera_ark run --monitor 0 --planner heuristic --steps 5 --interval 1
```

Monitor indexes are zero-based. A Windows capture sees the selected desktop, so close sensitive windows first. No command above can operate an actual controller. See the [Windows first-test protocol](docs/FIRST_TEST.md) for the two-terminal stop-file exercise, expected receipts, and later Remote Play qualification requirements.

## Optional adapters and explicit safety controls

- **Visual model:** `--planner openai` uses `OPENAI_API_KEY` and optional `OPENAI_MODEL`. It submits a PNG to the Responses API, accepts only a bounded schema-checked suggestion, and falls back to the offline planner on missing credentials or invalid responses. A provider label or successful API response is not host-authenticated authority.
- **Memory:** `--memory-file path.jsonl` reads text-only `{"text":"..."}` rows. Corrupt input disables that optional context; it never authorizes an action.
- **Event mirroring:** `SUPABASE_URL` and `SUPABASE_ANON_KEY` optionally enable best-effort event delivery. The [SQL migration](supabase/migrations/0001_agent_memory.sql) is only a source artifact, not an applied database or a credential/consent grant.
- **Emergency stop:** The default `.vera_ark/STOP` file is checked before each capture and again before action serialization. It does **not** cancel a capture already executing. Every exit attempts to append and loopback-verify an exact neutral `RELEASE_ALL` report.
- **Motion guard:** `--motion-guard-config model.json` is supported on both `demo` and `run`, with an explicitly supplied `VERA_ARK_PHYSICA_GUARD_CONFIG_V1` world model. Potential obstacle overlap or model failure rejects a dry-run `MOVE` *before* controller serialization; other intentions are not motion-guarded. See the [Physica guard contract and synthetic JSON example](docs/PHYSICA_DRY_RUN_MOTION_GUARD.md). A clear broad-phase result does not establish collision-free motion, calibrated game coordinates, or physical safety.

All action intentions are `dry_run=true`, finite, range bounded, and duration bounded; unknown actions and report versions fail closed. A non-neutral report batch must conclude with an exact neutral report. These are source-checked serialization invariants, **not** a live input-suppression security boundary against a malicious or privileged host.

## DS4 specification and future integration

The source exposes two frozen version labels:

- `VERA_ARK_DS4_USB_INPUT_REPORT_V1`: a 64-byte report with report ID `0x01`, neutral stick axes at 128, and defined button/trigger offsets.
- `VERA_ARK_VHF_DS4_SUBMISSION_BATCH_V1`: a little-endian `VAD4` batch header with count, version and bounded report offsets. Any batch with non-neutral output must include a matched neutral report.

The byte-level implementation and validation are in [controller.py](src/vera_ark/controller.py) and [controller tests](tests/test_models.py). The future Windows driver selection and the **separate authorization, signing, device-inspection, and Remote Play tests that would be required** are described in [FIRST_TEST.md](docs/FIRST_TEST.md). No live driver source or approved controller-output path exists in v0.1.

## Verification

```sh
python -m pip install -e ".[dev]"
python -m pytest -q
python -m compileall -q src tests
```

The optional Physica guard tests also require Physica 0.3.0+ installed in the test environment. The base runtime and demo work without it. [TEST_REPORT.md](TEST_REPORT.md) records historical test environments and limits; those records are not proof of current Windows capture, live game behavior, host-installed drivers, or continuous qualification.

At the audited public `main` revision, an isolated Python 3.12 run passed **19 base tests** without Physica and **25 full tests** after adding the current Physica source. An offline one-step demo completed and recorded neutral release. No physical Windows monitor, HID device, ARK session, or Remote Play host was exercised by this audit.

## Rights and trust boundaries

This is a source-visible proprietary research product, not freely redistributable open-source software. Read [LICENSE](LICENSE), [COMMERCIAL_LICENSE.md](COMMERCIAL_LICENSE.md), and [NOTICE](NOTICE) before reuse; contributions follow [CONTRIBUTING.md](CONTRIBUTING.md) and [CLA.md](CLA.md).

An action proposal, valid schema, source test, report byte sequence, or simulated stop receipt is **not** consent, an authenticated provider identity, a host-owned immutable authority binding, or authorization for an external effect. Any future live controller or hosted integration must supply and verify those guarantees outside this package.
