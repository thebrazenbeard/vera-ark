"""Static guard against executable payloads disguised as repository assets.

This test reads bytes and configuration only; it never executes project tasks.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RepositoryAssetIntegrityTests(unittest.TestCase):
    def test_woff2_assets_have_woff2_signature(self):
        fonts = sorted((ROOT / "public" / "fonts").glob("*.woff2"))
        self.assertTrue(fonts, "Expected at least one WOFF2 asset")
        for font in fonts:
            with self.subTest(path=str(font.relative_to(ROOT))):
                with font.open("rb") as handle:
                    self.assertEqual(handle.read(4), b"wOF2")

    def test_no_automatic_folder_open_tasks(self):
        path = ROOT / ".vscode" / "tasks.json"
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        for task in data.get("tasks", []):
            with self.subTest(task=task.get("label", "<unnamed>")):
                self.assertNotEqual(
                    task.get("runOptions", {}).get("runOn"), "folderOpen"
                )

    def test_automatic_tasks_disabled(self):
        path = ROOT / ".vscode" / "settings.json"
        settings = json.loads(path.read_text(encoding="utf-8"))
        self.assertIs(settings.get("task.allowAutomaticTasks"), False)


if __name__ == "__main__":
    unittest.main()
