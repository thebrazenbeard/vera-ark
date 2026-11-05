"""Synthetic local custody regression: no simultaneous owners of one JSONL ledger."""

from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

from vera_ark.storage import AppendOnlyJsonl, LedgerBusyError, LedgerCorruptionError


class SingleWriterLeaseTests(unittest.TestCase):
    def test_two_instances_fail_closed_then_reopen_preserves_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            first = AppendOnlyJsonl(path)
            try:
                with self.assertRaises(LedgerBusyError):
                    AppendOnlyJsonl(path)
                self.assertEqual(first.append("ONE", {})["sequence"], 1)
            finally:
                first.close()

            second = AppendOnlyJsonl(path)
            try:
                self.assertEqual(second.append("TWO", {})["sequence"], 2)
            finally:
                second.close()

            reopen = AppendOnlyJsonl(path)
            try:
                self.assertEqual([r["sequence"] for r in reopen.read_all()], [1, 2])
            finally:
                reopen.close()

    def test_child_process_cannot_take_active_writer_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            owner = AppendOnlyJsonl(path)
            try:
                child = """
from pathlib import Path
import sys
from vera_ark.storage import AppendOnlyJsonl, LedgerBusyError
try:
    writer = AppendOnlyJsonl(Path(sys.argv[1]))
except LedgerBusyError:
    sys.exit(0)
else:
    writer.close()
    sys.exit(8)
"""
                env = os.environ.copy()
                package_root = Path(__file__).resolve().parents[1] / "src"
                env["PYTHONPATH"] = str(package_root) + os.pathsep + env.get("PYTHONPATH", "")
                result = subprocess.run(
                    [sys.executable, "-c", child, str(path)],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    env=env,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(owner.append("ONE", {})["sequence"], 1)
            finally:
                owner.close()

    def test_closed_lease_cannot_append_and_existing_corruption_never_repairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            writer = AppendOnlyJsonl(path)
            self.assertEqual(writer.append("ONE", {})["sequence"], 1)
            writer.close()
            with self.assertRaises(LedgerBusyError):
                writer.append("TWO", {})

            # Offline tamper only against this test's fresh temporary ledger.
            row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")
            with self.assertRaises(LedgerCorruptionError):
                AppendOnlyJsonl(path)


if __name__ == "__main__":
    unittest.main()
