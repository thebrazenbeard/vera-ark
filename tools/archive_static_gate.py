"""Inert archive-only security gate. Never imports or executes repository source."""
import ast
import hashlib
import json
import re
import stat
import struct
import sys
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
AUTO = re.compile(rb'["\x27]runOn["\x27]\s*:\s*["\x27]folderOpen["\x27]', re.I)
HEADER = struct.Struct(">4sIIHHIIHHIIIII")

def unpack_archive(path):
    problems = []
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            problems.append("bad ZIP CRC: " + bad)
        entries = {}
        for info in archive.infolist():
            parts = Path(info.filename).parts
            if not parts or ".." in parts or info.filename.startswith("/"):
                problems.append("unsafe archive path")
                continue
            if info.is_dir():
                continue
            rel = "/".join(parts[1:])
            if not rel or rel.casefold() in (x.casefold() for x in entries):
                problems.append("duplicate/empty path: " + rel)
                continue
            if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
                problems.append("symlink entry: " + rel)
            entries[rel] = archive.read(info)
    return entries, problems
def pins_from_source(data):
    tree = ast.parse(data.decode("utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == "PINNED_BLOBS" for t in node.targets):
                return ast.literal_eval(node.value)
    raise ValueError("no static font pins")

def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def contains_folder_open(data):
    try:
        node = json.loads(data)
    except (ValueError, UnicodeError):
        return bool(AUTO.search(data)) or (b"folderOpen" in data and b"\\u" in data)
    stack = [node]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if item.get("runOn") == "folderOpen":
                return True
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return False

def evaluate(files, *, expect_pins):
    problems = []
    config = [p for p in files if ("/.vscode/" in "/" + p or p.startswith(".vscode/") or p.endswith(".code-workspace")) and p.endswith((".json", ".code-workspace"))]
    autorun = [p for p in config if contains_folder_open(files[p])]
    if autorun:
        problems.append("folder-open task in " + ",".join(autorun))
    settings = files.get(".vscode/settings.json", b"{}")
    try:
        if json.loads(settings).get("task.allowAutomaticTasks") is not False:
            problems.append("automatic tasks not disabled")
    except (ValueError, UnicodeError):
        problems.append("settings JSON invalid")
    if "public/fonts/fa-solid-500.woff2" in files:
        problems.append("disguised font path present")
    fonts = {p.removeprefix("public/fonts/"): data for p, data in files.items() if p.startswith("public/fonts/")}
    for name, data in fonts.items():
        if name.endswith(".woff2") and (len(data) < HEADER.size or data[:4] != b"wOF2"):
            problems.append("non-WOFF2 bytes: " + name)
    if expect_pins:
        pins = pins_from_source(files["tests/test_repository_font_pins.py"])
        if set(fonts) != set(pins):
            problems.append("font set differs from pins")
        for name in sorted(set(fonts) & set(pins)):
            if git_blob(fonts[name]) != pins[name]:
                problems.append("font blob differs: " + name)
    return {"problems": problems, "auto_paths": autorun, "font_count": len(fonts), "config_count": len(config)}
def main():
    base_archive = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "main.zip"
    candidate_archive = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE / "candidate.zip"
    old, old_zip_errors = unpack_archive(base_archive)
    new, new_zip_errors = unpack_archive(candidate_archive)
    baseline = evaluate(old, expect_pins=False)
    candidate = evaluate(new, expect_pins=True)
    outcome = {
        "base_ref": "7e4b8469c6c4d5918556e3f80a54f9335238a0c3",
        "candidate_ref": "37a2fdeb09a634376a76f208628c2a3b3fa83f58",
        "baseline": baseline,
        "candidate": candidate,
        "baseline_archive_errors": old_zip_errors,
        "candidate_archive_errors": new_zip_errors,
        "negative_control_detected": bool(baseline["auto_paths"]) and "disguised font path present" in baseline["problems"],
        "candidate_static_pass": not new_zip_errors and not candidate["problems"],
        "limits": ["No repository code executed", "Header check is not full WOFF2 validation", "Self-declared pins do not prove trusted origin", "No endpoint/credential/gameplay qualification"]
    }
    if len(sys.argv) > 3:
        Path(sys.argv[3]).write_text(json.dumps(outcome, indent=2), encoding="utf-8")
    print(json.dumps(outcome, indent=2))
    return 0 if outcome["negative_control_detected"] and outcome["candidate_static_pass"] else 1

if __name__ == "__main__":
    sys.exit(main())