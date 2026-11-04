import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description='Build the PYNQ ARM library and the shared PC game core.')
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--arm-cc',type=Path,required=True)
    parser.add_argument('--target-libs',type=Path,required=True)
    args=parser.parse_args()
    project=args.project.resolve()
    output=args.output.resolve()
    if not output.is_relative_to(project):
        parser.error('--output must be inside the source project')
    script=project/'color_test/software/vision_ps_baremetal/tools/build_beam_pynq.py'
    subprocess.run([sys.executable,'-B',str(script),'--output',str(output),
        '--arm-cc',str(args.arm_cc.resolve()),'--target-libs',str(args.target_libs.resolve())],
        cwd=project,check=True)
    subprocess.run([sys.executable,'-B','-c',
        'from pc_vision.board_native import build_board_host; print(build_board_host())'],
        cwd=project,check=True)


if __name__=='__main__':
    main()
