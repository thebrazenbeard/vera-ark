import unittest
from dataclasses import replace
from hashlib import sha256
import struct, zlib
from vera_ark.visual_trial_gate import Observation, assess_abab


def png(i):
    def chunk(k, d):
        body = k + d
        return struct.pack('>I', len(d)) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)
    header = struct.pack('>IIBBBBB', 2, 2, 8, 2, 0, 0, 0)
    raw = (b'\x00' + bytes((i, 1, 2)) * 2) * 2
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


def packet():
    return tuple(Observation(
        'IDLE' if i % 2 == 0 else 'ACTION', 'LIVE_CAPTURE', 'beach', 'chiaki',
        0 if i % 2 == 0 else -.36, 10000 + 2000*i, 10050 + 2000*i,
        10290 + 2000*i, 10400 + 2000*i, 240, True, True, 190,
        0.1 if i % 2 == 0 else 20, 0, png(i*2), png(i*2+1),
    ) for i in range(4))


class GateTests(unittest.TestCase):
    def test_only_frame_bound_candidate(self):
        a = assess_abab(packet(), expected_dx_sign=1)
        self.assertEqual(a.status, 'FRAME_BOUND_CANDIDATE')
        self.assertFalse(a.verified_game_effect)
        self.assertFalse(a.independent_reviewed)
        self.assertFalse(a.automatic_execution_permitted)
        self.assertEqual(len(a.evidence_digest), 64)

    def test_fabricated_capture_label_is_not_attestation(self):
        p = list(packet()); p[1] = replace(p[1], source='SYNTHETIC')
        self.assertEqual(assess_abab(tuple(p), expected_dx_sign=1).status, 'SYNTHETIC_OR_UNKNOWN')

    def test_corrupt_png_and_duplicate_frame(self):
        p = list(packet()); p[2] = replace(p[2], before_png=b'bad')
        self.assertEqual(assess_abab(tuple(p), expected_dx_sign=1).reason, 'INVALID_PNG')
        p = list(packet()); p[2] = replace(p[2], before_png=p[0].before_png)
        self.assertEqual(assess_abab(tuple(p), expected_dx_sign=1).reason, 'DUPLICATE_FRAME')

    def test_invalid_release_or_timing(self):
        p = list(packet()); p[1] = replace(p[1], neutral_released=False)
        self.assertEqual(assess_abab(tuple(p), expected_dx_sign=1).reason, 'INVALID_CONTROL_OR_REVIEW')
        p = list(packet()); p[1] = replace(p[1], release_ms=p[1].start_ms+100)
        self.assertEqual(assess_abab(tuple(p), expected_dx_sign=1).reason, 'INVALID_TIMING')

    def test_no_single_action_reward(self):
        p = list(packet()); p[3] = replace(p[3], dx=0)
        self.assertEqual(assess_abab(tuple(p), expected_dx_sign=1).status, 'INCONCLUSIVE')

    def test_idle_drift_or_wrong_direction(self):
        p = list(packet()); p[2] = replace(p[2], dx=15)
        self.assertEqual(assess_abab(tuple(p), expected_dx_sign=1).reason, 'UNSTABLE_IDLE')
        self.assertEqual(assess_abab(packet(), expected_dx_sign=-1).reason, 'WEAK_OR_INCONSISTENT_ACTION')

    def test_changed_scene_and_action(self):
        p = list(packet()); p[2] = replace(p[2], scene='other')
        self.assertEqual(assess_abab(tuple(p), expected_dx_sign=1).reason, 'SCENE_OR_WINDOW_MISMATCH')
        p = list(packet()); p[3] = replace(p[3], stick_x=-.28)
        self.assertEqual(assess_abab(tuple(p), expected_dx_sign=1).reason, 'ACTION_MISMATCH')

    def test_invalid_numbers_and_packet(self):
        p = list(packet()); p[1] = replace(p[1], dx=float('nan'))
        self.assertEqual(assess_abab(tuple(p), expected_dx_sign=1).reason, 'INVALID_MEASUREMENTS')
        self.assertEqual(assess_abab(packet()[:3], expected_dx_sign=1).reason, 'INVALID_PACKET')
        self.assertEqual(assess_abab(packet(), expected_dx_sign=True).reason, 'INVALID_DIRECTION')


if __name__ == '__main__':
    unittest.main()
