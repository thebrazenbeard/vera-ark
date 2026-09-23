from __future__ import annotations

import json
from pathlib import Path

import pytest

from vera_ark import cli
from vera_ark.capture import CaptureError, SyntheticCapture
from vera_ark.controller import ControllerError, DryRunController
from vera_ark.models import ActionIntention, ActionType, new_id, utc_now
from vera_ark.planner import HeuristicPlanner, OfflinePerceptionEngine
from vera_ark.runtime import RuntimeConfig, VeraArkRuntime
from vera_ark.storage import JsonlMemoryAdapter, OperationalStorage


def make_runtime(tmp_path: Path, *, stop_file: Path | None = None, memory=None, steps: int = 2):
    storage = OperationalStorage.create(tmp_path / "logs")
    controller = DryRunController(storage)
    runtime = VeraArkRuntime(
        config=RuntimeConfig(
            monitor_index=0,
            steps=steps,
            interval_seconds=0,
            stop_file=stop_file or (tmp_path / "STOP"),
        ),
        capture=SyntheticCapture(),
        perception=OfflinePerceptionEngine(),
        planner=HeuristicPlanner(),
        controller=controller,
        storage=storage,
        memory=memory,
        sleeper=lambda _seconds: None,
    )
    return runtime, storage, controller


def kinds(path: Path) -> list[str]:
    return [json.loads(line)["kind"] for line in path.read_text(encoding="utf-8").splitlines()]


def test_dry_run_controller_never_sends_external_input(tmp_path: Path) -> None:
    storage = OperationalStorage.create(tmp_path / "logs")
    controller = DryRunController(storage)
    action = ActionIntention(
        schema_version=ActionIntention.SCHEMA_VERSION,
        intention_id=new_id(), perception_id=new_id(), session_id=new_id(), step=0,
        action_type=ActionType.LOOK, x=0.1, y=0.1, duration_ms=100,
        reason="test", planner="test", created_at=utc_now(), dry_run=True,
    )
    receipt = controller.execute(action)
    assert receipt.external_inputs_sent == 0
    assert controller.external_inputs_sent == 0


def test_stop_file_halts_loop_before_capture_and_records_release(tmp_path: Path) -> None:
    stop_file = tmp_path / "STOP"
    stop_file.write_text("stop", encoding="utf-8")
    runtime, storage, controller = make_runtime(tmp_path, stop_file=stop_file)
    result = runtime.run()
    assert result.stopped is True
    assert result.completed_steps == 0
    assert controller.external_inputs_sent == 0
    assert "RELEASE_ALL" in kinds(storage.action_ledger.path)


def test_runtime_exit_records_release_all(tmp_path: Path) -> None:
    runtime, storage, controller = make_runtime(tmp_path, steps=2)
    result = runtime.run()
    assert result.completed_steps == 2
    assert result.release_recorded is True
    assert kinds(storage.action_ledger.path)[-1] == "RELEASE_ALL"
    assert controller.external_inputs_sent == 0


def test_corrupted_optional_memory_does_not_enable_action(tmp_path: Path) -> None:
    memory_file = tmp_path / "memory.jsonl"
    memory_file.write_text('{"text":"safe"}\n{broken}\n', encoding="utf-8")
    memory = JsonlMemoryAdapter(memory_file)
    runtime, storage, controller = make_runtime(tmp_path, memory=memory, steps=1)
    result = runtime.run()
    assert result.completed_steps == 1
    assert memory.last_error is not None
    assert "OPTIONAL_MEMORY_IGNORED" in kinds(storage.event_ledger.path)
    assert controller.external_inputs_sent == 0


def test_duplicate_and_stale_commands_fail_closed(tmp_path: Path) -> None:
    storage = OperationalStorage.create(tmp_path / "logs")
    controller = DryRunController(storage)
    session = new_id()
    first = ActionIntention(
        schema_version=ActionIntention.SCHEMA_VERSION,
        intention_id=new_id(), perception_id=new_id(), session_id=session, step=1,
        action_type=ActionType.LOOK, x=0.1, y=0.0, duration_ms=100,
        reason="first", planner="test", created_at=utc_now(), dry_run=True,
    )
    controller.execute(first)
    with pytest.raises(ControllerError):
        controller.execute(first)
    stale = ActionIntention(
        schema_version=ActionIntention.SCHEMA_VERSION,
        intention_id=new_id(), perception_id=new_id(), session_id=session, step=0,
        action_type=ActionType.NOOP, x=0.0, y=0.0, duration_ms=0,
        reason="stale", planner="test", created_at=utc_now(), dry_run=True,
    )
    with pytest.raises(ControllerError):
        controller.execute(stale)


def test_capture_error_returns_nonzero_with_clear_message(monkeypatch, tmp_path: Path, capsys) -> None:
    class BrokenCapture:
        def __init__(self) -> None:
            pass
        def capture(self, monitor_index: int):
            raise CaptureError(f"monitor {monitor_index} unavailable")

    monkeypatch.setattr(cli, "WindowsMonitorCapture", BrokenCapture)
    code = cli.main(["capture", "--monitor", "9", "--output", str(tmp_path / "frame.png")])
    captured = capsys.readouterr()
    assert code != 0
    assert "capture failed" in captured.err
    assert "monitor 9 unavailable" in captured.err


def test_offline_demo_produces_event_and_action_ledgers(tmp_path: Path) -> None:
    log_dir = tmp_path / "demo"
    code = cli.main(["demo", "--steps", "1", "--log-dir", str(log_dir)])
    assert code == 0
    assert (log_dir / "events.jsonl").exists()
    assert (log_dir / "actions.jsonl").exists()


def test_ds4_neutral_report_exact_offsets_and_size() -> None:
    from vera_ark.controller import DS4USBReportV1

    report = DS4USBReportV1.neutral_report()
    assert len(report) == 64
    assert report[:10] == bytes([0x01, 128, 128, 128, 128, 0x08, 0, 0, 0, 0])
    assert report[10:] == bytes(54)
    assert DS4USBReportV1.verify_round_trip(report).to_dict()["dpad"] == "NEUTRAL"


def test_ds4_button_masks_match_coordinator_contract() -> None:
    from vera_ark.controller import DS4Button, DS4State, DS4USBReportV1, button_mask_table

    table = button_mask_table()
    assert table["square"] == {"offset": 5, "mask": 0x10}
    assert table["cross"] == {"offset": 5, "mask": 0x20}
    assert table["circle"] == {"offset": 5, "mask": 0x40}
    assert table["triangle"] == {"offset": 5, "mask": 0x80}
    assert table["l1"] == {"offset": 6, "mask": 0x01}
    assert table["r1"] == {"offset": 6, "mask": 0x02}
    assert table["share"] == {"offset": 6, "mask": 0x10}
    assert table["options"] == {"offset": 6, "mask": 0x20}
    assert table["l3"] == {"offset": 6, "mask": 0x40}
    assert table["r3"] == {"offset": 6, "mask": 0x80}
    assert table["ps"] == {"offset": 7, "mask": 0x01}
    assert table["touchpad_click"] == {"offset": 7, "mask": 0x02}
    report = DS4USBReportV1.serialize(
        DS4State(buttons=frozenset({DS4Button.CROSS, DS4Button.OPTIONS, DS4Button.PS}))
    )
    assert report[5] == 0x28
    assert report[6] == 0x20
    assert report[7] == 0x01


def test_ds4_axis_trigger_ranges_and_unknown_report_fail_closed() -> None:
    from vera_ark.controller import (
        ControllerError,
        DS4State,
        DS4USBReportV1,
        normalized_axis_to_u8,
    )

    assert normalized_axis_to_u8(-1.0) == 0
    assert normalized_axis_to_u8(0.0) == 128
    assert normalized_axis_to_u8(1.0) == 255
    state = DS4State(left_x=0, left_y=255, right_x=255, right_y=0, left_trigger=0, right_trigger=255)
    report = DS4USBReportV1.serialize(state)
    assert report[1:5] == bytes([0, 255, 255, 0])
    assert report[8:10] == bytes([0, 255])
    with pytest.raises(ControllerError):
        DS4USBReportV1.deserialize(bytes([0x02]) + bytes(63))
    with pytest.raises(ControllerError):
        DS4USBReportV1.deserialize(bytes(63))


def test_interact_serializes_press_then_matched_neutral_release(tmp_path: Path) -> None:
    from vera_ark.controller import DS4USBReportV1

    storage = OperationalStorage.create(tmp_path / "logs")
    controller = DryRunController(storage)
    action = ActionIntention(
        schema_version=ActionIntention.SCHEMA_VERSION,
        intention_id=new_id(), perception_id=new_id(), session_id=new_id(), step=0,
        action_type=ActionType.INTERACT, x=0.0, y=0.0, duration_ms=75,
        reason="interact", planner="test", created_at=utc_now(), dry_run=True,
    )
    receipt = controller.execute(action)
    assert receipt.reports_serialized == 2
    active, release = controller.transport.receipts[-2:]
    assert bytes.fromhex(active.report_hex)[5] == 0x28
    assert active.offset_ms == 0
    assert release.report_hex == DS4USBReportV1.neutral_report().hex()
    assert release.offset_ms == 75
    assert active.external_inputs_sent == release.external_inputs_sent == 0


def test_release_all_is_verified_exact_neutral_report(tmp_path: Path) -> None:
    from vera_ark.controller import DS4USBReportV1

    storage = OperationalStorage.create(tmp_path / "logs")
    controller = DryRunController(storage)
    receipt = controller.release_all(new_id(), 0, "test")
    assert receipt.disposition == "VERIFIED_NEUTRAL_DS4_REPORT_NO_EXTERNAL_INPUT"
    assert controller.transport.receipts[-1].report_hex == DS4USBReportV1.neutral_report().hex()
    assert controller.external_inputs_sent == 0


def test_vhf_submission_batch_exact_round_trip_and_matched_release() -> None:
    from vera_ark.controller import (
        ControllerError,
        DS4Button,
        DS4State,
        DS4USBReportV1,
        VHFDS4SubmissionBatchV1,
    )

    active = DS4USBReportV1.serialize(
        DS4State(buttons=frozenset({DS4Button.CROSS}))
    )
    neutral = DS4USBReportV1.neutral_report()
    frame = VHFDS4SubmissionBatchV1.serialize(7, ((active, 0), (neutral, 75)))
    sequence, reports = VHFDS4SubmissionBatchV1.deserialize(frame)
    assert sequence == 7
    assert reports == ((active, 0), (neutral, 75))
    assert len(frame) == 16 + (68 * 2)
    with pytest.raises(ControllerError):
        VHFDS4SubmissionBatchV1.serialize(8, ((active, 0),))
    corrupt = bytearray(frame)
    corrupt[4:6] = (2).to_bytes(2, "little")
    with pytest.raises(ControllerError):
        VHFDS4SubmissionBatchV1.deserialize(bytes(corrupt))


def test_non_loopback_transport_is_rejected(tmp_path: Path) -> None:
    class FakeLiveTransport:
        external_inputs_sent = 0

    storage = OperationalStorage.create(tmp_path / "logs")
    with pytest.raises(ControllerError):
        DryRunController(storage, transport=FakeLiveTransport())  # type: ignore[arg-type]
