"""Exact-byte Git blob pins for reviewed ARK font assets; no asset execution."""
import hashlib
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# GitHub readback: security/quarantine-vscode-autorun-20261016@62c455972d8d30f7e3d22ca97c24c5ec45410749
PINNED_BLOBS = {
    "README.md": "1e4f9ba13fffd107aaafb1d1196819f5162c871f",
    "fa-brands-400.eot": "a1bc094ab14d8c7d84d8c59aa511de9e69440d0a",
    "fa-brands-400.svg": "46ad237a6191a5cd8518e0bb24379a1a111249c9",
    "fa-brands-400.ttf": "948a2a6cc76a4d7cb692d0d08e352f126ec48a9d",
    "fa-brands-400.woff": "2a89d521e3fadb6ad3bc1738830a2c039bc57272",
    "fa-brands-400.woff2": "141a90a9e0a4b5a794557efa098a5c52320fb226",
    "fa-regular-400.eot": "38cf2517a4da71a05f8e83723cdffce45ebc3319",
    "fa-regular-400.svg": "48634a9ab4743ba0fff2870a383792030877671d",
    "fa-regular-400.ttf": "abe99e20c38a23e95295917d6a5cdb49a8489eb8",
    "fa-regular-400.woff": "24de566a5c97289a86ce0c238a195da0d3251263",
    "fa-regular-400.woff2": "7e0118e526eb53511cb57e7cfaf515784fee4345",
    "fa-solid-900.eot": "d3b77c223afc9a0a1af914936219da2b001a010f",
    "fa-solid-900.svg": "7742838b4481a6d678c7fb51417e84da69707ec2",
    "fa-solid-900.ttf": "5b979039ab28aaae305074541fe39258753ba624",
    "fa-solid-900.woff": "beec79178427adba9f767e1c1d2bd205044a85da",
    "fa-solid-900.woff2": "978a681a10ff0478581436eaca5c5695c97445d4",
}


def git_blob_oid(data: bytes) -> str:
    if type(data) is not bytes:
        raise TypeError("expected bytes")
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def inspect_font_tree(directory: Path, expected: dict[str, str]) -> list[str]:
    """Fail closed on missing, extra, symlinked, or modified entries."""
    if not directory.is_dir() or directory.is_symlink():
        return ["font directory missing or symlinked"]
    violations = []
    actual = {entry.name for entry in directory.iterdir()}
    for name in sorted(actual - expected.keys()):
        violations.append(f"unreviewed entry: {name}")
    for name in sorted(expected.keys() - actual):
        violations.append(f"missing pinned entry: {name}")
    for name in sorted(actual & expected.keys()):
        path = directory / name
        if not path.is_file() or path.is_symlink():
            violations.append(f"not an ordinary file: {name}")
            continue
        if git_blob_oid(path.read_bytes()) != expected[name]:
            violations.append(f"blob mismatch: {name}")
    return violations


class RepositoryFontPinTests(unittest.TestCase):
    def test_security_branch_font_tree_matches_pins(self):
        self.assertEqual(inspect_font_tree(ROOT / "public" / "fonts", PINNED_BLOBS), [])

    def test_same_length_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            original, replacement = b"wOF2-ordinary-bytes", b"wOF2-script--bytes!"
            self.assertEqual(len(original), len(replacement))
            (root / "asset.woff2").write_bytes(original)
            pin = {"asset.woff2": git_blob_oid(original)}
            self.assertEqual(inspect_font_tree(root, pin), [])
            (root / "asset.woff2").write_bytes(replacement)
            self.assertIn("blob mismatch: asset.woff2", inspect_font_tree(root, pin))

    def test_added_disguised_font_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "allowed.woff2").write_bytes(b"wOF2-good")
            pin = {"allowed.woff2": git_blob_oid(b"wOF2-good")}
            (root / "fa-solid-500.woff2").write_bytes(b"inert fixture")
            self.assertIn("unreviewed entry: fa-solid-500.woff2", inspect_font_tree(root, pin))

    def test_missing_asset_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIn("missing pinned entry: asset.ttf", inspect_font_tree(Path(d), {"asset.ttf": "0" * 40}))

    def test_unexpected_non_font_file_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "payload.js").write_bytes(b"inert")
            self.assertIn("unreviewed entry: payload.js", inspect_font_tree(root, {}))


if __name__ == "__main__":
    unittest.main()
