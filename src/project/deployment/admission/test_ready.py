"""用进程、寄存器及保护文件夹具验证准入边界，不访问真实硬件。"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import ready

spec = importlib.util.spec_from_file_location('pynq_vision._gate_test', Path(__file__).resolve().parents[2] / 'pynq_vision/beam_admission.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

COMMAND = '/usr/bin/python3 /usr/local/bin/start_pl_server.py'
MAPPING = 'b6f5b000-b6f5c000 rw-s f8f00000 00:06 1049 /dev/mem'
UID = 'Uid:\t0\t0\t0\t0'
CGROUP = '1:name=systemd:/system.slice/pl_server.service'


class AdmissionTests(unittest.TestCase):
    def test_exact_platform_ps_mapping_can_be_classified(self):
        self.assertTrue(gate.platform_server_shape(COMMAND, UID, '/usr/bin/python3.6', CGROUP, [], MAPPING))

    def test_platform_name_does_not_allow_pl_or_cma_mapping(self):
        for mapping in (MAPPING.replace('f8f00000', '43000000'),
                        MAPPING + '\n' + MAPPING.replace('/dev/mem', '/dev/xlnk'),
                        MAPPING.replace('b6f5c000', 'b6f5d000'),
                        MAPPING + ' (deleted)'):
            with self.subTest(mapping=mapping):
                self.assertFalse(gate.platform_server_shape(COMMAND, UID, '/usr/bin/python3.6', CGROUP, [], mapping))

    def test_platform_open_device_fd_is_still_conflict(self):
        for path in ('/dev/mem', '/dev/xlnk', '/dev/uio0', '/dev/fb0'):
            self.assertFalse(gate.platform_server_shape(COMMAND, UID, '/usr/bin/python3.6', CGROUP, [path], MAPPING))

    def test_platform_identity_is_required(self):
        for command, uid, executable, cgroup in (
            (COMMAND + ' extra', UID, '/usr/bin/python3.6', CGROUP),
            (COMMAND, 'Uid: 1000 1000 1000 1000', '/usr/bin/python3.6', CGROUP),
            (COMMAND, UID, '/usr/bin/custom-python', CGROUP),
            (COMMAND, UID, '/usr/bin/python3.6', '1:name=systemd:/user.slice')):
            self.assertFalse(gate.platform_server_shape(command, uid, executable, cgroup, [], MAPPING))

    def test_source_hash_and_start_time_are_not_bypassed(self):
        with tempfile.TemporaryDirectory(prefix='admission_test_') as folder:
            root = Path(folder)
            process = root / 'proc/42'
            process.mkdir(parents=True)
            (process / 'cmdline').write_bytes(COMMAND.replace(' ', '\0').encode())
            (process / 'status').write_text(UID)
            (process / 'cgroup').write_text(CGROUP)
            value = '42 (python3) ' + ' '.join(['S'] + ['0'] * 18 + ['1234'])
            (process / 'stat').write_text(value)
            (root / 'trusted.py').write_bytes(b'trusted-source')
            expected = {'trusted.py': hashlib.sha256(b'trusted-source').hexdigest()}
            with patch.object(gate, 'PL_SERVER_SOURCES', expected), patch.object(gate.os, 'readlink', return_value='/usr/bin/python3.6'):
                self.assertTrue(gate.trusted_platform_server(process, [], MAPPING, value, root))
                (root / 'trusted.py').write_bytes(b'changed-source')
                self.assertFalse(gate.trusted_platform_server(process, [], MAPPING, value, root))
                (root / 'trusted.py').write_bytes(b'trusted-source')
                (process / 'stat').write_text(value.replace('1234', '9999'))
                self.assertFalse(gate.trusted_platform_server(process, [], MAPPING, value, root))

    def test_missing_receipt_still_rejected_after_platform_check(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(gate, 'platform_inputs', return_value='fresh-boot'):
            with self.assertRaises(OSError): gate.preflight({}, Path(folder) / 'absent', '/dev/i2c-0')

    def test_valid_receipt_identity_is_still_required(self):
        record = {'bit_sha256': 'b'*64, 'hwh_sha256': 'h'*64, 'ps_reference_hz': 33333333}
        receipt = {'schema': 'beam-pynq-mmio-admission-v1', 'boot_id': 'fresh-boot',
                   **record, 'evidence_path': '/run/evidence', 'evidence_sha256': 'e'*64}
        self.assertEqual(gate.validate_receipt(receipt, 'fresh-boot', record), receipt)
        for key, bad in (('boot_id', 'old-boot'), ('bit_sha256', 'bad'), ('evidence_path', ''),
                         ('evidence_sha256', 'short')):
            changed = dict(receipt)
            changed[key] = bad
            with self.assertRaises(RuntimeError): gate.validate_receipt(changed, 'fresh-boot', record)

    def test_isolation_is_physical_level_shifter_state(self):
        self.assertTrue(ready.isolated({'fpga_reset': 0, 'level_shifters': 0}))
        self.assertFalse(ready.isolated({'fpga_reset': 15, 'level_shifters': 15}))
        self.assertFalse(ready.isolated({'level_shifters': False}))

    def test_actual_dma_register_values_required(self):
        for capture in (True, False):
            base = 0x30 if capture else 0
            self.assertEqual(ready.dma_proof(lambda offset: 0 if offset == base else 1, capture),
                             {'control': 0, 'status': 1})
            for control, status in ((1, 1), (0, 0), (0, 0x11), (0, 0x8001)):
                with self.assertRaises(RuntimeError):
                    ready.dma_proof(lambda offset: control if offset == base else status, capture)

    def test_receipt_builder_refuses_active_channels_or_unisolated_bootstrap(self):
        record = {'bit_sha256': 'b'*64, 'hwh_sha256': 'h'*64, 'ps_reference_hz': 33333333}
        channels = {role: {'control': 0, 'status': 1} for role in ('capture', 'display')}
        receipt = ready.make_records(record, 'fresh-boot', {'level_shifters': 0}, channels,
                                     Path('/run/evidence'), 'e'*64)
        self.assertEqual(receipt['boot_id'], 'fresh-boot')
        for control, status in ((1, 1), (0, 0), (0, True)):
            bad = copy.deepcopy(channels)
            bad['capture'] = {'control': control, 'status': status}
            with self.assertRaises(RuntimeError):
                ready.make_records(record, 'fresh-boot', {'level_shifters': 0}, bad, Path('/run/evidence'), 'e'*64)
        with self.assertRaises(RuntimeError):
            ready.make_records(record, 'fresh-boot', {'level_shifters': 15}, channels, Path('/run/evidence'), 'e'*64)


if __name__ == '__main__':
    unittest.main()
