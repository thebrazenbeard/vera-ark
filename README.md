> **License:** Source-visible, not open source. Original material is proprietary. Commercial use, redistribution, hosted-service use, and commercial derivative products require written permission. See [LICENSE](LICENSE) and [COMMERCIAL_LICENSE.md](COMMERCIAL_LICENSE.md). Separately identified third-party components retain their own licenses.

# VERA ARK Player v0.1

A Windows-first, local, safety-bounded runtime scaffold for an independent ARK survivor. Version 0.1 captures a monitor, creates structured perception records, produces one bounded high-level action intention, maps it into an exact DualShock 4 USB input-report contract, and verifies the serialized bytes through a **loopback-only transport**. It does not send keyboard, mouse, gamepad, Remote Play, virtual-HID, or network controller input.

## Safety boundary

- There is no live controller backend in this release.
- Every action intention is schema-validated, finite, range-bounded to `[-1, 1]`, duration-bounded to 1000 ms, and marked `dry_run=true`.
- Unknown fields, unknown actions, stale steps, duplicate intentions, non-finite numbers, report-version drift, and live-output requests fail closed.
- Every non-neutral DS4 report batch ends with a matched neutral release report.
- A stop file is checked before capture and again before action serialization.
- Every runtime exit records and loopback-verifies the exact neutral `RELEASE_ALL` report.
- OpenAI, Supabase, and optional memory are adapters. Their absence or failure cannot enable controller output.

## Requirements

- Windows 10 or 11 for real monitor capture
- 64-bit Python 3.11
- No mandatory third-party runtime packages

## Install on Windows

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1 -WithDev
.\.venv\Scripts\Activate.ps1
```

`setup.ps1` is idempotent for an existing `.venv`. Do not put secrets in the repository. Copy `.env.example` to a local `.env` only if you have your own environment loader; this package reads process environment variables directly.

## Required commands

```powershell
vera-ark doctor
vera-ark demo
vera-ark capture --monitor 0 --output .vera_ark\capture.png
vera-ark run --monitor 0 --planner heuristic --steps 5 --interval 1
```

Monitor indexes are zero-based. `doctor` reports the monitor count, active loopback contract, and the selected but unavailable future Windows backend.

## Emergency stop

The default stop file is `.vera_ark\STOP`. Create it from another terminal:

```powershell
New-Item -ItemType File -Force .vera_ark\STOP
```

Remove it before a later run:

```powershell
Remove-Item .vera_ark\STOP
```

The runtime checks the file before every capture and immediately before every dry-run action serialization. It cannot interrupt a capture already inside the Windows GDI call, because operating systems still insist that time is linear.

## Exact DS4 transport contract

The semantic action layer remains separate from the controller transport layer:

- `MOVE` maps to the left stick.
- `LOOK` maps to the right stick.
- `INTERACT` maps to Cross, followed by neutral release.
- `NOOP` and `RELEASE_ALL` map to the exact neutral report.

The report contract is `VERA_ARK_DS4_USB_INPUT_REPORT_V1`:

| Zero-based byte offset | Field | Range / meaning |
|---:|---|---|
| 0 | USB report ID | `0x01` |
| 1 | left X | `0..255`, neutral `128` |
| 2 | left Y | `0..255`, neutral `128` |
| 3 | right X | `0..255`, neutral `128` |
| 4 | right Y | `0..255`, neutral `128` |
| 5 | buttons0 | D-pad `0x0F`; Square `0x10`; Cross `0x20`; Circle `0x40`; Triangle `0x80` |
| 6 | buttons1 | L1 `0x01`; R1 `0x02`; L2 digital `0x04`; R2 digital `0x08`; Share `0x10`; Options `0x20`; L3 `0x40`; R3 `0x80` |
| 7 | buttons2 | PS `0x01`; touchpad click `0x02` |
| 8 | left trigger analog | `0..255` |
| 9 | right trigger analog | `0..255` |
| 10..63 | v0.1 unsupported fields | must be zero |

The neutral report is exactly 64 bytes:

```text
01 80 80 80 80 08 00 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
```

### Atomic submission envelope

The future driver-facing batch is `VERA_ARK_VHF_DS4_SUBMISSION_BATCH_V1`:

```text
little-endian header: <4sHHII
magic="VAD4"
version=1
report_size=64
sequence=uint32
report_count=1..8

repeated entry: <I64s
offset_ms=uint32, bounded 0..1000
report=64-byte VERA_ARK_DS4_USB_INPUT_REPORT_V1
```

Offsets must begin at zero and be nondecreasing. Any batch containing a non-neutral report must end in the exact neutral report. The whole batch is one future driver request, preventing a button press from being accepted without its scheduled release.

## Selected future Windows backend

The selected transport is `VERA_ARK_MICROSOFT_VHF_KMDF_DS4_V1`, version 1:

- Microsoft Virtual HID Framework (VHF), KMDF kernel-mode HID source driver
- device interface GUID `{8F78C4F8-1D21-4C5C-BBAA-2D907D98C721}`
- submit IOCTL `0x0022A004`
- definition `CTL_CODE(FILE_DEVICE_UNKNOWN, 0x801, METHOD_BUFFERED, FILE_WRITE_DATA)`
- driver validates the batch, queues reports, calls `VhfReadReportSubmit`, and forces neutral on handle close

This is a selected interface contract, **not an implemented, installed, signed, or authorized driver**. ViGEm is deliberately not selected because its upstream project is retired and archived. VHF is the supported Windows framework for a custom virtual HID source, but it requires a separately authorized kernel driver, installation, signing, native device inspection, and Remote Play compatibility review.

## Offline operation

`vera-ark demo` uses a deterministic synthetic image and works without Windows capture, OpenAI, or Supabase. `--planner openai` is optional. With no `OPENAI_API_KEY`, or when the request or response fails validation, planning falls back to the local heuristic and logs `PLANNER_FALLBACK`.

The optional OpenAI planner submits a PNG as an image input to the Responses API, parses one JSON action proposal, reconstructs internal identifiers locally, and subjects the result to the same strict action schema. It never talks to the controller directly.

## Logs

Each run creates two append-only JSONL ledgers:

- `events.jsonl`: session, capture, perception, planner, stop, error, and release events
- `actions.jsonl`: semantic intentions, raw DS4 report bytes, atomic submission-envelope bytes, loopback receipts, and `RELEASE_ALL`

Existing ledgers are strictly validated before append. A malformed or sequence-broken ledger blocks the session rather than pretending history is fine.

## Optional adapters

- `--memory-file path.jsonl` accepts text-only rows shaped exactly as `{"text":"..."}`. Any corrupted row disables all memory context for that read.
- `SUPABASE_URL` and `SUPABASE_ANON_KEY` enable best-effort event mirroring to `vera_ark_operational_events`. The included migration is a design artifact only and is not applied by the runtime.
- `OPENAI_API_KEY` and optional `OPENAI_MODEL` enable the vision planner. No secret value is logged.

## Development checks

```powershell
python -m pytest
python -m compileall -q src tests
vera-ark demo --steps 2 --log-dir .vera_ark\verification-demo
```

See [docs/FIRST_TEST.md](docs/FIRST_TEST.md) for the first Windows test and the gated Remote Play compatibility plan. See [TEST_REPORT.md](TEST_REPORT.md) for verified results and limitations.
