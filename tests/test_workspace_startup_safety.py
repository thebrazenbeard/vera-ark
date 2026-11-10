"""Source-level guard against editor-open commands and disguised executable assets.

The tests inspect repository bytes only; no workspace task or font is executed.
"""

from __future__ import annotations

import json
import re
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTERPRETER = re.compile(
    r"(?:^|[\s'\";&|/\\])(?:node(?:\.exe|js)?|python(?:\d+(?:\.\d+)?)?(?:\.exe)?|py(?:\.exe)?|bun|deno)(?=$|[\s'\";&|])",
    re.IGNORECASE,
)
EXECUTABLE_ASSET = re.compile(
    r"\.(?:ttf|otf|ttc|woff2?|eot|svg|lkf)\b",
    re.IGNORECASE,
)


def _json(path: Path) -> dict:
    # A UTF-8 BOM cannot be allowed to blind the safety check.
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _task_violations(task: dict) -> list[str]:
    violations: list[str] = []
    for platform in (None, "windows", "osx", "linux"):
        override = task.get(platform, {}) if platform else {}
        if not isinstance(override, dict):
            violations.append(f"malformed {platform} override")
            continue
        effective = {**task, **override}
        run_options = effective.get("runOptions", {})
        if not isinstance(run_options, dict):
            violations.append("malformed runOptions")
        elif run_options.get("runOn") == "folderOpen":
            violations.append(f"automatic folderOpen execution: {platform}")
        command = effective.get("command", "")
        args = effective.get("args", [])
        invocation = " ".join([str(command), *(str(a) for a in args)]) if isinstance(args, list) else f"{command} {args}"
        if INTERPRETER.search(str(command)) and EXECUTABLE_ASSET.search(invocation):
            violations.append(f"interpreter invoked on font-like asset: {platform}")
    return violations


def _valid_sfnt(data: bytes) -> bool:
    if len(data) < 12 or data[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1"):
        return False
    count, search_range, entry_selector, range_shift = struct.unpack_from(">HHHH", data, 4)
    if not (1 <= count <= 512) or 12 + 16 * count > len(data):
        return False
    power = 1 << (count.bit_length() - 1)
    if (search_range, entry_selector, range_shift) != (
        power * 16,
        power.bit_length() - 1,
        count * 16 - power * 16,
    ):
        return False
    tags: set[bytes] = set()
    for index in range(count):
        tag, _checksum, offset, length = struct.unpack_from(">4sIII", data, 12 + index * 16)
        if tag in tags or length == 0 or offset < 12 + 16 * count or offset > len(data) or length > len(data) - offset:
            return False
        if (tag == b"head" and length < 54) or (tag == b"cmap" and length < 4):
            return False
        tags.add(tag)
    return {b"head", b"cmap"} <= tags


class WorkspaceStartupSafetyTests(unittest.TestCase):
    def test_no_automatic_workspace_task(self) -> None:
        tasks = _json(ROOT / ".vscode" / "tasks.json")
        self.assertIsInstance(tasks.get("tasks", []), list)
        for task in tasks["tasks"]:
            self.assertIsInstance(task, dict)
            self.assertFalse(_task_violations(task), _task_violations(task))

    def test_workspace_settings_do_not_grant_automatic_execution(self) -> None:
        settings = _json(ROOT / ".vscode" / "settings.json")
        self.assertNotIn(settings.get("task.allowAutomaticTasks"), (True, "on"))
        self.assertNotIn("tasks", settings)

    def test_platform_specific_font_commands_and_open_triggers_are_detected(self) -> None:
        self.assertTrue(_task_violations({"command": "echo", "windows": {"command": "node", "args": ["public/fonts/evil.ttf"]}}))
        self.assertTrue(_task_violations({"command": "echo", "linux": {"runOptions": {"runOn": "folderOpen"}}}))
        self.assertTrue(_task_violations({"command": "nodejs", "args": ["public/fonts/evil.ttf"]}))
        self.assertTrue(_task_violations({"command": "python", "args": ["public/fonts/evil.ttf"]}))
        self.assertFalse(_task_violations({"command": "echo", "args": ["node public/fonts/example.ttf"]}))
        self.assertFalse(_task_violations({"label": "manual syntax check", "command": "python", "args": ["-m", "compileall", "src"]}))

    def test_real_ttf_assets_have_bounded_font_tables(self) -> None:
        for path in (ROOT / "public" / "fonts").glob("*.ttf"):
            self.assertTrue(_valid_sfnt(path.read_bytes()), f"not a real bounded sfnt font: {path.name}")

    def test_executable_text_with_true_prefix_is_not_a_font(self) -> None:
        self.assertFalse(_valid_sfnt(b'true;\nconsole.log("never execute this");'))
        fake_directory = b"\x00\x01\x00\x00" + struct.pack(">HHHH", 2, 32, 1, 0)
        fake_directory += struct.pack(">4sIII", b"head", 0, 44, 1)
        fake_directory += struct.pack(">4sIII", b"cmap", 0, 45, 1) + b"XY"
        self.assertFalse(_valid_sfnt(fake_directory))
