"""检查只读诊断、启动转发和U-Boot候选的关键约束，不访问板卡。"""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zlib

import beam_v14
import prepare_console


def script_image(text):
    data = text.encode('utf-8')
    data = struct.pack('>II', len(data), 0) + data
    values = [0x27051956, 0, 1, len(data), 0, 0, zlib.crc32(data) & 0xffffffff,
              5, 2, 6, 1, b'\0' * 32]
    values[1] = zlib.crc32(prepare_console.HEADER.pack(*values)) & 0xffffffff
    return prepare_console.HEADER.pack(*values) + data


class SetupTests(unittest.TestCase):
    def test_console_preserves_root_and_only_one_console(self):
        args = prepare_console.console_arguments(prepare_console.CMDLINE + ' console=ttyPS0,115200')
        self.assertIn('root=/dev/mmcblk0p2', args)
        self.assertIn('uio_pdrv_genirq.of_id=generic-uio', args)
        self.assertEqual(args.count('console='), 1)
        self.assertIn('console=tty0', args)
        self.assertNotIn('earlyprintk', args)
        self.assertIn('systemd.mask=serial-getty@ttyPS0.service', args)

    def test_unknown_root_or_shell_content_rejected(self):
        for text in ('root=/dev/sda1 rw', 'root=/dev/mmcblk0p2 foo=$(whoami)'):
            with self.assertRaises(ValueError): prepare_console.console_arguments(text)

    def test_script_branches_and_crcs_preserved(self):
        source = 'echo begin\nfor boot_target in ${boot_targets};\ndo\nif test x = x; then\nbootm ${imageub_addr};\nfi\ndone\n'
        raw = script_image(source)
        result, text = prepare_console.patch(raw, prepare_console.CMDLINE)
        self.assertEqual(prepare_console.decode(result)[1], text)
        self.assertEqual(text.count('\nfi\n'), 1)
        self.assertTrue(text.endswith(source[source.index('for boot_target'):]))
        self.assertEqual(prepare_console.decode(raw)[1], source)

    def test_corrupt_header_or_body_rejected(self):
        raw = script_image('echo begin\nfor boot_target in x; do\ndone\n')
        for offset in (4, 64, len(raw)-1):
            broken = bytearray(raw)
            broken[offset] ^= 1
            with self.assertRaises(ValueError): prepare_console.decode(bytes(broken))

    def test_existing_bootargs_script_rejected(self):
        raw = script_image('setenv bootargs old\nfor boot_target in x; do\ndone\n')
        with self.assertRaises(ValueError): prepare_console.patch(raw, prepare_console.CMDLINE)

    def test_ethernet_report_does_not_include_wifi_secret(self):
        config = ('auto eth0\niface eth0 inet static\n address 192.168.2.99\n netmask 255.255.255.0\n'
                  'iface wlan0 inet dhcp\n wpa-psk SECRET\n address 1.2.3.4\n')
        result = beam_v14.ethernet_config(config)
        self.assertIn('address 192.168.2.99', result)
        self.assertFalse(any('SECRET' in line or '1.2.3.4' in line for line in result))

    def test_missing_files_report_errors_without_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'missing'
            self.assertIn('read_error', beam_v14.read_text(path))
            self.assertIn('read_error', beam_v14.fingerprint(path))
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_check_collects_only_files_and_keeps_missing_admission_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'proc/sys/kernel/random').mkdir(parents=True)
            (root / 'proc/sys/kernel/random/boot_id').write_text('fresh-boot')
            (root / 'proc/consoles').write_text('ttyPS0 -W-\n')
            module = types.ModuleType('pynq_vision.beam_admission')
            module.inspect_bundle = lambda *a: {'version': 14, 'library_sha256': 'a' * 64}
            module.conflicting_owners = lambda *a: []
            before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.dict(sys.modules, {'pynq_vision.beam_admission': module}):
                data = beam_v14.collect(root, root)
            self.assertEqual(data['hardware_operations'], 0)
            self.assertEqual(data['boot_id'], 'fresh-boot')
            self.assertFalse(data['admission_exists'])
            self.assertEqual(before, {str(p.relative_to(root)): p.read_bytes()
                                     for p in root.rglob('*') if p.is_file()})

    def test_run_forwards_original_entry_and_admission_checks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'pynq_vision').mkdir()
            (root / 'pynq_vision/beam_launcher.py').write_text('')
            calls = []
            module = types.ModuleType('pynq_vision.beam_launcher')
            module.main = lambda args: calls.append(args)
            with patch.object(beam_v14, '__file__', str(root / 'beam_v14.py')):
                with patch.dict(sys.modules, {'pynq_vision.beam_launcher': module}):
                    self.assertEqual(beam_v14.main(['--run', '--frames', '10']), 0)
            self.assertEqual(len(calls), 1)
            self.assertIn('--run', calls[0])
            self.assertEqual(calls[0][calls[0].index('--uart')+1], '/dev/ttyPS0')
            self.assertEqual(calls[0][calls[0].index('--i2c-device')+1], '/dev/i2c-0')
            self.assertNotIn('--admission', calls[0])


if __name__ == '__main__':
    unittest.main()
