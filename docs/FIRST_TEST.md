# First Windows Test

This test proves installation, local diagnostics, offline operation, real monitor capture, append-only records, DS4 byte serialization, emergency stop, and forced neutral release. It does **not** prove ARK gameplay competence or live controller integration. No virtual controller is created in v0.1.

## 1. Install

Open PowerShell in the repository:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1 -WithDev
.\.venv\Scripts\Activate.ps1
```

## 2. Run diagnostics

```powershell
vera-ark doctor
```

Confirm:

- `python_supported` is `true`;
- `windows_capture_supported` is `true`;
- `monitor_count` is at least 1;
- `controller_backend` is `dry-run-ds4-loopback-v1`;
- `ds4_report_contract` is `VERA_ARK_DS4_USB_INPUT_REPORT_V1`;
- `ds4_submission_contract` is `VERA_ARK_VHF_DS4_SUBMISSION_BATCH_V1`;
- `live_controller_available` is `false`.

## 3. Run the offline demo

```powershell
vera-ark demo --steps 2 --log-dir .vera_ark\first-demo
```

Inspect `.vera_ark\first-demo\events.jsonl` and `actions.jsonl`. The last action record must have kind `RELEASE_ALL`. Every action receipt must report:

- `loopback_verified: true`;
- `external_inputs_sent: 0`;
- transport backend `VERA_ARK_DS4_LOOPBACK_V1`.

The terminal neutral report must begin `01808080800800000000` and contain 128 hexadecimal characters total.

## 4. Capture a monitor

Close or hide sensitive windows first. Then run:

```powershell
vera-ark capture --monitor 0 --output .vera_ark\first-capture.png
```

Open the PNG and verify it is the intended display. An invalid monitor index must return a nonzero exit code and a clear error.

## 5. Run the bounded dry-run loop

Start ARK or Remote Play on monitor 0, then:

```powershell
vera-ark run --monitor 0 --planner heuristic --steps 5 --interval 1 --log-dir .vera_ark\first-run
```

Nothing should control the game. The only controller work is local semantic mapping, raw report serialization, atomic batch-envelope serialization, exact deserialization, and append-only logging.

## 6. Test emergency stop

In terminal A:

```powershell
vera-ark run --monitor 0 --planner heuristic --steps 60 --interval 1 --log-dir .vera_ark\stop-test
```

In terminal B:

```powershell
New-Item -ItemType File -Force .vera_ark\STOP
```

Terminal A should stop before the next action record, append `EMERGENCY_STOP_OBSERVED`, append `RELEASE_ALL`, verify the exact neutral report, and exit normally. Remove the stop file afterward:

```powershell
Remove-Item .vera_ark\STOP
```

## 7. Run automated checks

```powershell
python -m pytest
python -m compileall -q src tests
```

The DS4 tests verify exact offsets, masks, axis and trigger ranges, neutral bytes, unknown-version rejection, atomic batch round-trip, matched press/release, and zero external output.

## Future Remote Play compatibility gate

This plan is **not authorized for execution by v0.1**. It defines the evidence required before any live backend can be proposed:

1. Independently implement and review the `VERA_ARK_MICROSOFT_VHF_KMDF_DS4_V1` KMDF driver from the frozen interface contract.
2. Build with a pinned Windows Driver Kit and record source, compiler, INF, catalog, binary, and symbol hashes.
3. Install only on an explicitly authorized nonproduction Windows host. Verify device-interface GUID, ACL, driver signer, version, and exact binary readback.
4. Use a native HID/device inspector to confirm one enumerated DS4-compatible device and exact 64-byte report decoding.
5. Submit only a neutral batch. Confirm no buttons, centered sticks, and zero triggers.
6. Submit isolated Cross, Options, D-pad, stick-extreme, and trigger-extreme batches. Each non-neutral state must have an atomic matched neutral release.
7. Kill the user-mode feeder and close its handle during a held input. Confirm the driver forces neutral.
8. Test malformed magic, version, report size, count, offsets, report ID, reserved bytes, stale sequence, and missing neutral release. Every case must be rejected without changing device state.
9. Start Remote Play only after device-inspector tests pass. Confirm it selects the intended virtual DS4, accepts neutral state, and observes each isolated input exactly once.
10. Run the ARK semantic mapping test separately. No semantic success may waive transport failures.
11. Record loopback, device-inspector, Remote Play, stop, crash, and release evidence. Any ambiguous result blocks live activation.
12. Require a new coordinator assignment and exact writer authority before enabling or installing the backend. Passing this plan is evidence, not self-authorization.

A failure is a failure. Do not bypass a test, edit a ledger, or enable an input library to make the demo appear more alive than it is.
