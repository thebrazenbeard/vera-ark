from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Callable

from .capture import CaptureProvider
from .controller import DryRunController
from .models import new_id
from .planner import ActionPlanner, FallbackPlanner, PerceptionEngine
from .storage import MemoryAdapter, NullMemoryAdapter, OperationalStorage


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    monitor_index: int = 0
    steps: int = 1
    interval_seconds: float = 1.0
    stop_file: Path = Path(".vera_ark/STOP")

    def __post_init__(self) -> None:
        if isinstance(self.monitor_index, bool) or not isinstance(self.monitor_index, int):
            raise ValueError("monitor_index must be an integer")
        if not 0 <= self.monitor_index <= 127:
            raise ValueError("monitor_index must be between 0 and 127")
        if isinstance(self.steps, bool) or not isinstance(self.steps, int) or not 1 <= self.steps <= 10_000:
            raise ValueError("steps must be an integer between 1 and 10000")
        if isinstance(self.interval_seconds, bool) or not isinstance(self.interval_seconds, (int, float)):
            raise ValueError("interval_seconds must be numeric")
        if not 0.0 <= float(self.interval_seconds) <= 60.0:
            raise ValueError("interval_seconds must be between 0 and 60")


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    session_id: str
    requested_steps: int
    completed_steps: int
    stopped: bool
    release_recorded: bool
    event_log: str
    action_log: str

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "requested_steps": self.requested_steps,
            "completed_steps": self.completed_steps,
            "stopped": self.stopped,
            "release_recorded": self.release_recorded,
            "event_log": self.event_log,
            "action_log": self.action_log,
        }


class VeraArkRuntime:
    """Capture -> perception -> planning -> safety -> dry-run execution -> storage."""

    def __init__(
        self,
        config: RuntimeConfig,
        capture: CaptureProvider,
        perception: PerceptionEngine,
        planner: ActionPlanner,
        controller: DryRunController,
        storage: OperationalStorage,
        memory: MemoryAdapter | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.capture = capture
        self.perception = perception
        self.planner = planner
        self.controller = controller
        self.storage = storage
        self.memory = memory or NullMemoryAdapter()
        self.sleeper = sleeper

    def _stop_requested(self) -> bool:
        return self.config.stop_file.exists()

    def run(self) -> RuntimeResult:
        session_id = new_id()
        completed = 0
        stopped = False
        release_recorded = False
        self.storage.event(
            "SESSION_STARTED",
            {
                "session_id": session_id,
                "config": {
                    "monitor_index": self.config.monitor_index,
                    "steps": self.config.steps,
                    "interval_seconds": float(self.config.interval_seconds),
                    "stop_file": str(self.config.stop_file),
                    "controller_backend": self.controller.backend_name,
                },
            },
        )
        try:
            for step in range(self.config.steps):
                if self._stop_requested():
                    stopped = True
                    self.storage.event(
                        "EMERGENCY_STOP_OBSERVED",
                        {"session_id": session_id, "step": step, "phase": "BEFORE_CAPTURE"},
                    )
                    break

                frame = self.capture.capture(self.config.monitor_index)
                self.storage.event(
                    "FRAME_CAPTURED",
                    {
                        "session_id": session_id,
                        "step": step,
                        "monitor_index": frame.monitor_index,
                        "width": frame.width,
                        "height": frame.height,
                        "image_sha256": frame.sha256,
                    },
                )
                perception = self.perception.perceive(frame, session_id, step)
                self.storage.event("PERCEPTION_RESULT", perception.to_dict())

                memory_context = self.memory.recall(perception)
                memory_error = getattr(self.memory, "last_error", None)
                if memory_error:
                    self.storage.event(
                        "OPTIONAL_MEMORY_IGNORED",
                        {"session_id": session_id, "step": step, "reason": memory_error},
                    )

                intention = self.planner.plan(perception, frame, memory_context)
                self.storage.event("ACTION_INTENTION_PLANNED", intention.to_dict())
                if isinstance(self.planner, FallbackPlanner) and self.planner.last_fallback_reason:
                    self.storage.event(
                        "PLANNER_FALLBACK",
                        {
                            "session_id": session_id,
                            "step": step,
                            "reason": self.planner.last_fallback_reason,
                        },
                    )

                if self._stop_requested():
                    stopped = True
                    self.storage.event(
                        "EMERGENCY_STOP_OBSERVED",
                        {"session_id": session_id, "step": step, "phase": "BEFORE_ACTION"},
                    )
                    break

                receipt = self.controller.execute(intention)
                self.storage.event("DRY_RUN_ACTION_RECORDED", receipt.to_dict())
                completed += 1
                if step + 1 < self.config.steps and self.config.interval_seconds:
                    self.sleeper(float(self.config.interval_seconds))
        except Exception as exc:
            self.storage.event(
                "SESSION_ERROR",
                {
                    "session_id": session_id,
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:500],
                },
            )
            raise
        finally:
            receipt = self.controller.release_all(
                session_id=session_id,
                step=completed,
                reason="Runtime exit safety invariant",
            )
            release_recorded = True
            self.storage.event("FORCED_RELEASE_RECORDED", receipt.to_dict())
            self.storage.event(
                "SESSION_ENDED",
                {
                    "session_id": session_id,
                    "requested_steps": self.config.steps,
                    "completed_steps": completed,
                    "stopped": stopped,
                    "release_recorded": release_recorded,
                    "external_inputs_sent": self.controller.external_inputs_sent,
                },
            )
        return RuntimeResult(
            session_id=session_id,
            requested_steps=self.config.steps,
            completed_steps=completed,
            stopped=stopped,
            release_recorded=release_recorded,
            event_log=str(self.storage.event_ledger.path),
            action_log=str(self.storage.action_ledger.path),
        )
