"""Replay indexed original uploads without using detector output as labels."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile

from PIL import Image
import matplotlib
matplotlib.use('Agg')
from matplotlib.patches import Circle, Polygon
import matplotlib.pyplot as plt

from replay_photos import compiler_environment, parse


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_tsv(path, rows):
    with path.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, list(rows[0]), delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)


def compare_figure(photo, result, destination):
    with Image.open(photo) as source:
        frame = source.convert('RGB')
    fig, axes = plt.subplots(1, 2, figsize=(16, 5), layout='constrained')
    for ax, title in zip(axes, ['Original upload', 'C effective models and raw-scene rays']):
        ax.imshow(frame)
        ax.set(xlim=(0, 1280), ylim=(720, 0), title=title, xticks=[], yticks=[])
    ax = axes[1]
    colors = {'MIRROR': '#ffe66b', 'PORTAL_A': '#4dd4ff', 'PORTAL_B': '#ff9c4a',
              'TARGET': '#66ff9d', 'WALL': '#ffffff'}
    for model in result['models']:
        x, y = model['center']; a, b = model['axis']
        length, width = model['size']; color = colors.get(model['type'], 'white')
        if model['type'] == 'TARGET':
            ax.add_patch(Circle((x, y), width / 2, fill=False, edgecolor=color, linewidth=1.6))
        else:
            points = [(x+s*a*length/2-t*b*width/2, y+s*b*length/2+t*a*width/2)
                      for s, t in [(-1,-1),(1,-1),(1,1),(-1,1)]]
            ax.add_patch(Polygon(points, fill=False, edgecolor=color, linewidth=1.6))
            ax.arrow(x, y, a*length*.35, b*length*.35, color=color,
                     width=.6, head_width=7, length_includes_head=True)
        ax.text(x+5, y-14, model['type'], fontsize=7, color=color,
                bbox=dict(facecolor='black', alpha=.65, edgecolor='none', pad=1))
    for x1, y1, x2, y2 in result['segments']:
        ax.plot([x1,x2], [y1,y2], color='#ff4560', linewidth=2)
    fig.suptitle('Case {} | {} | {} detections, {} segments | no timed confirmation'.format(
        result['sample_id'], result['roster_status'], len(result['detections']), len(result['segments'])), fontsize=12)
    fig.savefig(destination, dpi=120)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    project = args.project.resolve(); index = args.index.resolve(); output = args.output.resolve()
    with index.open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    if not rows or len({r['sample_id'] for r in rows}) != len(rows):
        raise ValueError('empty index or duplicate case ID')
    for row in rows:
        photo = (index.parent / row['file']).resolve()
        if photo.parent != (index.parent / 'raw').resolve() or sha(photo) != row['sha256']:
            raise ValueError('source path/hash mismatch: ' + row['sample_id'])
    output.mkdir(parents=True, exist_ok=False)
    app = project / 'color_test/software/vision_ps_baremetal'
    config_path = project / 'pc_vision/game_config.json'
    config = json.loads(config_path.read_text(encoding='utf-8'))['real_scene']['beam']
    if config['detector_profile'] != 'restored_markers' or (config['width'], config['height']) != (1280, 720):
        raise ValueError('unsupported detector profile or resolution')
    probe = Path(__file__).with_name('test_data_probe.c')
    sources = [app/'src'/name for name in ['vision_ps.c','green_target_detector.c','ray_game.c']] + [probe]
    results = []; summary = []; build_command = []; compiler = ''
    with tempfile.TemporaryDirectory(prefix='raw_photo_replay_') as temporary:
        work = Path(temporary); compiler, env = compiler_environment(work)
        if not compiler:
            raise RuntimeError('MSVC or GCC required')
        exe = work / ('probe.exe' if os.name == 'nt' else 'probe')
        if os.name == 'nt':
            build_command = [compiler, '/nologo', '/utf-8', '/std:c11', '/O2', '/W4', '/WX',
                             '/D_CRT_SECURE_NO_WARNINGS', '/I'+str(app/'src'), *map(str,sources), '/Fe:'+str(exe)]
        else:
            build_command = [compiler, '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror',
                             '-I'+str(app/'src'), *map(str,sources), '-lm', '-o', str(exe)]
        build = subprocess.run(build_command, cwd=work, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=90)
        (output/'compile.log').write_bytes(build.stdout)
        build.check_returncode()
        for row in rows:  # attachment order from the index, never filesystem sort order
            photo = index.parent / row['file']
            with Image.open(photo) as frame:
                if frame.size != (1280, 720): raise ValueError('resolution mismatch')
                raw_bytes = frame.convert('RGB').tobytes('raw', 'BGR')
            raw = work/'frame.bgr'; raw.write_bytes(raw_bytes)
            command = [str(exe), str(raw), *map(str, config['emitter_point']),
                       *map(str, config['emitter_direction']), str(config['portal_b_exit_side'])]
            run = subprocess.run(command, cwd=work, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, timeout=60)
            text = run.stdout.decode('utf-8', errors='strict').replace('\r\n', '\n')
            (output/('case_'+row['sample_id']+'.log')).write_text(text, encoding='utf-8')
            run.check_returncode()
            detections, segments = parse(text)
            models = []
            for match in re.finditer(r'^MODEL (\w+) center=([-\d.]+),([-\d.]+) axis=([-\d.]+),([-\d.]+) size=([-\d.]+),([-\d.]+)$', text, re.M):
                kind, x, y, ax, ay, length, width = match.groups()
                models.append(dict(type=kind, center=[float(x),float(y)],
                                   axis=[float(ax),float(ay)], size=[float(length),float(width)]))
            expected = Counter(row['observed_types'].split(';')) if row['observed_types'] else Counter()
            actual = Counter(d['type'] for d in detections)
            declared_count = int(re.search(r'^count=(\d+)$',text,re.M).group(1))
            ray = re.search(r'segments=(\d+) interactions=(\d+) termination=(\d+)', text)
            assert declared_count == len(detections) == len(models)
            assert ray and int(ray[1]) == len(segments)
            missing = sorted((expected-actual).elements()); extra = sorted((actual-expected).elements())
            status = 'ROSTER_MATCH' if not missing and not extra else 'ROSTER_MISMATCH'
            result = dict(sample_id=row['sample_id'], upload_order=int(row['upload_order']),
                          image=photo.name, input_sha256=row['sha256'],
                          decoded_bgr888_sha256=hashlib.sha256(raw_bytes).hexdigest(),
                          expected_types=list(expected.elements()), roster_status=status,
                          missing_types=missing, extra_types=extra, detections=detections,
                          models=models, segments=segments, interactions=int(ray[2]),
                          termination_code=int(ray[3]),
                          hit_type_codes=[int(v) for v in re.findall(r'^HIT (\d+)$',text,re.M)])
            results.append(result)
            summary.append(dict(sample_id=row['sample_id'], image=photo.name,
                                expected_types=';'.join(expected.elements()),
                                detected_types=';'.join(d['type'] for d in detections),
                                roster_status=status, missing_types=';'.join(missing),
                                extra_types=';'.join(extra), detections=len(detections),
                                models=len(models), segments=len(segments),
                                interactions=int(ray[2]), termination_code=int(ray[3]),
                                pose_accuracy='NO_INDEPENDENT_GEOMETRY_LABELS'))
            compare_figure(photo,result,output/('case_'+row['sample_id']+'_comparison.png'))
            print(row['sample_id'], status, 'missing='+','.join(missing), 'extra='+','.join(extra), flush=True)
        (output/'probe.exe' if os.name=='nt' else output/'probe').write_bytes(exe.read_bytes())
    matched = sum(r['roster_status']=='ROSTER_MATCH' for r in results)
    payload = dict(environment='HOST_STATIC_C_REPLAY', platform=platform.platform(),
                   python=sys.version, compiler=compiler, compile_command=build_command,
                   index_sha256=sha(index), config_sha256=sha(config_path),
                   c_source_sha256={p.name:sha(p) for p in sources},
                   header_sha256={p.name:sha(p) for p in sorted((app/'src').glob('*.h'))},
                   pixel_format='BGR888', resolution=[1280,720], transformations='PNG decode to RGB then packed BGR; no resize/enhancement',
                   coordinate_space='UNCALIBRATED_CAMERA_PIXELS',
                   emitter_point=config['emitter_point'], emitter_direction=config['emitter_direction'],
                   portal_b_exit_side=config['portal_b_exit_side'],
                   label_scope='MANUALLY_REVIEWED_OBJECT_IDENTITIES_ONLY; nominal placement is not numeric pose ground truth',
                   timed_stability='NOT_TESTED_BY_STILL_PHOTOS', game_scoring='NOT_RUN',
                   hardware='NOT_RUN', reference_relationship='NO_SCREENSHOT_PAIRING',
                   totals=dict(images=len(results), roster_matches=matched, roster_mismatches=len(results)-matched),
                   images=results)
    (output/'results.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    write_tsv(output/'summary.tsv',summary)
    print('Complete: {}/{} identity rosters match; geometric accuracy and live timing not tested.'.format(matched,len(results)))


if __name__ == '__main__':
    main()
