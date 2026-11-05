"""Synthetic local custody regression: no simultaneous owners of one JSONL ledger."""

from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from vera_ark.storage import AppendOnlyJsonl, LedgerBusyError, LedgerCorruptionError


class SingleWriterLeaseTests(unittest.TestCase):
    @unittest.skipUnless(hasattr(os, "fork"), "requires POSIX fork")
    def test_child_does_not_inherit_locked_thread_mutex(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            owner = AppendOnlyJsonl(path)
            owner._lock.acquire()
            child_pid = os.fork()
            if child_pid == 0:
                try:
                    owner.append("INHERITED_LOCK", {})
                except LedgerBusyError:
                    os._exit(0)
                except BaseException:
                    os._exit(9)
                os._exit(8)
            try:
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    done, status = os.waitpid(child_pid, os.WNOHANG)
                    if done:
                        self.assertEqual(os.waitstatus_to_exitcode(status), 0)
                        break
                    time.sleep(0.02)
                else:
                    os.kill(child_pid, 9)
                    os.waitpid(child_pid, 0)
                    self.fail("fork child blocked on inherited parent thread mutex")
            finally:
                owner._lock.release()
                owner.close()

    def test_ambiguous_post_commit_check_poison_prevents_duplicate_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            owner = AppendOnlyJsonl(path)
            try:
                with patch.object(owner, "_assert_current_writer", side_effect=[
                    None, LedgerBusyError("synthetic pathname move after durable write")
                ]):
                    with self.assertRaises(LedgerBusyError):
                        owner.append("COMMITTED_AMBIGUOUS", {})
                self.assertEqual(owner._sequence, 1)
                with self.assertRaises(LedgerBusyError):
                    owner.append("MUST_NOT_RETRY", {})
            finally:
                owner.close()
            recheck = AppendOnlyJsonl(path)
            try:
                self.assertEqual([r["kind"] for r in recheck.read_all()], ["COMMITTED_AMBIGUOUS"])
                self.assertEqual(recheck.append("NEW_OWNER", {})["sequence"], 2)
            finally:
                recheck.close()

    @unittest.skipUnless(hasattr(os, "fork"), "requires POSIX fork")
    def test_inherited_writer_after_fork_cannot_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            owner = AppendOnlyJsonl(path)
            try:
                child_pid = os.fork()
                if child_pid == 0:
                    try:
                        owner.append("INHERITED_CHILD", {})
                    except LedgerBusyError:
                        os._exit(0)
                    except BaseException:
                        os._exit(9)
                    os._exit(8)
                _, status = os.waitpid(child_pid, 0)
                self.assertEqual(os.waitstatus_to_exitcode(status), 0)
                self.assertEqual(owner.append("REAL_OWNER", {})["sequence"], 1)
            finally:
                owner.close()
            recheck = AppendOnlyJsonl(path)
            try:
                self.assertEqual([r["kind"] for r in recheck.read_all()], ["REAL_OWNER"])
            finally:
                recheck.close()

    @unittest.skipUnless(os.name == "posix", "POSIX open-sidecar unlink semantics")
    def test_unlinked_sidecar_cannot_make_second_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            owner = AppendOnlyJsonl(path)
            try:
                path.with_name(path.name + ".writer.lock").unlink()
                with self.assertRaises(LedgerBusyError):
                    AppendOnlyJsonl(path)
                with self.assertRaises(LedgerBusyError):
                    owner.append("UNBOUND", {})
            finally:
                owner.close()
            self.assertEqual(path.read_text(encoding="utf-8"), "")

    @unittest.skipUnless(hasattr(os, "symlink"), "OS symlink support required")
    def test_symlinked_data_file_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            logs = base / "logs"
            logs.mkdir()
            outside = base / "outside.jsonl"
            outside.write_text("", encoding="utf-8")
            path = logs / "events.jsonl"
            try:
                path.symlink_to(outside)
            except OSError:
                self.skipTest("symlink creation unavailable")
            with self.assertRaises(LedgerBusyError):
                AppendOnlyJsonl(path)
            self.assertEqual(outside.read_text(encoding="utf-8"), "")

    @unittest.skipUnless(os.name == "posix", "rename of held data file is OS-specific")
    def test_data_path_swapped_after_init_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            path = base / "events.jsonl"
            moved = base / "moved.jsonl"
            outside = base / "outside.jsonl"
            outside.write_text("", encoding="utf-8")
            owner = AppendOnlyJsonl(path)
            try:
                self.assertEqual(owner.append("FIRST", {})["sequence"], 1)
                path.rename(moved)
                path.symlink_to(outside)
                with self.assertRaises(LedgerBusyError):
                    owner.append("DIVERTED", {})
                self.assertEqual(outside.read_text(encoding="utf-8"), "")
            finally:
                owner.close()

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
