"""Offline contracts only;the native HDL/implementation stages are separate."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
import tkinter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "assets/rtl-demo/python"))
from pynq_rtl_demo.core import Session, CTRL, STATUS, IRQ_ENABLE, A, B, RESULT
from pynq_rtl_demo.artifacts import inspect_hwh, REGISTERS
from prepare import prepare
from verify_inputs import verify
from gate import parse_rtl_reports


class FakeIRQ:
    def __init__(self):
        self.event = asyncio.Event()
        self.armed = False

    async def wait(self):
        self.armed = True
        await self.event.wait()
        self.event.clear()


class FakeIO:
    def __init__(self, irq=None, complete=True):
        self.r = {CTRL: 0, STATUS: 0, IRQ_ENABLE: 0, A: 0, B: 0, RESULT: 0}
        self.writes, self.irq, self.complete = [], irq, complete

    def read(self, offset):
        return self.r[offset]

    def write(self, offset, value):
        self.writes.append((offset, value))
        if offset == STATUS:
            self.r[STATUS] &= ~value
        elif offset == CTRL:
            if self.complete:
                self.r[RESULT] = (self.r[A] + self.r[B]) & 0xffffffff
                self.r[STATUS] = 1
                if self.r[IRQ_ENABLE]:
                    if self.irq is None or not self.irq.armed:
                        raise AssertionError("IRQ waiter must register before START")
                    self.irq.event.set()
            else:
                self.r[CTRL] = 2
        else:
            self.r[offset] = value


class RuntimeTests(unittest.TestCase):
    def test_unsigned_wrap_and_w1c(self):
        io = FakeIO()
        io.r[STATUS] = 1
        session = Session(io)
        self.assertEqual(session.add(0xffffffff, 1), 0)
        self.assertEqual([v for k, v in io.writes if k == STATUS], [1, 1])
        self.assertEqual(io.r[IRQ_ENABLE], 0)
        self.assertEqual(io.r[STATUS], 0)
        session.close()
        with self.assertRaises(RuntimeError):
            session.add(1, 2)

    def test_invalid_arguments_no_mmio(self):
        io = FakeIO()
        for a, b, timeout in [(True, 0, .1), (-1, 0, .1), (0, 1 << 32, .1), (0, 0, float('nan')), (0, 0, 0), (0, 0, True)]:
            with self.assertRaises(ValueError):
                Session(io).add(a, b, timeout)
        self.assertEqual(io.writes, [])

    def test_timeout_requires_idle_confirmation(self):
        io = FakeIO(complete=False)
        session = Session(io)
        with self.assertRaises(TimeoutError):
            session.add(1, 2, .001)
        with self.assertRaises(RuntimeError):
            session.close()
        self.assertFalse(session.recover_if_idle())
        io.r[CTRL] = 0
        self.assertTrue(session.recover_if_idle())
        session.close()

    def test_async_order_and_cancel(self):
        async def scenario():
            irq = FakeIRQ()
            io = FakeIO(irq)
            session = Session(io, irq)
            self.assertEqual(await session.add_async(7, 6), 13)
            self.assertEqual(session.irq_events, 1)
            io.complete = False
            task = asyncio.ensure_future(session.add_async(7, 6))
            await asyncio.sleep(.001)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertFalse(session.irq_usable)
            self.assertFalse(session.recover_if_idle())
            io.r[CTRL] = 0
            self.assertTrue(session.recover_if_idle())
            with self.assertRaises(RuntimeError):
                await session.add_async(1, 2)
            io.complete = True
            self.assertEqual(session.add(1, 2), 3)
        asyncio.run(scenario())


class PreparationTests(unittest.TestCase):
    def test_receipt_tracks_staged_and_original_bytes(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            root = Path(folder)
            preset = root / 'preset.tcl'
            preset.write_text('# trusted test fixture only\n')
            profile = root / 'profile.json'
            profile.write_text(json.dumps(dict(part='xc7z020clg400-2', board_label='fixture', tool_version='2023.1', clock_mhz=100, ps_preset_tcl=str(preset))))
            build = root / 'new'
            prepare(profile, build, 'rtl')
            self.assertEqual(verify(build / 'inputs.json')['flow'], 'rtl')
            staged = build / 'source/hdl/add32.v'
            staged.write_text(staged.read_text() + '\n// drift\n')
            with self.assertRaises(ValueError):
                verify(build / 'inputs.json')
            with self.assertRaises(ValueError):
                prepare(profile, build, 'rtl')

    def test_source_path_captured_before_later_proc_call(self):
        tcl = tkinter.Tcl()
        source = ROOT / 'assets/rtl-demo/vivado/project.tcl'
        tcl.call('source', '-encoding', 'utf-8', str(source))
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            root = Path(folder)
            preset = root / 'preset.tcl'
            preset.write_text('# fixture')
            # Stop before vendor APIs;exercise actual procedure resolution from a different caller.
            tcl.eval('proc create_project {args} {};proc add_files {args} {set ::captured [lindex $args end];error END_OF_HOST_SCOPE}')
            with self.assertRaises(tkinter.TclError):
                tcl.call('make_project', (root / 'new').as_posix(), preset.as_posix(), 'xc7z020clg400-2', 100)
            self.assertEqual(Path(tcl.getvar('captured')).resolve(), (source.parent.parent / 'hdl/add32.v').resolve())

    def test_hwh_rejects_missing_or_ambiguous_core(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            path = Path(folder) / 'bad.hwh'
            for content in ['<SYSTEM/>', '<!DOCTYPE x><SYSTEM/>', '<SYSTEM><MODULE INSTANCE="add32_0" VLNV="pynq.local:rtl:add32:1.0"/></SYSTEM>']:
                path.write_text(content)
                with self.assertRaises(ValueError):
                    inspect_hwh(path)

    def test_hwh_real_property_layout_and_duplicate(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            path = Path(folder) / 'metadata.hwh'
            registers = ''.join('<REGISTER NAME="{}"><PROPERTY NAME="ADDRESS_OFFSET" VALUE="{}"/><PROPERTY NAME="SIZE" VALUE="32"/><PROPERTY NAME="ACCESS" VALUE="{}"/></REGISTER>'.format(name, offset, 'read-only' if name in ('VERSION', 'RESULT', 'COUNT') else 'read-write') for name, offset in REGISTERS.items())
            xml = '<SYSTEM><MODULE INSTANCE="add32_0" VLNV="pynq.local:rtl:add32:1.0">{}</MODULE><MEMRANGE INSTANCE="add32_0" BASEVALUE="0x43c00000" HIGHVALUE="0x43c00fff"/></SYSTEM>'
            path.write_text(xml.format(registers))
            self.assertEqual(inspect_hwh(path)['registers'], REGISTERS)
            path.write_text(xml.format(registers + registers))
            with self.assertRaises(ValueError):
                inspect_hwh(path)

    def test_reports_fail_missing_unknown_negative(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            root = Path(folder)
            (root / 'timing.rpt').write_text('\n'.join('checking {} (0)'.format(k) for k in ('no_clock', 'unconstrained_internal_endpoints', 'no_input_delay', 'no_output_delay')))
            (root / 'cdc.rpt').write_text('CDC Report\nID Severity Count Description\n')
            (root / 'utilization.rpt').write_text('\n'.join('| {} | 1 | 0 | 0 | 100 | 1 |'.format(k) for k in ('Slice LUTs', 'Slice Registers', 'Slice', 'Block RAM Tile', 'DSPs')))
            metrics = dict(WNS=1, TNS=0, WHS=.1, THS=0)
            self.assertEqual(parse_rtl_reports(root, metrics)['status'], 'PASS')
            metrics['WNS'] = -.1
            self.assertEqual(parse_rtl_reports(root, metrics)['status'], 'FAIL')
            (root / 'timing.rpt').write_text('new unknown format')
            with self.assertRaises(ValueError):
                parse_rtl_reports(root, metrics)


if __name__ == '__main__':
    unittest.main()
