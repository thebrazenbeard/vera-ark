"""Static ARK repository asset checks; no workspace tasks or assets are executed."""
import json
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_WOFF2_HEADER = struct.Struct(">4sIIHHIIHHIIIII")
_ALLOWED_FLAVORS = {0x00010000, 0x4F54544F, 0x74746366}


def coherent_woff2_header(data: bytes) -> bool:
    """Reject magic-prefix spoofs; this is not complete font validation."""
    if type(data) is not bytes or len(data) < _WOFF2_HEADER.size:
        return False
    (magic, flavor, declared_length, num_tables, reserved, sfnt_size,
     compressed_size, major, minor, meta_offset, meta_length,
     meta_orig_length, priv_offset, priv_length) = _WOFF2_HEADER.unpack_from(data)
    if (magic != b"wOF2" or flavor not in _ALLOWED_FLAVORS or
        declared_length != len(data) or not 1 <= num_tables <= 4095 or
        reserved != 0 or sfnt_size < 12 or
        not 1 <= compressed_size <= len(data) - _WOFF2_HEADER.size):
        return False
    if meta_offset == 0:
        if meta_length or meta_orig_length:
            return False
    elif (meta_length == 0 or meta_orig_length == 0 or
          meta_offset < _WOFF2_HEADER.size or meta_offset + meta_length > len(data)):
        return False
    if priv_offset == 0:
        if priv_length:
            return False
    elif (priv_length == 0 or priv_offset < _WOFF2_HEADER.size or
          priv_offset + priv_length > len(data)):
        return False
    if meta_offset and priv_offset:
        if max(meta_offset, priv_offset) < min(meta_offset + meta_length,
                                               priv_offset + priv_length):
            return False
    return True


def contains_folder_open(node):
    if isinstance(node, dict):
        if node.get("runOn") == "folderOpen":
            return True
        return any(contains_folder_open(value) for value in node.values())
    if isinstance(node, list):
        return any(contains_folder_open(value) for value in node)
    return False


class RepositoryAssetIntegrityTests(unittest.TestCase):
    def test_woff2_assets_have_coherent_headers(self):
        fonts = sorted((ROOT / "public" / "fonts").glob("*.woff2"))
        self.assertTrue(fonts, "Expected at least one WOFF2 asset")
        for font in fonts:
            with self.subTest(path=str(font.relative_to(ROOT))):
                self.assertTrue(coherent_woff2_header(font.read_bytes()))

    def test_magic_prefix_script_spoof_is_rejected(self):
        self.assertFalse(coherent_woff2_header(b"wOF2=0; /* inert fixture */"))

    def test_woff2_declared_length_mismatch_is_rejected(self):
        data = _WOFF2_HEADER.pack(b"wOF2", 0x00010000, 49, 1, 0, 64, 1,
                                  1, 0, 0, 0, 0, 0, 0) + b"x" * 8
        self.assertFalse(coherent_woff2_header(data))

    def test_out_of_bounds_metadata_is_rejected(self):
        data = _WOFF2_HEADER.pack(b"wOF2", 0x00010000, 49, 1, 0, 64, 1,
                                  1, 0, 48, 3, 3, 0, 0) + b"x"
        self.assertFalse(coherent_woff2_header(data))

    def test_out_of_bounds_private_block_is_rejected(self):
        data = _WOFF2_HEADER.pack(b"wOF2", 0x00010000, 49, 1, 0, 64, 1,
                                  1, 0, 0, 0, 0, 48, 3) + b"x"
        self.assertFalse(coherent_woff2_header(data))

    def test_no_automatic_folder_open_tasks_in_vscode_config(self):
        paths = [ROOT / ".vscode" / "tasks.json",
                 ROOT / ".vscode" / "settings.json"]
        paths.extend(sorted(ROOT.glob("*.code-workspace")))
        for path in paths:
            if path.exists():
                with self.subTest(path=str(path.relative_to(ROOT))):
                    self.assertFalse(path.is_symlink())
                    data = json.loads(path.read_text(encoding="utf-8"))
                    self.assertFalse(contains_folder_open(data))

    def test_nested_folder_open_declaration_is_rejected(self):
        self.assertTrue(contains_folder_open({"tasks": [{"runOptions": {"runOn": "folderOpen"}}]}))
        self.assertFalse(contains_folder_open({"tasks": [{"runOptions": {"runOn": "manual"}}]}))

    def test_overlapping_metadata_private_blocks_are_rejected(self):
        data = _WOFF2_HEADER.pack(b"wOF2", 0x00010000, 80, 1, 0, 64, 1,
                                  1, 0, 52, 8, 8, 55, 8) + b"x" * 32
        self.assertFalse(coherent_woff2_header(data))

    def test_automatic_tasks_explicitly_disabled(self):
        path = ROOT / ".vscode" / "settings.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIs(data.get("task.allowAutomaticTasks"), False)
        self.assertEqual(data.get("editor.defaultFormatter"), "esbenp.prettier-vscode")


if __name__ == "__main__":
    unittest.main()
