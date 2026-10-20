"""T103: offline bounded byte snapshot, synthetic evidence only."""
from __future__ import annotations

from hashlib import sha256
from unittest import TestCase

from vera_ark.offline_seqlock_byte_binding import (
    OfflineByteSnapshot, capture_offline_bytes_with_seqlock,
)


class OfflineSeqlockByteBindingT103(TestCase):
    def test_even_epoch_immutable_bytes_digest_and_size(self):
        source = bytearray(b"ark:1")
        calls = []
        def read_epoch():
            calls.append("epoch")
            return 12
        def capture():
            calls.append("capture")
            return source
        snap = capture_offline_bytes_with_seqlock(read_epoch, capture)
        self.assertEqual(calls, ["epoch", "capture", "epoch"])
        self.assertIs(type(snap), OfflineByteSnapshot)
        self.assertEqual((snap.epoch, snap.byte_count), (12, 5))
        self.assertEqual(snap.sha256_hex, sha256(b"ark:1").hexdigest())
        source[:] = b"changed"
        self.assertEqual(snap.data, b"ark:1")
        with self.assertRaises(AttributeError):
            snap.epoch = 14

    def test_bytes_source_identity_is_safe(self):
        snap = capture_offline_bytes_with_seqlock(lambda: 0, lambda: b"abc")
        self.assertEqual(snap.data, b"abc")

    def test_odd_start_prevents_capture(self):
        called = []
        with self.assertRaisesRegex(RuntimeError, "writer active"):
            capture_offline_bytes_with_seqlock(lambda: 3, lambda: called.append(1))
        self.assertEqual(called, [])

    def test_changed_epoch_discards_result(self):
        epochs = iter((2, 4))
        with self.assertRaisesRegex(RuntimeError, "epoch changed"):
            capture_offline_bytes_with_seqlock(lambda: next(epochs), lambda: b"abc")

    def test_invalid_final_epoch_discards_result(self):
        epochs = iter((2, True))
        with self.assertRaisesRegex(ValueError, "uint64"):
            capture_offline_bytes_with_seqlock(lambda: next(epochs), lambda: b"abc")

    def test_reader_failure_discards_result(self):
        epochs = iter((2,))
        with self.assertRaisesRegex(RuntimeError, "epoch read failed"):
            capture_offline_bytes_with_seqlock(lambda: next(epochs), lambda: b"abc")

    def test_type_fail_closed(self):
        for bad in ("abc", None, [1, 2], memoryview(b"abc"), 3):
            with self.subTest(bad=type(bad)), self.assertRaisesRegex(ValueError, "exact bytes"):
                capture_offline_bytes_with_seqlock(lambda: 2, lambda: bad)

    def test_oversize_and_exact_boundary(self):
        with self.assertRaisesRegex(ValueError, "exceeds"):
            capture_offline_bytes_with_seqlock(lambda: 2, lambda: bytearray(5), max_bytes=4)
        snap = capture_offline_bytes_with_seqlock(lambda: 2, lambda: bytearray(4), max_bytes=4)
        self.assertEqual(snap.byte_count, 4)

    def test_max_bytes_rejects_boolean_and_invalid(self):
        for bad in (True, False, 0, -1, 1.5, "10", 16*1024*1024+1):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "max_bytes"):
                capture_offline_bytes_with_seqlock(lambda: 2, lambda: b"", max_bytes=bad)

    def test_frozen_epoch_is_not_authentication(self):
        source = bytearray(b"abc")
        def uncooperative_capture():
            source[0] = ord("x")
            return source
        snap = capture_offline_bytes_with_seqlock(lambda: 2, uncooperative_capture)
        self.assertEqual(snap.data, b"xbc")
        self.assertEqual(snap.epoch, 2)

    def test_no_retries_on_bad_capture(self):
        count = []
        def bad():
            count.append(1)
            raise LookupError("capture failed")
        with self.assertRaisesRegex(LookupError, "capture failed"):
            capture_offline_bytes_with_seqlock(lambda: 2, bad)
        self.assertEqual(count, [1])
