"""Build an isolated PL candidate, or inspect the frozen delivered Overlay."""
import argparse
import csv
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
BD = 'color_test/color_test.srcs/sources_1/bd/system/system.bd'
XDC = 'color_test/color_test.srcs/constrs_1/new/'
CONSTRAINTS = ['system.xdc', 'mipi.xdc', 'hdmi_out.xdc', 'display720.xdc']
XPR = 'color_test/color_test.xpr'
CAMERA_MANIFEST = 'board/runtime/output/build/game_app/pynq_beam_hardware_5/hardware.json'
CAMERA_REVIEW = 'build/timing_evidence/nominal_clock_review_20261020.json'
CAMERA_READBACK = 'build/timing_evidence/sensor_readback_20261019.json'
REVIEW_SHA256 = '66a3a6c8112f04391b39fa48442e7210da48277390cac4cbb06317da08b3d7be'
READBACK_SHA256 = '3e40a78f5ee212b79c6ae156862eb198ba98cf47b022dd54d8309813af5a567a'


def camera_timing_model(package=PACKAGE):
    """Bind the nominal model to executed tables, not unused Python defaults.

    12 MHz XVCLK and the 140 MHz HS interpretation were reviewed in the
    preserved 2026-10-20 evidence. Neither is a new physical clock measurement.
    Fail closed for another sensor mode rather than guessing a new PLL formula.
    """
    manifest = json.loads((package/CAMERA_MANIFEST).read_text(encoding='utf-8'))
    for relative, expected in [(CAMERA_REVIEW, REVIEW_SHA256), (CAMERA_READBACK, READBACK_SHA256)]:
        if sha(package/relative) != expected:
            raise ValueError('Camera timing provenance changed: '+relative)
    review = json.loads((package/CAMERA_REVIEW).read_text(encoding='utf-8'))
    readback = json.loads((package/CAMERA_READBACK).read_text(encoding='utf-8'))
    expected = {0x3034: 0x1a, 0x3035: 0x21, 0x3036: 0x46, 0x3037: 0x05,
                0x3108: 0x11, 0x4837: 0x24, 0x3808: 5, 0x3809: 0,
                0x380a: 2, 0x380b: 0xd0, 0x4300: 0, 0x501f: 3}
    executed = dict(manifest['sensor_init'])
    executed.update(dict(manifest['sensor_mode']))
    if any(executed.get(address) != value for address, value in expected.items()):
        raise ValueError('Final executed sensor mode differs from reviewed 720p RAW10 clock model')
    observed = readback['sensor_receipt']['events'][5]['registers']
    for address in [0x3034, 0x3035, 0x3036, 0x3037, 0x3108, 0x4837]:
        if observed.get(hex(address)) != executed[address]:
            raise ValueError('Historical mode readback does not match the final sensor table')
    nominal_hz = review['recommended_declared_model']['nominal_hs_hz']
    if nominal_hz != 140000000 or manifest['frame']['width'] != 1280 or manifest['frame']['height'] != 720:
        raise ValueError('Unreviewed camera clock or image geometry')
    period = Fraction(1000000000, nominal_hz)
    ui = period/2
    minimum, maximum = ui*Fraction(15, 100), ui*Fraction(85, 100)
    # Round outward: never increase the guaranteed stability window by rounding.
    # Vivado 2023.1 uses a 1 ps time grid, not the six-digit printing grid.
    minimum_ps = minimum*1000
    maximum_ps = maximum*1000
    lower = minimum_ps.numerator//minimum_ps.denominator
    upper = -(-maximum_ps.numerator//maximum_ps.denominator)
    return dict(schema='camera-timing-model-v1', xvclk_nominal_hz=12000000,
                hs_nominal_hz=nominal_hz, lane_bps=2*nominal_hz, byte_hz=nominal_hz//4,
                period_exact_ns=str(period), ui_exact_ns=str(ui), time_grid_ns=0.001,
                period_ns=round(float(period), 3), half_period_ns=round(float(ui), 3),
                input_min_ns=lower/1000, input_max_ns=upper/1000,
                input_contract='Inherited 15%/85% UI engineering assumption at FPGA pins',
                physical_hs_frequency='NOT_MEASURED_FOR_CURRENT_BOOT',
                physical_tolerance_skew_jitter_eye='UNKNOWN; not a physical pin guarantee',
                sensor_registers={hex(k): hex(v) for k, v in sorted(expected.items())},
                manifest_sha256=sha(package/CAMERA_MANIFEST),
                evidence_sha256={CAMERA_REVIEW: REVIEW_SHA256, CAMERA_READBACK: READBACK_SHA256})


def camera_timing_xdc(package=PACKAGE):
    model = camera_timing_model(package)
    header = ('# Generated from build/run_pl.py camera_timing_xdc; final executed hardware.json tables.\n'
              '# XVCLK nominal 12 MHz; HS nominal 140 MHz; lane 280 Mb/s; byte 35 MHz.\n'
              '# Sensor 3034=1a,3035=21,3036=46,3037=05,3108=11,4837=24.\n'
              '# Evidence: build/timing_evidence/. No new physical frequency/eye measurement.\n'
              '# 15%/85% UI is the inherited pin-envelope assumption, not vendor signoff.\n'
              '# This top-level file is the sole owner of the MIPI clock and input delays.\n'
              'set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]\n')
    header += 'create_clock -name mipi_hs_clk -period {:.9f} -waveform {{0 {:.9f}}} [get_ports dphy_hs_clock_clk_p]\n'.format(model['period_ns'], model['half_period_ns'])
    ports = '[get_ports {dphy_data_hs_p[*] dphy_data_hs_n[*]}]'
    for edge in ['', ' -clock_fall -add_delay']:
        for kind in ['min', 'max']:
            header += 'set_input_delay -clock mipi_hs_clk{} -{} {:.6f} {}\n'.format(edge, kind, model['input_'+kind+'_ns'], ports)
    return header


def camera_timing_ooc_xdc(package=PACKAGE):
    model = camera_timing_model(package)
    text = ('# Generated from build/run_pl.py camera_timing_ooc_xdc.\n'
            '# IP-only OOC design: same final nominal camera model as top-level system.xdc.\n'
            '# 12MHz XVCLK / HS140MHz; inherited 15%/85% UI envelope, not physical signoff.\n')
    text += 'create_clock -name dphy_clk_hs_p -period {:.3f} -waveform {{0 {:.3f}}} [get_ports dphy_clk_hs_p]\n'.format(model['period_ns'], model['half_period_ns'])
    for edge in ['', ' -clock_fall -add_delay']:
        for kind in ['min', 'max']:
            text += 'set_input_delay -clock dphy_clk_hs_p{} -{} {:.3f} [get_ports {{dphy_data_hs_p[*] dphy_data_hs_n[*]}}]\n'.format(edge, kind, model['input_'+kind+'_ns'])
    return text


def check_camera_timing(project, package=PACKAGE):
    model = camera_timing_model(package)
    actual = (project/(XDC+'system.xdc')).read_text(encoding='utf-8')
    if actual != camera_timing_xdc(package):
        raise ValueError('Top-level camera timing differs from final sensor model')
    design = json.loads((project/BD).read_text(encoding='utf-8'))['design']
    metadata = design['interface_ports']['dphy_hs_clock']['parameters']['FREQ_HZ']['value']
    if int(metadata) != model['hs_nominal_hz']:
        raise ValueError('BD external camera clock metadata differs from final sensor model')
    references = project_references(project)
    for path in references:
        if path.name in {'input_model_effective.xdc', 'timing_context.xdc'}:
            raise ValueError('Historical exported constraints must be disabled in the XPR')
    scoped = project/'color_test/repo/ip/mipi_d_phy_rx/hdl/mipi_dphy_receiver_clocks.xdc'
    if re.search(r'^\s*(?:set_input_delay|create_clock)\b', scoped.read_text(encoding='utf-8'), re.M):
        raise ValueError('Scoped IP must not add a second camera input model')
    ooc = scoped.with_name('mipi_dphy_receiver_ooc.xdc')
    if ooc.read_text(encoding='utf-8') != camera_timing_ooc_xdc(package):
        raise ValueError('IP-only OOC camera model differs from the top-level nominal model')
    return model


def project_references(project):
    """Resolve enabled XPR file inputs, using exact spelling on every platform."""
    project = project.resolve()
    directory = project/'color_test'
    files = []
    for item in ET.parse(project/XPR).getroot().findall('./FileSets/FileSet/File'):
        if any(a.get('Name')=='UserDisabled' and a.get('Val')=='1' for a in item.findall('.//Attr')):
            continue
        name = item.get('Path', '')
        for variable, value in [('$PPRDIR', directory), ('$PSRCDIR', directory/'color_test.srcs'),
                                ('$PGENDIR', directory/'color_test.gen')]:
            name = name.replace(variable, value.as_posix())
        if '$' in name:
            raise ValueError('Unresolved XPR variable: '+name)
        path = Path(name)
        if not path.is_absolute():
            path = directory/path
        path = path.resolve()
        path.relative_to(project)
        if not path.is_file():
            raise ValueError('Missing enabled XPR input: '+str(path))
        files.append(path)
    return sorted(set(files))


def prepare_staged_xpr(project):
    """Remove disabled references only from the private copy before Vivado.

    Even disabled missing references are relocated by open_project, which can
    silently find files in the original workspace. Keep source and staged
    manifests separately so this deterministic transformation is reviewable.
    """
    path = project/XPR
    document = ET.parse(path)
    removed = []
    for fileset in document.getroot().findall('./FileSets/FileSet'):
        for node in list(fileset.findall('File')):
            if any(a.get('Name')=='UserDisabled' and a.get('Val')=='1' for a in node.findall('.//Attr')):
                removed.append(node.get('Path', ''))
                fileset.remove(node)
    document.getroot().set('Path', path.resolve().as_posix())
    document.write(path, encoding='utf-8', xml_declaration=True)
    return dict(disabled_references_removed=removed, project_path=path.resolve().as_posix())


def invoke_vivado(command, output, env):
    # Inherit OS stdio handles. Redirecting them to a Python-opened file can
    # cause intermittent Tcl file-channel failures on Windows ("No error").
    # Vivado's -log/-journal options retain the full native transcript.
    return subprocess.run(command, cwd=output, env=env)


def ip_file_check(project):
    namespace = {'s': 'http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009'}
    checked = 0
    for component in (project/'color_test/repo/ip').rglob('component.xml'):
        for node in ET.parse(component).getroot().findall('.//s:file/s:name', namespace):
            current = component.parent
            for part in Path(node.text or '').parts:
                if part not in {p.name for p in current.iterdir()}:
                    raise ValueError('Missing or case-mismatched IP input: '+str(component)+': '+str(node.text))
                current = current/part
            if not current.is_file():
                raise ValueError('IP input is not a file: '+str(current))
            checked += 1
    return checked


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def inventory(paths, root):
    return [dict(path=p.relative_to(root).as_posix(), bytes=p.stat().st_size, sha256=sha(p))
            for p in sorted(paths)]


def write_inventory(path, rows):
    with path.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, ['path', 'bytes', 'sha256'], delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)


def source_files(project):
    files = {project/BD, project/XPR, *project_references(project)}
    for folder in ['color_test/rtl', 'color_test/repo/ip']:
        directory = project/folder
        if not directory.is_dir():
            raise ValueError('Missing source directory: '+str(directory))
        files.update(p for p in directory.rglob('*') if p.is_file())
    for path in files:
        path.resolve().relative_to(project)
        if not path.is_file():
            raise ValueError('Missing source input: '+str(path))
    ip_file_check(project)
    return sorted(files)


def ip_version_check(project):
    namespace = {'s': 'http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009'}
    available = set()
    for path in (project/'color_test/repo/ip').rglob('component.xml'):
        component = ET.parse(path).getroot()
        available.add(':'.join(component.findtext('s:'+key, namespaces=namespace) or ''
                               for key in ['vendor', 'library', 'name', 'version']))
    required = set()
    def walk(value):
        if isinstance(value, dict):
            vlnv = value.get('vlnv', '')
            fields = vlnv.split(':')
            if len(fields)==4 and fields[0]!='xilinx.com' and fields[1] in {'ip', 'user'}:
                required.add(vlnv)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(json.loads((project/BD).read_text(encoding='utf-8')))
    missing = sorted(required-available)
    return dict(status='FAIL' if missing else 'PASS', missing_vlnvs=missing,
                required_repository_vlnvs=sorted(required), available_repository_vlnvs=sorted(available))


def bit_header(raw):
    """Read the standard BIT header without interpreting configuration data."""
    def field(offset):
        length = struct.unpack_from('>H', raw, offset)[0]
        return raw[offset+2:offset+2+length], offset+2+length
    _, offset = field(0)
    marker, offset = field(offset)
    if marker != b'a':
        raise ValueError('Not a standard Xilinx BIT header')
    result = {}
    for tag, key in [(b'a', 'design'), (b'b', 'part'), (b'c', 'date'), (b'd', 'time')]:
        if tag != b'a':
            if raw[offset:offset+1] != tag:
                raise ValueError('Unexpected BIT field')
            offset += 1
        value, offset = field(offset)
        result[key] = value.rstrip(b'\0').decode('ascii')
    return result


def xsa_payloads(path):
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError('XSA CRC failure: '+bad)
        result = {}
        for suffix in ['.bit', '.hwh']:
            names = [n for n in archive.namelist() if n.endswith(suffix)]
            if len(names) != 1:
                raise ValueError('XSA requires exactly one '+suffix+' member')
            result[suffix] = archive.read(names[0])
        return result


def inspect_delivery(package=PACKAGE):
    project = package/'src/project'
    hardware = package/'board/runtime/output/build/game_app/pynq_beam_hardware_5'
    xsa = project/'color_test/build/beam_standalone/restored_binary_v3_1/inputs/hardware.xsa'
    payloads = xsa_payloads(xsa)
    hashes = {'xsa_sha256': sha(xsa)}
    for suffix, name in [('.bit', 'system_wrapper.bit'), ('.hwh', 'system_wrapper.hwh')]:
        path = hardware/name
        if path.read_bytes() != payloads[suffix]:
            raise ValueError('Delivered payload differs from XSA: '+name)
        hashes[name+'_sha256'] = sha(path)
    reports = []
    for path in sorted((package/'build/reports/raw').glob('*.rpt')):
        text = path.read_text(encoding='utf-8', errors='replace')
        date = re.search(r'^\| Date\s*:\s*(.*?)\s*$', text, re.M)
        reports.append(dict(path=path.relative_to(package).as_posix(), sha256=sha(path),
                            generated_at=date.group(1) if date else 'UNKNOWN',
                            delivered_overlay_binding='NOT_ESTABLISHED'))
    timing = (package/'build/reports/raw/post_impl_timing.rpt').read_text(encoding='utf-8')
    match = re.search(r'Design Timing Summary.*?WNS\(ns\).*?\n\s*[- ]+\n\s*([-\d.]+)\s+([-\d.]+)\s+\d+\s+\d+\s+([-\d.]+)', timing, re.S)
    if not match:
        raise ValueError('Historical timing summary format not recognized')
    inputs = inventory(source_files(project), project)
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    return dict(schema='pl-delivery-evidence-v1', tool='Vivado 2023.1', part='xc7z020clg400-2',
                delivered_overlay={**hashes, 'bit_header': bit_header(payloads['.bit']),
                                   'xsa_bit_hwh_byte_identity': 'PASS'},
                packaged_source=dict(role='REFERENCE_SOURCE_NOT_PROVEN_FROZEN_BUILD_INPUT',
                                     files=len(inputs), inventory_sha256=digest,
                                     repository_ip_check=ip_version_check(project),
                                     constraints={p.relative_to(project).as_posix(): sha(p)
                                                  for p in project_references(project) if p.suffix=='.xdc'},
                                     exact_case_ip_files=ip_file_check(project)),
                historical_reports=reports,
                historical_timing=dict(setup_wns_ns=float(match[1]), setup_tns_ns=float(match[2]),
                                       hold_whs_ns=float(match[3]), status='FAIL'),
                delivered_overlay_source_and_report_binding='NOT_ESTABLISHED',
                delivered_overlay_timing='UNKNOWN',
                missing_evidence=['Frozen 2026-10-04 synthesis/routed checkpoints and their input manifest',
                                  'Synthesis/implementation reports bound to that exact build'],
                candidate_rebuild='NOT_RUN', board_operations=0)


def collect_candidate(artifacts, frozen_bit):
    bit = artifacts/'system_wrapper.bit'
    payloads = xsa_payloads(artifacts/'system_wrapper.xsa')
    if bit.read_bytes() != payloads['.bit']:
        raise ValueError('New XSA does not contain this run\'s BIT')
    hwh = artifacts/'system_wrapper.hwh'
    if hwh.exists():
        raise ValueError('Refuse pre-existing HWH')
    hwh.write_bytes(payloads['.hwh'])
    return dict(xsa_bit_hwh_byte_identity='PASS', matches_frozen_delivered_bit=sha(bit)==sha(frozen_bit),
                status='NEW_CANDIDATE_NOT_BOARD_QUALIFIED', board_operations=0,
                cdc_drc_review='REQUIRED; reports are included, not automatically accepted',
                files=inventory([p for p in artifacts.iterdir() if p.is_file()], artifacts))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, help='Project root containing color_test/color_test.xpr')
    parser.add_argument('--output', type=Path, required=True, help='Fresh directory; existing paths are refused')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--prepare-only', action='store_true', help='Stage and hash inputs without launching Vivado')
    actions.add_argument('--validate-only', action='store_true', help='Run Vivado BD/module-reference validation and output generation, without synthesis')
    actions.add_argument('--reports-only', action='store_true', help='Finish synthesis/route reports, record timing PASS/FAIL separately, never export hardware')
    actions.add_argument('--inspect-only', action='store_true', help='Inspect delivered BIT/XSA and historical report identities')
    parser.add_argument('--vivado-home', type=Path, help='Windows Vivado install; uses the bundled no-cd launcher')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error('preserve existing output: '+str(output))
    if not args.inspect_only and args.project is None:
        parser.error('--project is required for preparation/build')
    delivery = inspect_delivery()
    if args.inspect_only:
        output.mkdir(parents=True)
        write_json(output/'overlay_identity.json', delivery)
        print('Overlay identity inspected; exact source/report binding: NOT_ESTABLISHED')
        return
    project = args.project.resolve()
    files = source_files(project)
    versions = ip_version_check(project)
    camera_model = check_camera_timing(project)
    if project == output or project.is_relative_to(output):
        parser.error('output must not contain the source project')
    for folder in ['color_test/rtl', 'color_test/repo/ip', 'color_test/color_test.srcs']:
        if output.is_relative_to(project/folder):
            parser.error('output must not be in a source-input directory')
    output.mkdir(parents=True)
    staged = output/'inputs/project'
    before = inventory(files, project)
    for path in files:
        target = staged/path.relative_to(project)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    if inventory(source_files(staged), staged) != before:
        raise ValueError('Input copy changed bytes')
    write_inventory(output/'input_manifest.tsv', before)
    shutil.copy2(staged/XPR, output/'source_color_test.xpr')
    xpr_changes = prepare_staged_xpr(staged)
    staged_rows = inventory(source_files(staged), staged)
    for row, original in zip(staged_rows, before):
        if row['path'] != original['path'] or (row['path'] != XPR and row != original):
            raise ValueError('Unexpected staged source change')
    if len(staged_rows) != len(before):
        raise ValueError('Unexpected staged input count')
    write_inventory(output/'staged_input_manifest.tsv', staged_rows)
    script = output/'build_pl.tcl'
    shutil.copy2(HERE/'build_pl.tcl', script)
    work = output/'vivado'
    launcher = str(HERE/'vivado_nocd.bat') if os.name == 'nt' else (shutil.which('vivado') or 'vivado')
    command = [launcher, '-mode', 'batch', '-notrace', '-log', str(output/'vivado.log'),
               '-journal', str(output/'vivado.jou'), '-source', str(script),
               '-tclargs', str(staged), str(work)]
    if args.validate_only:
        command.append('validate-only')
    elif args.reports_only:
        command.append('reports-only')
    record = dict(schema='pl-build-v1', status='PREPARED_ONLY', command=command,
                  source_project=str(project), input_files=len(before),
                  input_manifest_sha256=sha(output/'input_manifest.tsv'),
                  staged_input_manifest_sha256=sha(output/'staged_input_manifest.tsv'),
                  staged_xpr_adjustments=xpr_changes,
                  runner_sha256=sha(Path(__file__)),
                  source_xpr_sha256=sha(output/'source_color_test.xpr'),
                  build_script_sha256=sha(script), delivered_overlay=delivery['delivered_overlay'],
                  source_role=delivery['packaged_source']['role'], vivado_exit_code=None,
                  repository_ip_check=versions,
                  camera_timing_model=camera_model,
                  requested_stage='validate' if args.validate_only else ('reports' if args.reports_only else 'build'),
                  stdio_policy='INHERITED; native vivado.log/vivado.jou; no Python stdio redirection',
                  frozen_runtime_modified=False, board_operations=0)
    write_json(output/'build.json', record)
    if versions['status'] != 'PASS':
        record.update(status='FAILED_PREFLIGHT', error='BD requires unavailable repository IP: '+', '.join(versions['missing_vlnvs']))
        write_json(output/'build.json', record)
        raise SystemExit(record['error'])
    if args.prepare_only:
        print('Prepared {} hashed PL input files; Vivado NOT_RUN'.format(len(before)))
        return
    env = dict(os.environ)
    if args.vivado_home:
        env['XILINX_VIVADO'] = str(args.vivado_home.resolve())
    try:
        if os.name=='nt' and len(str(staged/'color_test'))>80:
            raise ValueError('Vivado project path exceeds 80 characters; select a short fresh output such as tmp/pl1')
        record['status'] = 'RUNNING'
        write_json(output/'build.json', record)
        run = invoke_vivado(command, output, env)
        record['vivado_exit_code'] = run.returncode
        status_path = work/'status.tsv'
        if status_path.is_file():
            record['vivado_stage'] = status_path.read_text(encoding='utf-8').splitlines()[-1].split('\t')[0]
        if run.returncode:
            raise RuntimeError('Vivado failed at {}; retain vivado.log, vivado.jou and partial reports'.format(record.get('vivado_stage', 'startup')))
        if args.validate_only:
            if (work/'status.tsv').read_text(encoding='utf-8').splitlines()[-1] != 'validated\tVALIDATED_INPUTS':
                raise RuntimeError('Vivado did not confirm completed BD/output validation')
            record['status'] = 'VALIDATED_INPUTS'
        elif args.reports_only:
            if (work/'status.tsv').read_text(encoding='utf-8').splitlines()[-1] != 'reports_complete\tREPORTS_COMPLETE':
                raise RuntimeError('Vivado did not confirm completed synthesis/route reports')
            with (work/'reports/timing_result.tsv').open(encoding='utf-8') as result_file:
                timing = list(csv.DictReader(result_file, delimiter='\t'))
            if len(timing) != 1 or timing[0]['status'] not in {'PASS', 'FAIL'}:
                raise RuntimeError('Missing explicit timing PASS/FAIL result')
            record.update(status='REPORTS_COMPLETE', timing_status=timing[0]['status'],
                          timing_detail=timing[0]['detail'], hardware_exported=False,
                          cdc_drc_review='REQUIRED; report completion is not technical acceptance',
                          reports_scope='Rebuilt source candidate; not deployed-Overlay signoff')
        else:
            record['candidate'] = collect_candidate(work/'artifacts', PACKAGE/'board/runtime/output/build/game_app/pynq_beam_hardware_5/system_wrapper.bit')
            record['status'] = 'EXPORTED_CANDIDATE'
    except Exception as error:
        record.update(status='FAILED', error=str(error))
    finally:
        paths = [p for p in work.rglob('*') if p.is_file() and (p.suffix in {'.rpt', '.dcp', '.bit', '.hwh', '.xsa', '.xdc', '.tsv'} or p.name=='prepared_bd.tcl')]
        write_inventory(output/'output_manifest.tsv', inventory(paths, output))
        write_json(output/'build.json', record)
    print(record['status']+'; stage='+record.get('vivado_stage', 'startup')+'; timing='+record.get('timing_status', 'see reports')+'; build record: '+str(output/'build.json'))
    if record['status'] not in {'EXPORTED_CANDIDATE', 'VALIDATED_INPUTS', 'REPORTS_COMPLETE'}:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
