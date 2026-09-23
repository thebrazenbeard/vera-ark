from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
import hashlib
import struct
from typing import Any

from .models import ActionIntention, ActionType, new_id, utc_now
from .storage import OperationalStorage


class ControllerError(RuntimeError):
    pass


class DPad(IntEnum):
    UP = 0
    UP_RIGHT = 1
    RIGHT = 2
    DOWN_RIGHT = 3
    DOWN = 4
    DOWN_LEFT = 5
    LEFT = 6
    UP_LEFT = 7
    NEUTRAL = 8


class DS4Button(StrEnum):
    SQUARE = "square"
    CROSS = "cross"
    CIRCLE = "circle"
    TRIANGLE = "triangle"
    L1 = "l1"
    R1 = "r1"
    L2_DIGITAL = "l2_digital"
    R2_DIGITAL = "r2_digital"
    SHARE = "share"
    OPTIONS = "options"
    L3 = "l3"
    R3 = "r3"
    PS = "ps"
    TOUCHPAD_CLICK = "touchpad_click"


DS4_USB_REPORT_ID = 0x01
DS4_USB_REPORT_SIZE = 64
DS4_STICK_NEUTRAL = 128
DS4_ANALOG_MIN = 0
DS4_ANALOG_MAX = 255
DS4_REPORT_CONTRACT = "VERA_ARK_DS4_USB_INPUT_REPORT_V1"
DS4_BATCH_CONTRACT = "VERA_ARK_VHF_DS4_SUBMISSION_BATCH_V1"
DS4_LOOPBACK_BACKEND = "VERA_ARK_DS4_LOOPBACK_V1"
VHF_DEVICE_INTERFACE_GUID = "{8F78C4F8-1D21-4C5C-BBAA-2D907D98C721}"
VHF_IOCTL_SUBMIT_DS4_BATCH = 0x22A004
DS4_SELECTED_WINDOWS_BACKEND = {
    "backend_id": "VERA_ARK_MICROSOFT_VHF_KMDF_DS4_V1",
    "backend_version": 1,
    "framework": "Microsoft Virtual HID Framework (VHF)",
    "framework_api": "VhfReadReportSubmit",
    "driver_model": "KMDF kernel-mode HID source driver",
    "minimum_os": "Windows 10",
    "device_interface_guid": VHF_DEVICE_INTERFACE_GUID,
    "ioctl_submit_batch": f"0x{VHF_IOCTL_SUBMIT_DS4_BATCH:08X}",
    "ioctl_definition": "CTL_CODE(FILE_DEVICE_UNKNOWN,0x801,METHOD_BUFFERED,FILE_WRITE_DATA)",
    "submission_contract": DS4_BATCH_CONTRACT,
    "report_contract": DS4_REPORT_CONTRACT,
    "implementation_state": "SELECTED_NOT_IMPLEMENTED_OR_INSTALLED",
    "live_output_authorized": False,
}

_BUTTON_LOCATIONS: dict[DS4Button, tuple[int, int]] = {
    DS4Button.SQUARE: (5, 0x10),
    DS4Button.CROSS: (5, 0x20),
    DS4Button.CIRCLE: (5, 0x40),
    DS4Button.TRIANGLE: (5, 0x80),
    DS4Button.L1: (6, 0x01),
    DS4Button.R1: (6, 0x02),
    DS4Button.L2_DIGITAL: (6, 0x04),
    DS4Button.R2_DIGITAL: (6, 0x08),
    DS4Button.SHARE: (6, 0x10),
    DS4Button.OPTIONS: (6, 0x20),
    DS4Button.L3: (6, 0x40),
    DS4Button.R3: (6, 0x80),
    DS4Button.PS: (7, 0x01),
    DS4Button.TOUCHPAD_CLICK: (7, 0x02),
}


def button_mask_table() -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for button, (offset, mask) in _BUTTON_LOCATIONS.items():
        result[button.value] = {"offset": offset, "mask": mask}
    return result


def normalized_axis_to_u8(value: float, *, invert: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ControllerError("axis value must be numeric")
    number = float(value)
    if not -1.0 <= number <= 1.0:
        raise ControllerError("axis value must be between -1 and 1")
    if invert:
        number = -number
    return max(0, min(255, round((number + 1.0) * 127.5)))


def _u8(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
        raise ControllerError(f"{field_name} must be an integer from 0 through 255")
    return value


@dataclass(frozen=True, slots=True)
class DS4State:
    left_x: int = DS4_STICK_NEUTRAL
    left_y: int = DS4_STICK_NEUTRAL
    right_x: int = DS4_STICK_NEUTRAL
    right_y: int = DS4_STICK_NEUTRAL
    dpad: DPad = DPad.NEUTRAL
    buttons: frozenset[DS4Button] = field(default_factory=frozenset)
    left_trigger: int = 0
    right_trigger: int = 0

    def __post_init__(self) -> None:
        _u8(self.left_x, "left_x")
        _u8(self.left_y, "left_y")
        _u8(self.right_x, "right_x")
        _u8(self.right_y, "right_y")
        _u8(self.left_trigger, "left_trigger")
        _u8(self.right_trigger, "right_trigger")
        if not isinstance(self.dpad, DPad):
            raise ControllerError("dpad must be a DPad")
        if not isinstance(self.buttons, frozenset):
            raise ControllerError("buttons must be a frozenset")
        for button in self.buttons:
            if not isinstance(button, DS4Button):
                raise ControllerError("buttons contains an unknown value")

    @classmethod
    def neutral(cls) -> "DS4State":
        return cls()

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_x": self.left_x,
            "left_y": self.left_y,
            "right_x": self.right_x,
            "right_y": self.right_y,
            "dpad": self.dpad.name,
            "buttons": sorted(button.value for button in self.buttons),
            "left_trigger": self.left_trigger,
            "right_trigger": self.right_trigger,
        }


class DS4USBReportV1:
    """Exact 64-byte DS4 USB input report subset used by the selected VHF contract."""

    @staticmethod
    def serialize(state: DS4State) -> bytes:
        report = bytearray(DS4_USB_REPORT_SIZE)
        report[0] = DS4_USB_REPORT_ID
        report[1] = state.left_x
        report[2] = state.left_y
        report[3] = state.right_x
        report[4] = state.right_y
        report[5] = int(state.dpad) & 0x0F
        for button in state.buttons:
            offset, mask = _BUTTON_LOCATIONS[button]
            report[offset] |= mask
        report[8] = state.left_trigger
        report[9] = state.right_trigger
        return bytes(report)

    @staticmethod
    def deserialize(report: bytes) -> DS4State:
        if not isinstance(report, bytes):
            raise ControllerError("DS4 report must be bytes")
        if len(report) != DS4_USB_REPORT_SIZE:
            raise ControllerError(
                f"DS4 USB report must contain exactly {DS4_USB_REPORT_SIZE} bytes"
            )
        if report[0] != DS4_USB_REPORT_ID:
            raise ControllerError(
                f"unsupported DS4 report id 0x{report[0]:02x}; expected 0x01"
            )
        if any(report[10:]):
            raise ControllerError(
                "unsupported nonzero sensor, touch, status, or reserved bytes in v1 report"
            )
        dpad_value = report[5] & 0x0F
        try:
            dpad = DPad(dpad_value)
        except ValueError as exc:
            raise ControllerError(f"unsupported dpad value {dpad_value}") from exc
        buttons: set[DS4Button] = set()
        for button, (offset, mask) in _BUTTON_LOCATIONS.items():
            if report[offset] & mask:
                buttons.add(button)
        allowed_buttons0 = 0xFF
        allowed_buttons1 = 0xFF
        allowed_buttons2 = 0x03
        if report[5] & ~allowed_buttons0:
            raise ControllerError("buttons0 contains unsupported bits")
        if report[6] & ~allowed_buttons1:
            raise ControllerError("buttons1 contains unsupported bits")
        if report[7] & ~allowed_buttons2:
            raise ControllerError("buttons2 contains unsupported bits")
        return DS4State(
            left_x=report[1],
            left_y=report[2],
            right_x=report[3],
            right_y=report[4],
            dpad=dpad,
            buttons=frozenset(buttons),
            left_trigger=report[8],
            right_trigger=report[9],
        )

    @classmethod
    def verify_round_trip(cls, report: bytes) -> DS4State:
        state = cls.deserialize(report)
        if cls.serialize(state) != report:
            raise ControllerError("DS4 report failed exact round-trip verification")
        return state

    @classmethod
    def neutral_report(cls) -> bytes:
        return cls.serialize(DS4State.neutral())

    @classmethod
    def is_neutral(cls, report: bytes) -> bool:
        cls.verify_round_trip(report)
        return report == cls.neutral_report()


class VHFDS4SubmissionBatchV1:
    """Atomic user-mode-to-KMDF batch envelope for the selected future VHF backend."""

    MAGIC = b"VAD4"
    VERSION = 1
    MAX_REPORTS = 8
    HEADER = struct.Struct("<4sHHII")
    ENTRY = struct.Struct("<I64s")

    @classmethod
    def serialize(
        cls,
        sequence: int,
        reports: tuple[tuple[bytes, int], ...],
    ) -> bytes:
        if isinstance(sequence, bool) or not isinstance(sequence, int):
            raise ControllerError("batch sequence must be an integer")
        if not 1 <= sequence <= 0xFFFFFFFF:
            raise ControllerError("batch sequence must be between 1 and uint32 max")
        cls._validate_reports(reports)
        body = bytearray(
            cls.HEADER.pack(
                cls.MAGIC,
                cls.VERSION,
                DS4_USB_REPORT_SIZE,
                sequence,
                len(reports),
            )
        )
        for report, offset_ms in reports:
            body.extend(cls.ENTRY.pack(offset_ms, report))
        return bytes(body)

    @classmethod
    def deserialize(cls, frame: bytes) -> tuple[int, tuple[tuple[bytes, int], ...]]:
        if not isinstance(frame, bytes) or len(frame) < cls.HEADER.size:
            raise ControllerError("VHF submission frame is truncated")
        magic, version, report_size, sequence, count = cls.HEADER.unpack_from(frame, 0)
        if magic != cls.MAGIC:
            raise ControllerError("VHF submission magic mismatch")
        if version != cls.VERSION:
            raise ControllerError(f"unsupported VHF submission version {version}")
        if report_size != DS4_USB_REPORT_SIZE:
            raise ControllerError("VHF submission report size mismatch")
        if not 1 <= count <= cls.MAX_REPORTS:
            raise ControllerError("VHF submission report count is out of bounds")
        expected_size = cls.HEADER.size + count * cls.ENTRY.size
        if len(frame) != expected_size:
            raise ControllerError(
                f"VHF submission frame must contain exactly {expected_size} bytes"
            )
        reports: list[tuple[bytes, int]] = []
        cursor = cls.HEADER.size
        for _ in range(count):
            offset_ms, report = cls.ENTRY.unpack_from(frame, cursor)
            reports.append((report, offset_ms))
            cursor += cls.ENTRY.size
        result = tuple(reports)
        cls._validate_reports(result)
        return sequence, result

    @classmethod
    def _validate_reports(cls, reports: tuple[tuple[bytes, int], ...]) -> None:
        if not isinstance(reports, tuple) or not 1 <= len(reports) <= cls.MAX_REPORTS:
            raise ControllerError("report batch must contain between 1 and 8 reports")
        previous_offset = -1
        has_non_neutral = False
        for index, item in enumerate(reports):
            if not isinstance(item, tuple) or len(item) != 2:
                raise ControllerError("each batch item must be (report, offset_ms)")
            report, offset_ms = item
            if isinstance(offset_ms, bool) or not isinstance(offset_ms, int):
                raise ControllerError("offset_ms must be an integer")
            if not 0 <= offset_ms <= ActionIntention.MAX_DURATION_MS:
                raise ControllerError("offset_ms is out of bounds")
            if index == 0 and offset_ms != 0:
                raise ControllerError("first report offset must be zero")
            if offset_ms < previous_offset:
                raise ControllerError("report offsets must be nondecreasing")
            previous_offset = offset_ms
            DS4USBReportV1.verify_round_trip(report)
            has_non_neutral = has_non_neutral or not DS4USBReportV1.is_neutral(report)
        if has_non_neutral and not DS4USBReportV1.is_neutral(reports[-1][0]):
            raise ControllerError("every non-neutral batch must end with neutral release")


@dataclass(frozen=True, slots=True)
class TransportReceipt:
    receipt_id: str
    backend: str
    report_contract: str
    offset_ms: int
    report_sha256: str
    report_hex: str
    batch_sequence: int
    submission_sha256: str
    submission_hex: str
    loopback_verified: bool
    decoded_state: dict[str, Any]
    external_inputs_sent: int
    record_time: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "backend": self.backend,
            "report_contract": self.report_contract,
            "offset_ms": self.offset_ms,
            "report_sha256": self.report_sha256,
            "report_hex": self.report_hex,
            "batch_sequence": self.batch_sequence,
            "submission_sha256": self.submission_sha256,
            "submission_hex": self.submission_hex,
            "loopback_verified": self.loopback_verified,
            "decoded_state": self.decoded_state,
            "external_inputs_sent": self.external_inputs_sent,
            "record_time": self.record_time,
        }


class LoopbackDS4Transport:
    """Serializer loopback only. This class has no OS or Remote Play output path."""

    backend_name = DS4_LOOPBACK_BACKEND
    dry_run_only = True

    def __init__(self) -> None:
        self.receipts: list[TransportReceipt] = []
        self.external_inputs_sent = 0
        self._batch_sequence = 0

    def submit_batch(
        self,
        reports: tuple[tuple[bytes, int], ...],
    ) -> list[TransportReceipt]:
        self._batch_sequence += 1
        frame = VHFDS4SubmissionBatchV1.serialize(self._batch_sequence, reports)
        parsed_sequence, parsed_reports = VHFDS4SubmissionBatchV1.deserialize(frame)
        if parsed_sequence != self._batch_sequence or parsed_reports != reports:
            raise ControllerError("VHF submission batch failed exact loopback verification")
        submission_sha256 = hashlib.sha256(frame).hexdigest()
        submission_hex = frame.hex()
        receipts: list[TransportReceipt] = []
        for report, offset_ms in parsed_reports:
            state = DS4USBReportV1.verify_round_trip(report)
            receipt = TransportReceipt(
                receipt_id=new_id(),
                backend=self.backend_name,
                report_contract=DS4_REPORT_CONTRACT,
                offset_ms=offset_ms,
                report_sha256=hashlib.sha256(report).hexdigest(),
                report_hex=report.hex(),
                batch_sequence=parsed_sequence,
                submission_sha256=submission_sha256,
                submission_hex=submission_hex,
                loopback_verified=True,
                decoded_state=state.to_dict(),
                external_inputs_sent=0,
                record_time=utc_now(),
            )
            self.receipts.append(receipt)
            receipts.append(receipt)
        return receipts


@dataclass(frozen=True, slots=True)
class ControllerReceipt:
    receipt_id: str
    intention_id: str
    session_id: str
    step: int
    disposition: str
    transport_backend: str
    report_contract: str
    reports_serialized: int
    loopback_verified: bool
    external_inputs_sent: int
    record_time: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "intention_id": self.intention_id,
            "session_id": self.session_id,
            "step": self.step,
            "disposition": self.disposition,
            "transport_backend": self.transport_backend,
            "report_contract": self.report_contract,
            "reports_serialized": self.reports_serialized,
            "loopback_verified": self.loopback_verified,
            "external_inputs_sent": self.external_inputs_sent,
            "record_time": self.record_time,
        }


def intention_to_ds4_sequence(
    intention: ActionIntention,
) -> tuple[tuple[DS4State, int], ...]:
    neutral = DS4State.neutral()
    if intention.action_type is ActionType.NOOP:
        return ((neutral, 0),)
    if intention.action_type is ActionType.MOVE:
        active = DS4State(
            left_x=normalized_axis_to_u8(intention.x),
            left_y=normalized_axis_to_u8(intention.y, invert=True),
        )
    elif intention.action_type is ActionType.LOOK:
        active = DS4State(
            right_x=normalized_axis_to_u8(intention.x),
            right_y=normalized_axis_to_u8(intention.y, invert=True),
        )
    elif intention.action_type is ActionType.INTERACT:
        active = DS4State(buttons=frozenset({DS4Button.CROSS}))
    else:
        raise ControllerError(f"unsupported semantic action: {intention.action_type.value}")
    release_offset = max(1, intention.duration_ms)
    return ((active, 0), (neutral, release_offset))


class DryRunController:
    """The only v0.1 controller: DS4 serialization and loopback, never injection."""

    backend_name = "dry-run-ds4-loopback-v1"

    def __init__(
        self,
        storage: OperationalStorage,
        transport: LoopbackDS4Transport | None = None,
    ) -> None:
        self.storage = storage
        if transport is not None and type(transport) is not LoopbackDS4Transport:
            raise ControllerError("only the sealed loopback transport is allowed in v0.1")
        self.transport = transport or LoopbackDS4Transport()
        self._last_step_by_session: dict[str, int] = {}
        self._seen_intentions: set[str] = set()
        self.external_inputs_sent = 0

    def _serialize_sequence(
        self,
        sequence: tuple[tuple[DS4State, int], ...],
    ) -> list[TransportReceipt]:
        reports = tuple(
            (DS4USBReportV1.serialize(state), offset_ms)
            for state, offset_ms in sequence
        )
        receipts = self.transport.submit_batch(reports)
        if self.transport.external_inputs_sent != 0:
            raise ControllerError("loopback transport reported external output")
        return receipts

    def execute(self, intention: ActionIntention) -> ControllerReceipt:
        if intention.dry_run is not True:
            raise ControllerError("live controller output is unsupported")
        if intention.action_type is ActionType.RELEASE_ALL:
            raise ControllerError("RELEASE_ALL is reserved for release_all()")
        if intention.intention_id in self._seen_intentions:
            raise ControllerError("duplicate intention rejected")
        previous = self._last_step_by_session.get(intention.session_id, -1)
        if intention.step <= previous:
            raise ControllerError("stale or duplicated step rejected")
        self._seen_intentions.add(intention.intention_id)
        self._last_step_by_session[intention.session_id] = intention.step
        report_receipts = self._serialize_sequence(intention_to_ds4_sequence(intention))
        receipt = ControllerReceipt(
            receipt_id=new_id(),
            intention_id=intention.intention_id,
            session_id=intention.session_id,
            step=intention.step,
            disposition="DS4_REPORTS_LOOPBACK_VERIFIED_NO_EXTERNAL_INPUT",
            transport_backend=self.transport.backend_name,
            report_contract=DS4_REPORT_CONTRACT,
            reports_serialized=len(report_receipts),
            loopback_verified=all(item.loopback_verified for item in report_receipts),
            external_inputs_sent=0,
            record_time=utc_now(),
        )
        self.storage.action(
            "ACTION_INTENTION_DRY_RUN",
            {
                "controller": self.backend_name,
                "selected_future_windows_backend": DS4_SELECTED_WINDOWS_BACKEND,
                "intention": intention.to_dict(),
                "transport_receipts": [item.to_dict() for item in report_receipts],
                "receipt": receipt.to_dict(),
            },
        )
        return receipt

    def release_all(self, session_id: str, step: int, reason: str) -> ControllerReceipt:
        release = ActionIntention(
            schema_version=ActionIntention.SCHEMA_VERSION,
            intention_id=new_id(),
            perception_id=new_id(),
            session_id=session_id,
            step=max(0, step),
            action_type=ActionType.RELEASE_ALL,
            x=0.0,
            y=0.0,
            duration_ms=0,
            reason=reason,
            planner="runtime-safety-layer",
            created_at=utc_now(),
            dry_run=True,
        )
        report_receipts = self._serialize_sequence(((DS4State.neutral(), 0),))
        neutral_hex = DS4USBReportV1.neutral_report().hex()
        if report_receipts[0].report_hex != neutral_hex:
            raise ControllerError("release_all did not serialize the exact neutral report")
        receipt = ControllerReceipt(
            receipt_id=new_id(),
            intention_id=release.intention_id,
            session_id=session_id,
            step=release.step,
            disposition="VERIFIED_NEUTRAL_DS4_REPORT_NO_EXTERNAL_INPUT",
            transport_backend=self.transport.backend_name,
            report_contract=DS4_REPORT_CONTRACT,
            reports_serialized=1,
            loopback_verified=True,
            external_inputs_sent=0,
            record_time=utc_now(),
        )
        self.storage.action(
            "RELEASE_ALL",
            {
                "controller": self.backend_name,
                "selected_future_windows_backend": DS4_SELECTED_WINDOWS_BACKEND,
                "neutral_report_hex": neutral_hex,
                "intention": release.to_dict(),
                "transport_receipts": [item.to_dict() for item in report_receipts],
                "receipt": receipt.to_dict(),
            },
        )
        return receipt
