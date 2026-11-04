"""Synthetic artifact failures,real CLI entry;never generates real firmware."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from bind_artifacts import bind
from gate import draft, verify as verify_gate
from prepare import prepare, tcl_word
from verify_inputs import verify
from pynq_scalar_demo.bundle import OFFSETS, MACROS, VLNV, check_header, check_hwh, validate_bundle, validate_description

HERE = Path(__file__).resolve().parent


def fake_hwh():
    regs = []
    for name, offset in OFFSETS.items():
        fields = ''.join('<FIELD NAME="{}" BIT_OFFSET="{}" BIT_WIDTH="1"/>'.format(n, b)
                         for n, b in (("AP_START", 0), ("AP_DONE", 1), ("AP_IDLE", 2))) if offset == 0 else ''
        regs.append('<REGISTER NAME="{}" ADDRESS_OFFSET="{}" SIZE="32">{}</REGISTER>'.format(name, hex(offset), fields))
    return ('<SYSTEM><MODULE FULLNAME="/add_bias_0" VLNV="{}">{}</MODULE></SYSTEM>'.format(VLNV, ''.join(regs))).encode()


def fake_header():
    return '\n'.join('#define XADD_BIAS_CONTROL_ADDR_{} {}'.format(MACROS[k], hex(v)) for k, v in OFFSETS.items()) + '\n'


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="scalar_artifacts_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = self.root / 'profile.json'
        (self.root / 'ps.tcl').write_text('# Synthetic fixture only;not a real PS preset\n', encoding='utf-8')
        self.profile.write_text(json.dumps(dict(board_label='SYNTHETIC_NOT_A_BOARD', part='xc7z020clg400-1',
            tool_version='2023.1', clock_mhz=100, ps_preset_tcl='ps.tcl')), encoding='utf-8')
        self.build = self.root / 'build'

    def inputs(self):
        prepare(self.profile, self.build)
        return self.build / 'inputs.json'

    def reviewed(self, receipt):
        data = draft(receipt)
        data.update(status='PASS', timing=dict.fromkeys(('WNS', 'TNS', 'WHS', 'THS'), 0),
            critical_cdc=0, unexplained_unconstrained=0, drc_errors=0, drc_critical=0,
            resources_reviewed=True, clock_reset_reviewed=True, reviewed_by='SYNTHETIC TEST ONLY')
        for row in data['reports'].values():
            path = Path(row['path'])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'SYNTHETIC DECLARATION TEST;NOT A TOOL REPORT')
            row['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        gate = self.build / 'gate.json'
        gate.write_text(json.dumps(data), encoding='utf-8')
        return gate

    def test_prepare_rejects_empty_profile_and_existing_output(self):
        data = json.loads(self.profile.read_text())
        data['part'] = ''
        self.profile.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            self.inputs()
        self.assertFalse(self.build.exists())

    def test_input_change_and_output_overwrite_rejected(self):
        receipt = self.inputs()
        verify(receipt)
        with self.assertRaises(ValueError):
            prepare(self.profile, self.build)
        (self.root / 'ps.tcl').write_text('# modified fixture')
        with self.assertRaises(ValueError):
            verify(receipt)

    def test_tcl_word_has_no_substitution(self):
        import tkinter
        tcl = tkinter.Tcl()
        value = 'space $danger [error forbidden] "quote" \\path\nnext'
        tcl.eval('set literal ' + tcl_word(value))
        self.assertEqual(tcl.getvar('literal'), value)

    def test_prepared_configuration_change_rejected(self):
        receipt = self.inputs()
        (self.build / 'config.tcl').write_text('set DEMO_PART changed\n')
        with self.assertRaises(ValueError):
            verify(receipt)

    def test_unknown_or_negative_gate_rejected(self):
        receipt = self.inputs()
        gate = self.build / 'gate.json'
        gate.write_text(json.dumps(draft(receipt)))
        with self.assertRaises(ValueError):
            verify_gate(receipt, gate)
        gate = self.reviewed(receipt)
        data = json.loads(gate.read_text())
        data['timing']['WHS'] = -0.001
        gate.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            verify_gate(receipt, gate)

    def test_report_change_rejected(self):
        receipt = self.inputs()
        gate = self.reviewed(receipt)
        verify_gate(receipt, gate)
        (self.build / 'reports/timing.rpt').write_text('changed')
        with self.assertRaises(ValueError):
            verify_gate(receipt, gate)

    def test_abi_fields_and_generated_header_rejected(self):
        check_hwh(fake_hwh(), 'add_bias_0')
        check_header(fake_header())
        for bad in (fake_hwh().replace(b'BIT_OFFSET="2"', b'BIT_OFFSET="3"'),
                    fake_hwh().replace(b'ADDRESS_OFFSET="0x20"', b'ADDRESS_OFFSET="0x24"'),
                    b'<!DOCTYPE SYSTEM []>' + fake_hwh()):
            with self.assertRaises(ValueError):
                check_hwh(bad, 'add_bias_0')
        with self.assertRaises(ValueError):
            check_header(fake_header().replace('0x20', '0x24'))

    def test_runtime_description_range(self):
        validate_description(dict(type=VLNV, phys_addr=0x40000000, addr_range=0x1000))
        for addr, size in ((0, 4096), (3, 4096), (0x40000000, 16), (0xfffff000, 8192)):
            with self.assertRaises(ValueError):
                validate_description(dict(type=VLNV, phys_addr=addr, addr_range=size))

    def test_bind_default_cli_is_offline_and_detects_changed_files(self):
        receipt = self.inputs()
        gate = self.reviewed(receipt)
        header, xsa = self.root / 'generated.h', self.root / 'fake.xsa'
        header.write_text(fake_header())
        with zipfile.ZipFile(xsa, 'w') as archive:
            archive.writestr('design.bit', b'SYNTHETIC_NOT_DOWNLOADABLE')
            archive.writestr('design.hwh', fake_hwh())
        output = self.root / 'bundle'
        bind(xsa, header, receipt, gate, output)
        run = subprocess.run([sys.executable, '-B', str(HERE / 'run_board.py'), str(output)],
                             capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['hardware'], 'NOT_RUN')
        (output / 'scalar.bit').write_bytes(b'modified')
        with self.assertRaises(ValueError):
            validate_bundle(output)

    def test_multiple_bit_members_rejected(self):
        receipt = self.inputs()
        gate = self.reviewed(receipt)
        header, xsa = self.root / 'generated.h', self.root / 'duplicate.xsa'
        header.write_text(fake_header())
        with zipfile.ZipFile(xsa, 'w') as archive:
            archive.writestr('a.bit', b'fake')
            archive.writestr('b.bit', b'fake')
            archive.writestr('design.hwh', fake_hwh())
        with self.assertRaises(ValueError):
            bind(xsa, header, receipt, gate, self.root / 'bundle')


if __name__ == '__main__':
    unittest.main()
