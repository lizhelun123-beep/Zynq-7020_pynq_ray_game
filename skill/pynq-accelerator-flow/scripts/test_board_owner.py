"""Fake PYNQ tests for reuse/failure ownership;no actual Overlay/device import."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assets/scalar-demo/python'))
from pynq_scalar_demo.bundle import VLNV


class OwnerTests(unittest.TestCase):
    def setUp(self):
        self.loads, self.constructs = [], []
        loads, constructs = self.loads, self.constructs
        class FakeIP:
            def __init__(inner, description):
                constructs.append(description)
            def read(inner, offset):
                return 4 if offset == 0 else 0
            def write(inner, offset, value):
                pass
        def overlay(path):
            loads.append(path)
            if path == 'bad.bit':
                raise OSError('partial download cannot be excluded')
            driver = self.module.AddBiasDriver(dict(type=VLNV, phys_addr=0x40000000, addr_range=4096))
            return types.SimpleNamespace(add_bias_0=driver)
        fake = types.ModuleType('pynq')
        fake.DefaultIP, fake.Overlay = FakeIP, overlay
        path = Path(__file__).resolve().parents[1] / 'assets/scalar-demo/python/pynq_scalar_demo/board.py'
        spec = importlib.util.spec_from_file_location('pynq_scalar_demo._board_under_test', path)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'pynq': fake}):
            spec.loader.exec_module(self.module)

    def test_repeat_load_reuses_owner_and_different_bundle_rejected(self):
        owner = self.module.open_board('one.bit', 'add_bias_0', 'hash1')
        self.assertIs(owner, self.module.open_board('one.bit', 'add_bias_0', 'hash1'))
        with self.assertRaises(RuntimeError):
            self.module.open_board('two.bit', 'add_bias_0', 'hash2')
        self.assertEqual(len(self.loads), 1)
        owner.session.close()
        self.assertIsNot(owner, self.module.open_board('two.bit', 'add_bias_0', 'hash2'))
        self.assertEqual(len(self.loads), 2)

    def test_partial_download_failure_blocks_retry(self):
        with self.assertRaises(OSError):
            self.module.open_board('bad.bit', 'add_bias_0', 'hash1')
        with self.assertRaises(RuntimeError):
            self.module.open_board('one.bit', 'add_bias_0', 'hash1')
        self.assertEqual(len(self.loads), 1)

    def test_description_rejected_before_defaultip_constructor(self):
        with self.assertRaises(ValueError):
            self.module.AddBiasDriver(dict(type=VLNV, phys_addr=0x40000000, addr_range=16))
        self.assertEqual(self.constructs, [])


if __name__ == '__main__':
    unittest.main()
