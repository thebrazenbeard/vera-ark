from __future__ import annotations

from dataclasses import dataclass
import binascii
import ctypes
from ctypes import wintypes
import hashlib
import struct
import sys
import zlib


class CaptureError(RuntimeError):
    """Raised when a monitor frame cannot be captured safely."""


@dataclass(frozen=True, slots=True)
class MonitorInfo:
    index: int
    left: int
    top: int
    right: int
    bottom: int
    primary: bool

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    png_bytes: bytes
    width: int
    height: int
    monitor_index: int

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.png_bytes).hexdigest()


class CaptureProvider:
    def capture(self, monitor_index: int) -> CapturedFrame:
        raise NotImplementedError


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", binascii.crc32(body) & 0xFFFFFFFF)


def encode_rgba_png(width: int, height: int, rgba: bytes) -> bytes:
    expected = width * height * 4
    if width <= 0 or height <= 0 or len(rgba) != expected:
        raise CaptureError("invalid RGBA buffer dimensions")
    scanlines = bytearray()
    stride = width * 4
    for row in range(height):
        scanlines.append(0)
        start = row * stride
        scanlines.extend(rgba[start : start + stride])
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(bytes(scanlines), level=6))
        + _png_chunk(b"IEND", b"")
    )


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", wintypes.DWORD),
    ]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class WindowsMonitorCapture(CaptureProvider):
    """Windows GDI monitor capture with no shell or third-party dependency."""

    SRCCOPY = 0x00CC0020
    CAPTUREBLT = 0x40000000
    DIB_RGB_COLORS = 0
    BI_RGB = 0
    MONITORINFOF_PRIMARY = 1

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise CaptureError("monitor capture requires Windows")
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        self._configure_functions()

    def _configure_functions(self) -> None:
        handle = ctypes.c_void_p
        self.user32.GetDC.argtypes = [handle]
        self.user32.GetDC.restype = handle
        self.user32.ReleaseDC.argtypes = [handle, handle]
        self.user32.ReleaseDC.restype = ctypes.c_int
        self.user32.GetMonitorInfoW.argtypes = [handle, ctypes.POINTER(_MONITORINFO)]
        self.user32.GetMonitorInfoW.restype = wintypes.BOOL
        self.gdi32.CreateCompatibleDC.argtypes = [handle]
        self.gdi32.CreateCompatibleDC.restype = handle
        self.gdi32.CreateCompatibleBitmap.argtypes = [handle, ctypes.c_int, ctypes.c_int]
        self.gdi32.CreateCompatibleBitmap.restype = handle
        self.gdi32.SelectObject.argtypes = [handle, handle]
        self.gdi32.SelectObject.restype = handle
        self.gdi32.BitBlt.argtypes = [
            handle, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            handle, ctypes.c_int, ctypes.c_int, wintypes.DWORD,
        ]
        self.gdi32.BitBlt.restype = wintypes.BOOL
        self.gdi32.GetDIBits.argtypes = [
            handle, handle, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
            ctypes.POINTER(_BITMAPINFO), wintypes.UINT,
        ]
        self.gdi32.GetDIBits.restype = ctypes.c_int
        self.gdi32.DeleteObject.argtypes = [handle]
        self.gdi32.DeleteObject.restype = wintypes.BOOL
        self.gdi32.DeleteDC.argtypes = [handle]
        self.gdi32.DeleteDC.restype = wintypes.BOOL

    def monitors(self) -> list[MonitorInfo]:
        monitor_handles: list[int] = []
        callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(_RECT),
            ctypes.c_long,
        )

        def callback(hmonitor: int, _hdc: int, _rect: object, _data: int) -> int:
            monitor_handles.append(hmonitor)
            return 1

        callback_ref = callback_type(callback)
        ok = self.user32.EnumDisplayMonitors(None, None, callback_ref, 0)
        if not ok:
            raise CaptureError(f"EnumDisplayMonitors failed: {ctypes.get_last_error()}")
        result: list[MonitorInfo] = []
        for handle in monitor_handles:
            info = _MONITORINFO()
            info.cbSize = ctypes.sizeof(_MONITORINFO)
            if not self.user32.GetMonitorInfoW(handle, ctypes.byref(info)):
                raise CaptureError(f"GetMonitorInfoW failed: {ctypes.get_last_error()}")
            rect = info.rcMonitor
            result.append(
                MonitorInfo(
                    index=0,
                    left=rect.left,
                    top=rect.top,
                    right=rect.right,
                    bottom=rect.bottom,
                    primary=bool(info.dwFlags & self.MONITORINFOF_PRIMARY),
                )
            )
        result.sort(key=lambda item: (not item.primary, item.left, item.top, item.right, item.bottom))
        return [
            MonitorInfo(i, item.left, item.top, item.right, item.bottom, item.primary)
            for i, item in enumerate(result)
        ]

    def _monitor_handle(self, selected: MonitorInfo) -> int:
        chosen: list[int] = []
        callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(_RECT),
            ctypes.c_long,
        )

        def callback(hmonitor: int, _hdc: int, rect_ptr: object, _data: int) -> int:
            rect = rect_ptr.contents
            if (rect.left, rect.top, rect.right, rect.bottom) == (
                selected.left, selected.top, selected.right, selected.bottom
            ):
                chosen.append(hmonitor)
                return 0
            return 1

        callback_ref = callback_type(callback)
        self.user32.EnumDisplayMonitors(None, None, callback_ref, 0)
        if not chosen:
            raise CaptureError("selected monitor changed before capture")
        return chosen[0]

    def capture(self, monitor_index: int) -> CapturedFrame:
        monitors = self.monitors()
        if isinstance(monitor_index, bool) or not isinstance(monitor_index, int):
            raise CaptureError("monitor index must be an integer")
        if monitor_index < 0 or monitor_index >= len(monitors):
            raise CaptureError(
                f"monitor {monitor_index} is unavailable; detected indexes: "
                + ", ".join(str(item.index) for item in monitors)
            )
        monitor = monitors[monitor_index]
        width, height = monitor.width, monitor.height
        if width <= 0 or height <= 0 or width > 32768 or height > 32768:
            raise CaptureError("monitor dimensions are invalid or unsupported")

        screen_dc = self.user32.GetDC(None)
        if not screen_dc:
            raise CaptureError(f"GetDC failed: {ctypes.get_last_error()}")
        memory_dc = bitmap = old_object = None
        try:
            memory_dc = self.gdi32.CreateCompatibleDC(screen_dc)
            if not memory_dc:
                raise CaptureError(f"CreateCompatibleDC failed: {ctypes.get_last_error()}")
            bitmap = self.gdi32.CreateCompatibleBitmap(screen_dc, width, height)
            if not bitmap:
                raise CaptureError(f"CreateCompatibleBitmap failed: {ctypes.get_last_error()}")
            old_object = self.gdi32.SelectObject(memory_dc, bitmap)
            if not old_object:
                raise CaptureError(f"SelectObject failed: {ctypes.get_last_error()}")
            copied = self.gdi32.BitBlt(
                memory_dc, 0, 0, width, height, screen_dc, monitor.left, monitor.top,
                self.SRCCOPY | self.CAPTUREBLT,
            )
            if not copied:
                raise CaptureError(f"BitBlt failed: {ctypes.get_last_error()}")

            info = _BITMAPINFO()
            info.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
            info.bmiHeader.biWidth = width
            info.bmiHeader.biHeight = -height
            info.bmiHeader.biPlanes = 1
            info.bmiHeader.biBitCount = 32
            info.bmiHeader.biCompression = self.BI_RGB
            buffer = ctypes.create_string_buffer(width * height * 4)
            lines = self.gdi32.GetDIBits(
                memory_dc, bitmap, 0, height, buffer, ctypes.byref(info), self.DIB_RGB_COLORS
            )
            if lines != height:
                raise CaptureError(
                    f"GetDIBits returned {lines} lines instead of {height}: {ctypes.get_last_error()}"
                )
            bgra = buffer.raw
            rgba = bytearray(len(bgra))
            for offset in range(0, len(bgra), 4):
                rgba[offset] = bgra[offset + 2]
                rgba[offset + 1] = bgra[offset + 1]
                rgba[offset + 2] = bgra[offset]
                rgba[offset + 3] = 255
            return CapturedFrame(encode_rgba_png(width, height, bytes(rgba)), width, height, monitor_index)
        finally:
            if old_object and memory_dc:
                self.gdi32.SelectObject(memory_dc, old_object)
            if bitmap:
                self.gdi32.DeleteObject(bitmap)
            if memory_dc:
                self.gdi32.DeleteDC(memory_dc)
            self.user32.ReleaseDC(None, screen_dc)


class SyntheticCapture(CaptureProvider):
    """Deterministic cross-platform capture provider for demos and tests."""

    def __init__(self, width: int = 64, height: int = 36) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("synthetic dimensions must be positive")
        self.width = width
        self.height = height
        pixels = bytearray()
        for y in range(height):
            for x in range(width):
                pixels.extend(((x * 5) % 256, (y * 7) % 256, ((x + y) * 3) % 256, 255))
        self._png = encode_rgba_png(width, height, bytes(pixels))

    def capture(self, monitor_index: int) -> CapturedFrame:
        if monitor_index != 0:
            raise CaptureError("synthetic capture exposes monitor index 0 only")
        return CapturedFrame(self._png, self.width, self.height, 0)
