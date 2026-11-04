"""从可读源码生成板端支持工具归档，保留已有输出。"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=('ready', 'deploy'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.kind == 'ready':
        folder = ROOT / 'deployment/admission'
        paths = {'__main__.py': folder / '__main__.py', 'ready.py': folder / 'ready.py',
                 'beam_admission.new': ROOT / 'pynq_vision/beam_admission.py'}
    else:
        folder = ROOT / 'deployment/setup'
        paths = {name: folder / name for name in ('__main__.py', 'deploy.py', 'prepare_console.py')}
    files = {name: path.read_bytes() for name, path in paths.items()}
    with args.output.open('xb') as stream:
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, raw in files.items():
                info = zipfile.ZipInfo(name, (2026, 11, 2, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, raw)
    with zipfile.ZipFile(str(args.output)) as archive:
        if archive.testzip() is not None or any(archive.read(name) != raw for name, raw in files.items()):
            raise RuntimeError('归档内容与源码不一致')
    print(json.dumps({'file': str(args.output),
                      'sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      'members': list(files)}))


if __name__ == '__main__':
    main()
