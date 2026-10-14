import unittest
from dataclasses import replace
import struct, zlib
from vera_ark.visual_trial_gate_strict import assess_abab_strict
from test_visual_trial_gate import packet


def png_with_dimensions(i, width, height):
    def chunk(kind, payload):
        body = kind + payload
        return struct.pack('>I', len(payload)) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)
    header = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    raw = (b'\x00' + bytes((i, 1, 2)) * width) * height
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


class StrictGateTests(unittest.TestCase):
    def test_all_same_dimensions_remain_candidate_only(self):
        result = assess_abab_strict(packet(), expected_dx_sign=1)
        self.assertEqual(result.status, 'FRAME_BOUND_CANDIDATE')
        self.assertFalse(result.verified_game_effect)

    def test_cross_frame_geometry_change_fails(self):
        trials = list(packet())
        trials[2] = replace(trials[2], before_png=png_with_dimensions(4, 3, 2))
        result = assess_abab_strict(tuple(trials), expected_dx_sign=1)
        self.assertEqual(result.status, 'INCONCLUSIVE')
        self.assertEqual(result.reason, 'FRAME_DIMENSION_MISMATCH')

    def test_invalid_png_fails_before_dimension_check(self):
        trials = list(packet())
        trials[2] = replace(trials[2], before_png=b'bad')
        self.assertEqual(assess_abab_strict(tuple(trials), expected_dx_sign=1).reason, 'INVALID_PNG')


if __name__ == '__main__':
    unittest.main()
