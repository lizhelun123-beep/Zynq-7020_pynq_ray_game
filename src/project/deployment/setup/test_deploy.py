"""用临时文件验证配置事务和进程身份读取，不连接板卡。"""
from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import deploy
from prepare_console import CMDLINE

SOURCE = Path(__file__).resolve().parent / 'fixtures'


class DeployTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='v14_deploy_test_')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.boot = self.root / 'boot/boot.scr'
        self.network = self.root / 'etc/network/interfaces.d/eth0'
        self.boot.parent.mkdir(parents=True)
        self.network.parent.mkdir(parents=True)
        (self.root / 'proc/sys/kernel/random').mkdir(parents=True)
        (self.root / 'proc/sys/kernel/random/boot_id').write_text('12345678-1234-4234-8234-123456789012')
        (self.root / 'proc/cmdline').write_text(CMDLINE)
        self.boot.write_bytes((SOURCE / 'boot.scr.original').read_bytes())
        self.network.write_bytes(b'# keep this note\nauto eth0\niface eth0 inet dhcp\n')

    def test_static_address_and_comments_preserved(self):
        result = deploy.network_candidate(self.network.read_bytes()).decode()
        self.assertIn('# keep this note', result)
        self.assertIn('address 192.168.2.99', result)
        self.assertNotIn('gateway', result)
        self.assertNotIn('inet dhcp', result)

    def test_unknown_network_settings_rejected_without_changes(self):
        before = self.boot.read_bytes()
        self.network.write_bytes(self.network.read_bytes() + b'up custom-command\n')
        with self.assertRaises(ValueError): deploy.install_configs(self.root)
        self.assertEqual(self.boot.read_bytes(), before)
        self.assertFalse((self.root / 'root/beam_v14_setup_backups').exists())

    def test_both_files_backed_up_and_verified_with_fresh_boot(self):
        before = {'boot': self.boot.read_bytes(), 'network': self.network.read_bytes()}
        result = deploy.install_configs(self.root)
        record = json.loads((Path(result['backup']) / 'record.json').read_text())
        for name in before:
            self.assertEqual((Path(result['backup']) / (name + '.before')).read_bytes(), before[name])
        self.assertTrue(record['applied'])
        self.assertFalse(result['reboot_performed'])
        self.assertEqual(result['boot_id'], '12345678-1234-4234-8234-123456789012')
        self.assertEqual(deploy.digest(self.boot.read_bytes()), deploy.BOOT_CANDIDATE)

    def test_second_write_failure_restores_first(self):
        boot, net = self.boot.read_bytes(), self.network.read_bytes()
        real = deploy.replace_file
        failed = []
        def fail_once(path, data, mode):
            if path == self.boot and not failed:
                failed.append(True)
                raise OSError('synthetic second-write failure')
            return real(path, data, mode)
        with patch.object(deploy, 'replace_file', side_effect=fail_once):
            with self.assertRaises(OSError): deploy.install_configs(self.root)
        self.assertTrue(failed)
        self.assertEqual(self.boot.read_bytes(), boot)
        self.assertEqual(self.network.read_bytes(), net)

    def test_unknown_boot_and_hardlink_are_rejected(self):
        self.boot.write_bytes(b'unreviewed boot')
        with self.assertRaises(ValueError): deploy.install_configs(self.root)
        self.boot.write_bytes((SOURCE / 'boot.scr.original').read_bytes())
        os.link(str(self.boot), str(self.boot.with_suffix('.linked')))
        with self.assertRaises(ValueError): deploy.install_configs(self.root)

    def test_repeated_apply_is_idempotent(self):
        deploy.install_configs(self.root)
        backups = sorted((self.root / 'root/beam_v14_setup_backups').iterdir())
        result = deploy.install_configs(self.root)
        self.assertEqual(result['changed'], [])
        self.assertEqual(backups, sorted((self.root / 'root/beam_v14_setup_backups').iterdir()))

    def test_owner_details_bind_pid_to_start_time(self):
        process = self.root / 'proc/42'
        (process / 'fd').mkdir(parents=True)
        tail = ['S'] + ['0'] * 18 + ['98765'] + ['0'] * 5
        (process / 'stat').write_text('42 (a process) ' + ' '.join(tail))
        (process / 'maps').write_text('1000-2000 rw-s 0 00:00 0 /dev/mem\n')
        (process / 'cmdline').write_bytes(b'python3\0worker.py\0--token=SECRET\0')
        (process / 'cgroup').write_text('1:name=systemd:/system.slice/example.service')
        data = deploy.owner_details(self.root / 'proc')
        self.assertEqual(data[0]['pid'], 42)
        self.assertEqual(data[0]['start_ticks'], '98765')
        self.assertTrue(data[0]['identity_stable'])
        self.assertNotIn('SECRET', data[0]['cmdline'])
        self.assertEqual(data[0]['device_maps'], ['1000-2000 rw-s 0 00:00 0 /dev/mem'])

    def test_exact_factory_fixture_is_preserved(self):
        raw = (Path(__file__).parent / 'fixtures/eth0.image').read_bytes()
        self.assertEqual(deploy.digest(raw),
                         '6715629218df4e29e6d9b787b31c3d03c015aeb865368a711b99c7b5c75b401a')
        self.assertEqual(deploy.network_candidate(raw), raw)

    def test_factory_profile_changes_only_boot_and_backs_up_actual_network(self):
        raw = (Path(__file__).parent / 'fixtures/eth0.image').read_bytes()
        self.network.write_bytes(raw)
        result = deploy.install_configs(self.root)
        self.assertEqual(result['changed'], ['boot'])
        self.assertEqual(self.network.read_bytes(), raw)
        self.assertEqual((Path(result['backup']) / 'network.before').read_bytes(), raw)
        self.assertEqual(deploy.digest(self.boot.read_bytes()), deploy.BOOT_CANDIDATE)

    def test_factory_profile_repeat_has_no_new_changes(self):
        self.network.write_bytes((Path(__file__).parent / 'fixtures/eth0.image').read_bytes())
        deploy.install_configs(self.root)
        backups = sorted((self.root / 'root/beam_v14_setup_backups').iterdir())
        result = deploy.install_configs(self.root)
        self.assertEqual(result['changed'], [])
        self.assertEqual(backups, sorted((self.root / 'root/beam_v14_setup_backups').iterdir()))

    def test_unknown_alias_address_or_missing_auto_is_not_silently_accepted(self):
        raw = (Path(__file__).parent / 'fixtures/eth0.image').read_bytes()
        for changed in (raw.replace(b'192.168.2.99', b'192.168.2.98'),
                        raw.replace(b'auto eth0:1\n', b''), raw + b'up custom-command\n'):
            with self.subTest(raw=changed):
                self.network.write_bytes(changed)
                boot = self.boot.read_bytes()
                with self.assertRaises(ValueError): deploy.install_configs(self.root)
                self.assertEqual(self.boot.read_bytes(), boot)
                self.assertEqual(self.network.read_bytes(), changed)
        self.assertFalse((self.root / 'root/beam_v14_setup_backups').exists())

    def test_rejection_keeps_owner_report_and_proves_no_file_write(self):
        self.network.write_bytes(b'auto eth0\niface eth0 inet dhcp\nup custom-command\n')
        report = {'boot_id': 'fresh-observation', 'device_owners': [{'pid': 42}]}
        result = deploy.apply_with_report(report, self.root)
        self.assertEqual(result, 2)
        self.assertTrue(report['configuration']['files_unchanged'])
        self.assertEqual(report['device_owners'], [{'pid': 42}])
        self.assertEqual(report['boot_id'], 'fresh-observation')
        self.assertIn('directives=', report['configuration']['error'])


if __name__ == '__main__':
    unittest.main()
