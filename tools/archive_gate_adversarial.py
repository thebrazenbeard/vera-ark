"""Adversarial tests of the inert archive static gate; no repo imports."""
import unittest
import sys
from pathlib import Path
from archive_static_gate import unpack_archive, evaluate

BASE = Path(__file__).resolve().parent
CANDIDATE = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "candidate.zip"
FILES, _ = unpack_archive(CANDIDATE)
sys.argv = [sys.argv[0]]

class ArchiveGateAdversarial(unittest.TestCase):
    def test_nested_folder_open(self):
        files = dict(FILES)
        files["sub/.vscode/tasks.json"] = b'{"tasks":[{"runOptions":{"runOn":"folderOpen"}}]}'
        self.assertTrue(evaluate(files, expect_pins=True)["auto_paths"])
    def test_modified_pinned_font(self):
        files = dict(FILES)
        name = "public/fonts/fa-brands-400.woff2"
        files[name] = files[name] + b"x"
        self.assertIn("font blob differs: fa-brands-400.woff2", evaluate(files, expect_pins=True)["problems"])
    def test_extra_disguised_font(self):
        files = dict(FILES)
        files["public/fonts/fa-solid-500.woff2"] = b"not a font"
        self.assertIn("disguised font path present", evaluate(files, expect_pins=True)["problems"])
    def test_escaped_json_key(self):
        files = dict(FILES)
        files["sub/.vscode/tasks.json"] = br'{"tasks":[{"runOptions":{"run\u004fn":"folderOpen"}}]}'
        self.assertTrue(evaluate(files, expect_pins=True)["auto_paths"])

if __name__ == "__main__":
    unittest.main(verbosity=2)