"""Host control-flow checks; these mocks do not synthesize or qualify FPGA logic."""
import importlib.util
import json
from fractions import Fraction
from pathlib import Path
import shutil
import tempfile
import tkinter
import unittest
from unittest.mock import patch
import zipfile

BUILD = Path(__file__).resolve().parents[1]/'build'
spec = importlib.util.spec_from_file_location('run_pl', BUILD/'run_pl.py')
flow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flow)


class PlFlowTests(unittest.TestCase):
    def test_staged_xpr_drops_only_disabled_references_and_keeps_source_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            path = project/flow.XPR
            path.parent.mkdir(parents=True)
            source = '<Project Path="old"><FileSets><FileSet><File Path="$PPRDIR/keep.xdc"/><File Path="$PPRDIR/missing.xdc"><FileInfo><Attr Name="UserDisabled" Val="1"/></FileInfo></File></FileSet></FileSets></Project>'
            path.write_text(source)
            backup = project/'source.xpr'
            shutil.copy2(path, backup)
            (path.parent/'keep.xdc').write_text('# active')
            result = flow.prepare_staged_xpr(project)
            self.assertEqual(result['disabled_references_removed'], ['$PPRDIR/missing.xdc'])
            self.assertNotIn('missing.xdc', path.read_text())
            self.assertEqual(backup.read_text(), source)
            self.assertEqual(flow.project_references(project), [(path.parent/'keep.xdc').resolve()])

    def test_vivado_inherits_stdio_and_returns_original_exit_code(self):
        with patch.object(flow.subprocess, 'run') as run:
            run.return_value.returncode = 7
            result = flow.invoke_vivado(['vivado', '-log', 'vivado.log'], Path('work'), {'NAME': 'value'})
            run.assert_called_once_with(['vivado', '-log', 'vivado.log'], cwd=Path('work'), env={'NAME': 'value'})
            self.assertEqual(result.returncode, 7)

    def run_flow(self, root, setup=.1, hold=.1, missing_path=False, pulse_failure=False,
                 open_failure=None, validate_only=False, reports_only=False, enclosing_proc=False):
        project = root/'inputs'
        bd = project/flow.BD
        bd.parent.mkdir(parents=True)
        bd.write_text('{}', encoding='utf-8')
        (project/'color_test/rtl').mkdir()
        (project/'color_test/rtl/top.v').write_text('module top; endmodule')
        for name in flow.CONSTRAINTS:
            path = project/flow.XDC/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# mock constraint')
        out = root/'result'
        run_dir = root/'run'
        run_dir.mkdir()
        launches = {}
        events = []
        interp = tkinter.Tcl()
        def invoke(name, *args):
            events.append((name, args))
            if name == 'open_bd_design':
                # One frame is our Tcl command shim. Its caller must be the
                # global script frame, as in the actual Vivado A/B probe.
                if int(interp.eval('info level')) != 1:
                    return 'Vendor BD initialization requires global Tcl scope'
                return open_failure or ''
            if name == 'get_ips':
                return 'system_axis_color_highlight_0_0'
            if name == 'version':
                return '2023.1'
            if name in {'get_runs', 'get_files'}:
                return args[-1]
            if name == 'get_timing_paths':
                return '' if missing_path else ('setup_path' if args[1]=='max' else 'hold_path')
            if name == 'get_property':
                prop, obj = args
                if prop == 'STATUS':
                    return ('synth_design' if obj=='synth_1' else launches['impl_1'])+' Complete!'
                if prop == 'DIRECTORY':
                    return str(run_dir)
                if prop == 'SLACK':
                    return setup if obj=='setup_path' else hold
            if name == 'launch_runs':
                launches[args[0]] = args[args.index('-to_step')+1] if '-to_step' in args else 'synth_design'
                if launches[args[0]] == 'write_bitstream':
                    (run_dir/'system_wrapper.bit').write_bytes(b'mock-bit')
            if name.startswith('report_') or name in {'write_checkpoint', 'write_xdc', 'write_bd_tcl'}:
                destination = Path(args[args.index('-file')+1]) if '-file' in args else Path(args[-1])
                destination.parent.mkdir(parents=True, exist_ok=True)
                text = 'HOST MOCK ONLY\n'
                if destination.name=='post_impl_timing.rpt':
                    text += 'Timing constraints are not met.\n' if pulse_failure else 'All user specified timing constraints are met.\n'
                destination.write_text(text)
            if name == 'write_hw_platform':
                with zipfile.ZipFile(args[-1], 'x') as archive:
                    archive.writestr('system.bit', b'mock-bit')
                    archive.writestr('system.hwh', b'mock-hwh')
            if name == 'make_wrapper':
                return str(project/'system_wrapper.v')
            return ''
        names = ['version', 'open_project', 'reset_run', 'set_property', 'current_project', 'update_ip_catalog',
                 'add_files', 'get_files', 'validate_bd_design', 'save_bd_design',
                 'get_ips', 'update_module_reference',
                 'write_bd_tcl', 'generate_target', 'make_wrapper', 'current_fileset',
                 'update_compile_order', 'report_ip_status', 'report_compile_order', 'launch_runs',
                 'wait_on_run', 'get_property', 'get_runs', 'open_run', 'write_checkpoint',
                 'report_timing_summary', 'report_utilization', 'close_design', 'write_xdc',
                 'report_clock_interaction', 'report_cdc', 'report_drc', 'report_methodology',
                 'get_timing_paths', 'write_hw_platform', 'close_project']
        for name in names:
            interp.createcommand(name, lambda *args, command=name: invoke(command, *args))
        interp.createcommand('host_open_bd_design', lambda *args: invoke('open_bd_design', *args))
        interp.eval('''
            proc open_bd_design {args} {
                set message [host_open_bd_design {*}$args]
                if {$message ne {}} {error $message}
            }
        ''')
        interp.setvar('argc', 3 if validate_only or reports_only else 2)
        mode = ['validate-only'] if validate_only else (['reports-only'] if reports_only else [])
        arguments = [str(project), str(out)] + mode
        interp.setvar('argv', interp.call('list', *arguments))
        failure = None
        try:
            script = (BUILD/'build_pl.tcl').read_text(encoding='utf-8')
            if enclosing_proc:
                script = 'proc legacy_local_scope {} {\n global argc argv\n'+script+'\n}\nlegacy_local_scope'
            interp.eval(script)
        except tkinter.TclError as error:
            failure = str(error)
        return out, events, failure

    def test_module_reference_load_and_refresh_run_in_global_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            out, events, failure = self.run_flow(Path(temporary), validate_only=True)
            self.assertIsNone(failure)
            self.assertEqual(sum(name=='open_bd_design' for name,_ in events), 1)
            names = [name for name,_ in events]
            self.assertLess(names.index('update_compile_order'), names.index('open_bd_design'))
            self.assertLess(names.index('open_bd_design'), names.index('update_module_reference'))
            self.assertLess(names.index('update_module_reference'), names.index('validate_bd_design'))

    def test_legacy_procedure_scope_reproduces_callback_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            out, events, failure = self.run_flow(Path(temporary), enclosing_proc=True)
            self.assertEqual(failure, 'Vendor BD initialization requires global Tcl scope')
            self.assertFalse(any(name=='launch_runs' for name,_ in events))

    def test_actual_bd_load_errors_stop_without_retry_or_synthesis(self):
        for reports_only in [False, True]:
            with self.subTest(reports_only=reports_only), tempfile.TemporaryDirectory() as temporary:
                out, events, failure = self.run_flow(Path(temporary), open_failure='BD load failed', reports_only=reports_only)
                self.assertEqual(failure, 'BD load failed')
                self.assertEqual(sum(name=='open_bd_design' for name,_ in events), 1)
                self.assertFalse(any(name=='launch_runs' for name,_ in events))
                self.assertIn('open_block_design\tFAILED', (out/'status.tsv').read_text())

    def test_validate_only_generates_products_without_launching_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            out, events, failure = self.run_flow(Path(temporary), validate_only=True)
            self.assertIsNone(failure)
            self.assertTrue(any(name=='generate_target' for name,_ in events))
            self.assertFalse(any(name=='launch_runs' for name,_ in events))
            self.assertFalse((out/'artifacts').exists())
            self.assertIn('validated\tVALIDATED_INPUTS', (out/'status.tsv').read_text())

    def test_reports_only_completes_but_preserves_failed_timing_without_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            out, events, failure = self.run_flow(Path(temporary), reports_only=True, hold=-.844)
            self.assertIsNone(failure)
            self.assertIn('reports_complete\tREPORTS_COMPLETE', (out/'status.tsv').read_text())
            result = (out/'reports/timing_result.tsv').read_text()
            self.assertIn('FAIL\tmin: slack=-0.844', result)
            self.assertTrue((out/'checkpoints/routed.dcp').is_file())
            self.assertFalse((out/'artifacts').exists())
            self.assertFalse(any(name=='write_hw_platform' for name,_ in events))
            self.assertFalse(any(name=='launch_runs' and '-to_step' in args and args[args.index('-to_step')+1]=='write_bitstream' for name,args in events))

    def test_reports_only_pass_still_does_not_export_hardware(self):
        with tempfile.TemporaryDirectory() as temporary:
            out, events, failure = self.run_flow(Path(temporary), reports_only=True)
            self.assertIsNone(failure)
            self.assertIn('PASS\t', (out/'reports/timing_result.tsv').read_text())
            self.assertFalse(any(name=='write_hw_platform' for name,_ in events))

    def test_success_exports_only_after_setup_and_hold_gates(self):
        with tempfile.TemporaryDirectory() as temporary:
            out, events, failure = self.run_flow(Path(temporary))
            self.assertIsNone(failure)
            export = next(i for i,(name,_) in enumerate(events) if name=='write_hw_platform')
            paths = [i for i,(name,_) in enumerate(events) if name=='get_timing_paths']
            self.assertEqual(len(paths), 2)
            self.assertGreater(export, max(paths))
            frozen = Path(temporary)/'frozen.bit'
            frozen.write_bytes(b'other-bit')
            collected = flow.collect_candidate(out/'artifacts', frozen)
            self.assertFalse(collected['matches_frozen_delivered_bit'])
            self.assertEqual((out/'artifacts/system_wrapper.hwh').read_bytes(), b'mock-hwh')

    def test_negative_setup_preserves_reports_without_export(self):
        self.assert_gate_failure(setup=-.1)

    def test_negative_hold_preserves_reports_without_export(self):
        self.assert_gate_failure(hold=-.1)

    def test_no_timing_path_is_rejected(self):
        self.assert_gate_failure(missing_path=True)

    def test_pulse_width_failure_is_rejected(self):
        self.assert_gate_failure(pulse_failure=True)

    def assert_gate_failure(self, **options):
        with tempfile.TemporaryDirectory() as temporary:
            out, events, failure = self.run_flow(Path(temporary), **options)
            self.assertIn('Timing failed:', failure)
            self.assertTrue((out/'reports/post_impl_timing.rpt').is_file())
            self.assertTrue((out/'checkpoints/routed.dcp').is_file())
            self.assertFalse((out/'artifacts').exists())
            self.assertFalse(any(name=='write_hw_platform' for name,_ in events))

    def test_mismatched_xsa_bit_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifacts = Path(temporary)
            frozen = artifacts/'frozen.bit'
            frozen.write_bytes(b'frozen')
            (artifacts/'system_wrapper.bit').write_bytes(b'new')
            with zipfile.ZipFile(artifacts/'system_wrapper.xsa', 'x') as archive:
                archive.writestr('system.bit', b'wrong')
                archive.writestr('system.hwh', b'hwh')
            with self.assertRaisesRegex(ValueError, 'this run'):
                flow.collect_candidate(artifacts, frozen)
            self.assertFalse((artifacts/'system_wrapper.hwh').exists())

    def test_recovered_source_ip_versions_and_exact_file_case_match(self):
        result = flow.ip_version_check(flow.PACKAGE/'src/project')
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['missing_vlnvs'], [])
        self.assertIn('digilentinc.com:ip:MIPI_CSI_2_RX:1.2', result['available_repository_vlnvs'])
        self.assertGreater(flow.ip_file_check(flow.PACKAGE/'src/project'), 100)

    def test_enabled_xpr_inputs_are_all_staged(self):
        project = flow.PACKAGE/'src/project'
        files = flow.source_files(project)
        self.assertIn(project/flow.XPR, files)
        recovered = [p for p in files if p.name in {'timing_context.xdc', 'input_model_effective.xdc'}]
        self.assertEqual(len(recovered), 0)
        for name in ['timing_context.xdc', 'input_model_effective.xdc']:
            self.assertTrue((project/'color_test/build/pl_rate93_production/build_5/synth'/name).is_file())

    def test_final_sensor_clock_and_window_scale_together(self):
        model = flow.check_camera_timing((flow.PACKAGE/'src/project').resolve())
        self.assertEqual((model['hs_nominal_hz'], model['lane_bps'], model['byte_hz']),
                         (140000000, 280000000, 35000000))
        self.assertLessEqual(Fraction(str(model['input_min_ns'])), Fraction(25, 28))
        self.assertGreaterEqual(Fraction(str(model['input_max_ns'])), Fraction(75, 28))
        self.assertEqual(model['input_contract_qualification'], 'USER_DECLARED_UNMEASURED')
        self.assertEqual(model['input_contract_sha256'], flow.sha(flow.PACKAGE/flow.CAMERA_CONTRACT))
        self.assertEqual(model['physical_hs_frequency'], 'NOT_MEASURED_FOR_CURRENT_BOOT')
        xdc = flow.camera_timing_xdc()
        self.assertEqual(xdc.count('set_input_delay '), 4)
        self.assertEqual(xdc.count('-clock_fall -add_delay'), 2)

    def test_unmeasured_input_contract_cannot_claim_physical_qualification(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            for relative in [flow.CAMERA_MANIFEST, flow.CAMERA_REVIEW, flow.CAMERA_READBACK, flow.CAMERA_CONTRACT]:
                target = package/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(flow.PACKAGE/relative, target)
            path = package/flow.CAMERA_CONTRACT
            contract = json.loads(path.read_text())
            contract['qualification'] = 'MEASURED'
            path.write_text(json.dumps(contract))
            with self.assertRaisesRegex(ValueError, 'qualification must remain explicitly unmeasured'):
                flow.camera_timing_model(package)

    def test_invalid_transition_envelope_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            for relative in [flow.CAMERA_MANIFEST, flow.CAMERA_REVIEW, flow.CAMERA_READBACK, flow.CAMERA_CONTRACT]:
                target = package/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(flow.PACKAGE/relative, target)
            path = package/flow.CAMERA_CONTRACT
            contract = json.loads(path.read_text())
            contract['minimum_ui'], contract['maximum_ui'] = '3/4', '1/4'
            path.write_text(json.dumps(contract))
            with self.assertRaisesRegex(ValueError, 'ordered within one UI'):
                flow.camera_timing_model(package)

    def test_different_executed_sensor_pll_is_not_given_the_same_model(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            for relative in [flow.CAMERA_MANIFEST, flow.CAMERA_REVIEW, flow.CAMERA_READBACK]:
                target = package/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(flow.PACKAGE/relative, target)
            path = package/flow.CAMERA_MANIFEST
            manifest = json.loads(path.read_text(encoding='utf-8'))
            manifest['sensor_mode'] = [[a, 0x61 if a==0x3035 else v] for a,v in manifest['sensor_mode']]
            path.write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Final executed sensor mode differs'):
                flow.camera_timing_model(package)

    def test_second_scoped_camera_window_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            top = project/(flow.XDC+'system.xdc')
            top.parent.mkdir(parents=True)
            top.write_text(flow.camera_timing_xdc(), encoding='utf-8')
            (project/flow.XPR).write_text('<Project><FileSets/></Project>')
            bd = project/flow.BD
            bd.parent.mkdir(parents=True)
            bd.write_text(json.dumps({'design': {'interface_ports': {'dphy_hs_clock': {
                'parameters': {'FREQ_HZ': {'value': '140000000'}}}}}}))
            scoped = project/'color_test/repo/ip/mipi_d_phy_rx/hdl/mipi_dphy_receiver_clocks.xdc'
            scoped.parent.mkdir(parents=True)
            scoped.write_text('set_input_delay -clock mipi_hs_clk -min 0.268 [get_ports dphy_data_hs_p*]')
            with self.assertRaisesRegex(ValueError, 'Scoped IP must not add a second'):
                flow.check_camera_timing(project)

    def test_wrong_bd_camera_frequency_is_rejected_before_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            top = project/(flow.XDC+'system.xdc')
            top.parent.mkdir(parents=True)
            top.write_text(flow.camera_timing_xdc(), encoding='utf-8')
            bd = project/flow.BD
            bd.parent.mkdir(parents=True)
            bd.write_text(json.dumps({'design': {'interface_ports': {'dphy_hs_clock': {
                'parameters': {'FREQ_HZ': {'value': '336000000'}}}}}}))
            with self.assertRaisesRegex(ValueError, 'BD external camera clock metadata'):
                flow.check_camera_timing(project)

    def test_missing_enabled_constraint_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            xpr = project/flow.XPR
            xpr.parent.mkdir(parents=True)
            xpr.write_text('<Project><FileSets><FileSet><File Path="$PPRDIR/missing.xdc"/></FileSet></FileSets></Project>')
            with self.assertRaisesRegex(ValueError, 'Missing enabled XPR input'):
                flow.project_references(project)


if __name__ == '__main__':
    unittest.main(verbosity=2)
