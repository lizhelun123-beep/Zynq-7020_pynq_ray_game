import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description='Run host-only PYNQ, UART v3 and web regressions.')
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--node',default='node')
    parser.add_argument('--web-python',type=Path)
    parser.add_argument('--host-library',type=Path)
    args=parser.parse_args()
    project=args.project.resolve()
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
    library=args.host_library.resolve() if args.host_library else project/'output/build/game_app/pynq_beam_c_5'/('beam_pynq_host.dll' if os.name=='nt' else 'libbeam_pynq_host.so')
    env['BEAM_PYNQ_HOST_LIBRARY']=str(library)
    env['BEAM_PYNQ_HARDWARE_DIR']=str(project/'output/build/game_app/pynq_beam_hardware_5')
    cases=[
        ('pynq_runtime',project,[sys.executable,'-B','-m','unittest','pynq_vision.tests.test_beam_runtime','pynq_vision.tests.test_display_retry','pynq_vision.tests.test_beam_hardware','-v']),
        ('admission',project,[sys.executable,'-B','-m','unittest','discover','-s','deployment/admission','-p','test_*.py','-v']),
        ('setup',project,[sys.executable,'-B','-m','unittest','discover','-s','deployment/setup','-p','test_*.py','-v']),
        ('wire',project,[sys.executable,'-B','-m','unittest','pc_vision.test_board_wire','-v']),
        ('web',project/'pc_vision_1_',[str(args.web_python.resolve()) if args.web_python else sys.executable,'-B','-m','unittest','pc_vision.test_web_game','-v']),
        ('frontend',project/'pc_vision_1_/pc_vision/web',[args.node,'--test','presentation.test.js']),
        ('frontend_syntax',project/'pc_vision_1_/pc_vision/web',[args.node,'--check','main.js']),
        ('runtime_inspect',project,[sys.executable,'-B','beam_v14.py','--inspect'])]
    results=[]
    for name,cwd,command in cases:
        run=subprocess.run(command,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
        (output/(name+'.log')).write_bytes(run.stdout)
        results.append(dict(name=name,exit_code=run.returncode,command=command))
        print(name,run.returncode,flush=True)
    (output/'results.json').write_text(json.dumps(dict(environment='host',hardware_operations=0,cases=results),indent=2)+'\n',encoding='utf-8')
    if any(item['exit_code'] for item in results):
        raise SystemExit(1)


if __name__=='__main__':
    main()
