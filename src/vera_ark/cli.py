from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys
from typing import Sequence

from . import __version__
from .capture import CaptureError, SyntheticCapture, WindowsMonitorCapture
from .controller import (
    DS4_BATCH_CONTRACT,
    DS4_REPORT_CONTRACT,
    DS4_SELECTED_WINDOWS_BACKEND,
    DryRunController,
)
from .planner import OfflinePerceptionEngine, make_planner
from .runtime import RuntimeConfig, VeraArkRuntime
from .storage import JsonlMemoryAdapter, OperationalStorage, SupabaseEventAdapter


def _timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _json_print(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, allow_nan=False))


def _storage(path: Path) -> OperationalStorage:
    adapter = SupabaseEventAdapter.from_environment()
    return OperationalStorage.create(path, adapter=adapter)


def doctor_command(_args: argparse.Namespace) -> int:
    python_ok = sys.version_info >= (3, 11)
    capture_supported = sys.platform == "win32"
    monitor_count: int | None = None
    capture_error: str | None = None
    if capture_supported:
        try:
            monitor_count = len(WindowsMonitorCapture().monitors())
        except CaptureError as exc:
            capture_error = str(exc)
    result = {
        "schema_version": "VERA_ARK_DOCTOR_V1",
        "version": __version__,
        "python": platform.python_version(),
        "python_supported": python_ok,
        "platform": platform.platform(),
        "windows_capture_supported": capture_supported,
        "monitor_count": monitor_count,
        "capture_error": capture_error,
        "openai_key_present": bool(os.getenv("OPENAI_API_KEY")),
        "supabase_adapter_configured": bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_ANON_KEY")),
        "controller_backend": "dry-run-ds4-loopback-v1",
        "ds4_report_contract": DS4_REPORT_CONTRACT,
        "ds4_submission_contract": DS4_BATCH_CONTRACT,
        "selected_future_windows_backend": DS4_SELECTED_WINDOWS_BACKEND,
        "live_controller_available": False,
    }
    _json_print(result)
    return 0 if python_ok else 2


def _run_runtime(
    *,
    capture: object,
    planner_name: str,
    monitor: int,
    steps: int,
    interval: float,
    log_dir: Path,
    stop_file: Path,
    memory_file: Path | None,
    motion_guard_file: Path | None = None,
) -> int:
    motion_guard = None
    if motion_guard_file is not None:
        from .physica_guard import PhysicaMotionGuard
        from physica.ark_bridge import MotionCalibration
        from physica.spatial import AABB
        payload = json.loads(motion_guard_file.read_text(encoding="utf-8"))
        fields = {"schema", "position_m", "x_axis", "y_axis", "radius_m", "obstacles"}
        if type(payload) is not dict or set(payload) != fields or payload["schema"] != "VERA_ARK_PHYSICA_GUARD_CONFIG_V1":
            raise ValueError("motion guard config must match exact V1 schema")
        if type(payload["obstacles"]) is not list or len(payload["obstacles"]) > 256:
            raise ValueError("motion guard obstacles must be a list of at most 256")
        boxes = []
        for item in payload["obstacles"]:
            if type(item) is not dict or set(item) != {"id", "lower", "upper"}:
                raise ValueError("invalid obstacle shape")
            boxes.append(AABB(item["id"], tuple(item["lower"]), tuple(item["upper"])))
        motion_guard = PhysicaMotionGuard(
            position_m=tuple(payload["position_m"]),
            calibration=MotionCalibration(tuple(payload["x_axis"]), tuple(payload["y_axis"])),
            radius_m=payload["radius_m"], obstacles=boxes,
        )
    storage = _storage(log_dir)
    controller = DryRunController(storage)
    memory = JsonlMemoryAdapter(memory_file) if memory_file else None
    runtime = VeraArkRuntime(
        config=RuntimeConfig(
            monitor_index=monitor,
            steps=steps,
            interval_seconds=interval,
            stop_file=stop_file,
        ),
        capture=capture,
        perception=OfflinePerceptionEngine(),
        planner=make_planner(planner_name),
        controller=controller,
        storage=storage,
        memory=memory,
        motion_guard=motion_guard,
    )
    result = runtime.run()
    _json_print(result.to_dict())
    return 0


def demo_command(args: argparse.Namespace) -> int:
    log_dir = args.log_dir or Path(".vera_ark") / f"demo-{_timestamp_slug()}"
    try:
        return _run_runtime(
            capture=SyntheticCapture(),
            planner_name=args.planner,
            monitor=0,
            steps=args.steps,
            interval=0.0,
            log_dir=log_dir,
            stop_file=args.stop_file,
            memory_file=args.memory_file,
            motion_guard_file=args.motion_guard_config,
        )
    except Exception as exc:
        print(f"demo failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def capture_command(args: argparse.Namespace) -> int:
    try:
        frame = WindowsMonitorCapture().capture(args.monitor)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(frame.png_bytes)
        _json_print(
            {
                "output": str(args.output),
                "monitor_index": frame.monitor_index,
                "width": frame.width,
                "height": frame.height,
                "sha256": frame.sha256,
            }
        )
        return 0
    except (CaptureError, OSError) as exc:
        print(f"capture failed: {exc}", file=sys.stderr)
        return 2


def run_command(args: argparse.Namespace) -> int:
    log_dir = args.log_dir or Path(".vera_ark") / f"run-{_timestamp_slug()}"
    try:
        capture = WindowsMonitorCapture()
        return _run_runtime(
            capture=capture,
            planner_name=args.planner,
            monitor=args.monitor,
            steps=args.steps,
            interval=args.interval,
            log_dir=log_dir,
            stop_file=args.stop_file,
            memory_file=args.memory_file,
            motion_guard_file=args.motion_guard_config,
        )
    except (CaptureError, OSError, ValueError) as exc:
        print(f"run failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vera-ark", description="VERA ARK local dry-run runtime")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="show local runtime diagnostics")
    doctor.set_defaults(func=doctor_command)

    demo = sub.add_parser("demo", help="run a synthetic offline dry-run demo")
    demo.add_argument("--steps", type=int, default=2)
    demo.add_argument("--planner", choices=("heuristic", "openai"), default="heuristic")
    demo.add_argument("--log-dir", type=Path)
    demo.add_argument("--stop-file", type=Path, default=Path(".vera_ark/STOP"))
    demo.add_argument("--memory-file", type=Path)
    demo.add_argument("--motion-guard-config", type=Path, help="explicit dry-run Physica world model JSON")
    demo.set_defaults(func=demo_command)

    capture = sub.add_parser("capture", help="capture one Windows monitor to PNG")
    capture.add_argument("--monitor", type=int, required=True)
    capture.add_argument("--output", type=Path, required=True)
    capture.set_defaults(func=capture_command)

    run = sub.add_parser("run", help="run the bounded Windows perception-to-intention loop")
    run.add_argument("--monitor", type=int, required=True)
    run.add_argument("--planner", choices=("heuristic", "openai"), default="heuristic")
    run.add_argument("--steps", type=int, required=True)
    run.add_argument("--interval", type=float, required=True)
    run.add_argument("--log-dir", type=Path)
    run.add_argument("--stop-file", type=Path, default=Path(".vera_ark/STOP"))
    run.add_argument("--memory-file", type=Path)
    run.add_argument("--motion-guard-config", type=Path, help="explicit dry-run Physica world model JSON")
    run.set_defaults(func=run_command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
