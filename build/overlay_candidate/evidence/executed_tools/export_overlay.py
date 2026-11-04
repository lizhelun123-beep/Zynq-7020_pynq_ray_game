"""Export a new Overlay from one completed report build, retaining its binding."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import xml.etree.ElementTree as ET

import run_pl as flow

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
FROZEN = PACKAGE/'board/runtime/output/build/game_app/pynq_beam_hardware_5'


def bit_configuration(raw):
    """Return the length-checked configuration field, excluding BIT metadata."""
    def field(offset):
        size=struct.unpack_from('>H',raw,offset)[0]
        return raw[offset+2:offset+2+size],offset+2+size
    _,offset=field(0)
    marker,offset=field(offset)
    if marker != b'a':
        raise ValueError('Unknown BIT header')
    for tag in [b'a',b'b',b'c',b'd']:
        if tag != b'a':
            if raw[offset:offset+1] != tag:
                raise ValueError('Unknown BIT header field')
            offset+=1
        _,offset=field(offset)
    if raw[offset:offset+1] != b'e':
        raise ValueError('Missing BIT configuration field')
    size=struct.unpack_from('>I',raw,offset+1)[0]
    if offset+5+size != len(raw):
        raise ValueError('BIT configuration length mismatch')
    return raw[offset+5:]


def canonicalize_xsa_bit(artifacts, preserved):
    """Preserve early bitgen; deliver the platform exporter BIT without edits."""
    path=artifacts/'system_wrapper.bit'
    initial=path.read_bytes()
    canonical=flow.xsa_payloads(artifacts/'system_wrapper.xsa')['.bit']
    a,b=flow.bit_header(initial),flow.bit_header(canonical)
    if (a['design'],a['part']) != (b['design'],b['part']) or bit_configuration(initial) != bit_configuration(canonical):
        raise ValueError('XSA configuration payload differs from this checkpoint bitgen')
    info=dict(configuration_payload_byte_identity='PASS',
              configuration_sha256=hashlib.sha256(bit_configuration(canonical)).hexdigest(),
              canonical_bit_source='Unmodified BIT member extracted from this native XSA',
              initial_bit_sha256=hashlib.sha256(initial).hexdigest(),
              canonical_bit_sha256=hashlib.sha256(canonical).hexdigest(),
              initial_header=a,canonical_header=b)
    if initial != canonical:
        if preserved.exists():
            raise ValueError('Refuse pre-existing preserved BIT')
        shutil.move(path,preserved)
        path.write_bytes(canonical)
        info['initial_bit_preserved_as']=preserved.name
    return info


def parent_file(parent, relative):
    path = parent/relative
    if not path.is_file() and relative.startswith('vivado/'):
        path = parent/relative[len('vivado/'):]
    if not path.is_file():
        raise ValueError('Missing parent evidence: '+relative)
    return path


def timing_metrics(path):
    lines = path.read_text(encoding='utf-8').splitlines()
    index = next(i for i, line in enumerate(lines) if 'WNS(ns)' in line)
    values = lines[index+2].split()
    if len(values) != 12:
        raise ValueError('Unknown timing summary format')
    return dict(zip(['wns','tns','setup_failing','setup_total','whs','ths','hold_failing',
                     'hold_total','wpws','tpws','pulse_failing','pulse_total'], values))


def validate_parent(parent, project):
    record = json.loads((parent/'build.json').read_text(encoding='utf-8'))
    if record.get('status') != 'REPORTS_COMPLETE' or record.get('timing_status') != 'PASS':
        raise ValueError('Require completed, timing-passing parent reports')
    for name, key in [('input_manifest.tsv','input_manifest_sha256'),
                      ('staged_input_manifest.tsv','staged_input_manifest_sha256')]:
        if flow.sha(parent/name) != record[key]:
            raise ValueError('Parent manifest changed: '+name)
    model = flow.check_camera_timing(project)
    if model != record['camera_timing_model']:
        raise ValueError('Source camera model differs from the reported implementation')
    for row in csv.DictReader((parent/'input_manifest.tsv').open(encoding='utf-8'), delimiter='\t'):
        path = (project/row['path']).resolve()
        path.relative_to(project.resolve())
        if flow.sha(path) != row['sha256']:
            raise ValueError('Reported source changed: '+row['path'])
    for row in csv.DictReader((parent/'output_manifest.tsv').open(encoding='utf-8'), delimiter='\t'):
        if flow.sha(parent_file(parent,row['path'])) != row['sha256']:
            raise ValueError('Reported output changed: '+row['path'])
    return record


def interface_snapshot(raw):
    root = ET.fromstring(raw)
    modules = {m.get('INSTANCE'):m for m in root.findall('.//MODULE')}
    parameters = {n:{p.get('NAME'):p.get('VALUE') for p in m.findall('./PARAMETERS/PARAMETER')}
                  for n,m in modules.items()}
    ranges = sorted((m.get('INSTANCE'), tuple(sorted(r.attrib.items())))
                    for m in modules.values() for r in m.findall('.//MEMRANGE'))
    ports = sorted(tuple((k,p.get(k)) for k in ['NAME','DIR','LEFT','RIGHT'])
                   for p in root.findall('./EXTERNALPORTS/PORT'))
    return dict(memory_ranges=ranges, external_ports=ports, parameters=parameters)


def compare_interfaces(old_raw, new_raw):
    old, new = interface_snapshot(old_raw), interface_snapshot(new_raw)
    if old['memory_ranges'] != new['memory_ranges'] or old['external_ports'] != new['external_ports']:
        raise ValueError('Address map or external port shape differs from the runtime baseline')
    for name in ['axi_vdma_0','axi_vdma_1','processing_system7_0']:
        if old['parameters'].get(name) != new['parameters'].get(name):
            raise ValueError('PS/VDMA parameters changed: '+name)
    changes = {}
    for name in sorted(old['parameters'].keys() | new['parameters'].keys()):
        a,b = old['parameters'].get(name,{}),new['parameters'].get(name,{})
        delta = {k:dict(old=a.get(k),new=b.get(k)) for k in sorted(a.keys()|b.keys()) if a.get(k)!=b.get(k)}
        if delta:
            changes[name] = delta
    return dict(address_map_external_port_shapes_ps_vdma_parameters='MATCH',
                parameter_differences=changes,
                scope='Static metadata only; not register-semantics or board-functional qualification')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-build',type=Path,required=True,help='Completed report run or its archived report folder')
    parser.add_argument('--output',type=Path,required=True,help='Fresh export directory')
    parser.add_argument('--vivado-home',type=Path)
    args = parser.parse_args()
    parent, out = args.from_build.resolve(), args.output.resolve()
    if out.exists() or out.is_relative_to(parent) or parent.is_relative_to(out):
        parser.error('Use a fresh output outside the parent build')
    project = PACKAGE/'src/project'
    record = validate_parent(parent, project)
    source_dcp = parent_file(parent,'vivado/checkpoints/routed.dcp')
    out.mkdir(parents=True)
    inputs = out/'inputs'
    inputs.mkdir()
    dcp = inputs/'routed.dcp'
    shutil.copy2(source_dcp,dcp)
    if flow.sha(dcp) != flow.sha(source_dcp):
        raise ValueError('Checkpoint copy differs')
    for name in ['build.json','input_manifest.tsv','staged_input_manifest.tsv','output_manifest.tsv']:
        shutil.copy2(parent/name,inputs/('parent_'+name))
    script = out/'export_overlay.tcl'
    shutil.copy2(HERE/'export_overlay.tcl',script)
    frozen_before = {p.name:flow.sha(p) for p in FROZEN.iterdir() if p.is_file()}
    binding = dict(schema='overlay-export-binding-v1',status='RUNNING',
                   parent_build=str(parent), parent_build_sha256=flow.sha(parent/'build.json'),
                   parent_input_manifest_sha256=record['input_manifest_sha256'],
                   parent_staged_input_manifest_sha256=record['staged_input_manifest_sha256'],
                   routed_checkpoint_sha256=flow.sha(source_dcp),
                   copied_checkpoint_sha256=flow.sha(dcp),
                   parent_timing_report_sha256=flow.sha(parent_file(parent,'vivado/reports/post_impl_timing.rpt')),
                   camera_timing_model=record['camera_timing_model'],
                   timing_qualification=record['timing_qualification'],
                   runner_sha256=flow.sha(Path(__file__)),script_sha256=flow.sha(script),
                   synthesis_rerun=False,implementation_rerun=False,board_operations=0,
                   installed_overlay_modified=False,hardware_exported=False)
    command = [str(HERE/'vivado_nocd.bat') if os.name=='nt' else (shutil.which('vivado') or 'vivado'),
               '-mode','batch','-notrace','-log',str(out/'vivado.log'),'-journal',str(out/'vivado.jou'),
               '-source',str(script),'-tclargs',str(dcp),str(out/'vivado')]
    binding['command'] = command
    flow.write_json(out/'binding.json',binding)
    env = dict(os.environ)
    if args.vivado_home:
        env['XILINX_VIVADO'] = str(args.vivado_home.resolve())
    try:
        result = flow.invoke_vivado(command,out,env)
        binding['vivado_exit_code'] = result.returncode
        if result.returncode:
            raise RuntimeError('Vivado export failed; retain native log and partial output')
        if (out/'vivado/status.tsv').read_text().splitlines()[-1] != 'complete\tEXPORTED_FROM_ROUTED_CHECKPOINT':
            raise ValueError('Missing completed export status')
        artifacts = out/'vivado/artifacts'
        normalization = canonicalize_xsa_bit(artifacts,out/'initial_bitgen.bit')
        candidate = flow.collect_candidate(artifacts,FROZEN/'system_wrapper.bit')
        before = timing_metrics(parent_file(parent,'vivado/reports/post_impl_timing.rpt'))
        after = timing_metrics(out/'vivado/reports/export_timing.rpt')
        if before != after:
            raise ValueError('Export checkpoint timing differs from parent reports')
        if flow.sha(dcp) != binding['routed_checkpoint_sha256'] or flow.sha(source_dcp) != binding['routed_checkpoint_sha256']:
            raise ValueError('Parent or copied checkpoint changed')
        interface = compare_interfaces((FROZEN/'system_wrapper.hwh').read_bytes(),(artifacts/'system_wrapper.hwh').read_bytes())
        flow.write_json(out/'interface_comparison.json',interface)
        binding.update(status='EXPORTED_BOUND_CANDIDATE', hardware_exported=True,
                       source_checkpoint_reports_artifacts_binding='PASS',
                       parent_and_export_timing_metrics=before,candidate=candidate,
                       platform_bit_extraction=normalization,
                       software_interface_comparison=interface,
                       bit_header=flow.bit_header((artifacts/'system_wrapper.bit').read_bytes()),
                       timing_claim='PASS_UNDER_DECLARED_UNMEASURED_PIN_WINDOW',
                       board_qualification='NOT_RUN')
    except Exception as error:
        binding.update(status='FAILED',error=str(error))
    finally:
        frozen_after = {p.name:flow.sha(p) for p in FROZEN.iterdir() if p.is_file()}
        if frozen_before != frozen_after:
            binding.update(status='FAILED',error='Frozen runtime changed during export')
        flow.write_json(out/'binding.json',binding)
        paths=[p for p in out.rglob('*') if p.is_file() and p.name!='export_manifest.tsv']
        flow.write_inventory(out/'export_manifest.tsv',flow.inventory(paths,out))
    print(binding['status']+'; timing='+binding.get('timing_claim','see reports')+'; binding: '+str(out/'binding.json'))
    if binding['status'] != 'EXPORTED_BOUND_CANDIDATE':
        raise SystemExit(1)


if __name__=='__main__':
    main()
