import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon


def compiler_environment(work):
    if os.name!='nt':
        return shutil.which('gcc'),os.environ.copy()
    vswhere=Path('C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe')
    install=subprocess.check_output([str(vswhere),'-latest','-products','*',
        '-requires','Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
        '-property','installationPath'],text=True).strip()
    command=work/'environment.cmd'
    command.write_text('@echo off\ncall "'+install+'/VC/Auxiliary/Build/vcvars64.bat" >nul\nset\n',encoding='utf-8')
    text=subprocess.check_output(['cmd.exe','/d','/c',str(command)],text=True,cwd=work)
    env=dict(line.split('=',1) for line in text.splitlines() if '=' in line and not line.startswith('='))
    return shutil.which('cl.exe',path=next(v for k,v in env.items() if k.lower()=='path')),env


def parse(text):
    text=text.replace('\r\n','\n')
    detections=[]
    pattern=r'^(\w+) center=(\d+),(\d+) angle=(-?\d+) bbox=([\d,]+) axis=([-\d.]+),([-\d.]+) size=([\d.]+),([\d.]+)$'
    for line in text.splitlines():
        match=re.match(pattern,line)
        if match:
            kind,x,y,angle,bbox,ax,ay,major,minor=match.groups()
            detections.append(dict(type=kind,center=[int(x),int(y)],angle=int(angle),
                axis=[float(ax),float(ay)],size=[float(major),float(minor)]))
    segments=[]
    for match in re.finditer(r'^segment\d+ ([-\d.]+),([-\d.]+) -> ([-\d.]+),([-\d.]+)$',text,re.M):
        segments.append([float(x) for x in match.groups()])
    return detections,segments


def figure(photo,result,destination):
    frame=Image.open(photo).convert('RGB')
    fig,axes=plt.subplots(1,2,figsize=(14,4.5),layout='constrained')
    for ax,title in zip(axes,['Reference screen image','Current C detector and ray trace']):
        ax.imshow(frame);ax.set_xlim(0,1280);ax.set_ylim(720,0);ax.set_title(title,fontsize=12)
        ax.set_xticks([]);ax.set_yticks([])
    ax=axes[1]
    colors={'PORTAL_A':'#4dd4ff','PORTAL_B':'#ff9c4a','MIRROR':'#ffe66b','TARGET':'#66ff9d','WALL':'white'}
    for item in result['detections']:
        x,y=item['center'];a,b=item['axis'];length,width=item['size'];color=colors.get(item['type'],'white')
        points=[(x+s*a*length/2-t*b*width/2,y+s*b*length/2+t*a*width/2) for s,t in [(-1,-1),(1,-1),(1,1),(-1,1)]]
        ax.add_patch(Polygon(points,fill=False,edgecolor=color,linewidth=1.8))
        ax.scatter([x],[y],s=12,c=color)
        ax.text(x+5,y-14,item['type'],fontsize=7,color=color,bbox=dict(facecolor='black',alpha=.65,edgecolor='none',pad=1))
    for x1,y1,x2,y2 in result['segments']:
        ax.plot([x1,x2],[y1,y2],color='#ff4560',linewidth=2.6)
    fig.suptitle(photo.stem+' | {} objects, {} ray segments'.format(len(result['detections']),len(result['segments'])),fontsize=13)
    fig.savefig(destination,dpi=150);plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description='Replay archived photographs through the delivered C detector.')
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    project=args.project.resolve();data=args.data.resolve();output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    app=project/'color_test/software/vision_ps_baremetal'
    results=[]
    expected_counts=[5,5,3,2,4,2]
    with tempfile.TemporaryDirectory(prefix='photo_replay_') as temporary:
        work=Path(temporary);cc,env=compiler_environment(work)
        if not cc: raise RuntimeError('MSVC or GCC is required')
        exe=work/('probe.exe' if os.name=='nt' else 'probe')
        sources=[app/'src'/name for name in ['vision_ps.c','green_target_detector.c','ray_game.c']]
        sources.append(app/'tests/restored_detection_probe.c')
        if os.name=='nt':
            command=[cc,'/nologo','/utf-8','/std:c11','/O2','/W4','/WX','/D_CRT_SECURE_NO_WARNINGS','/I'+str(app/'src'),*map(str,sources),'/Fe:'+str(exe)]
        else:
            command=[cc,'-std=c99','-O2','-Wall','-Wextra','-Werror','-I'+str(app/'src'),*map(str,sources),'-lm','-o',str(exe)]
        build=subprocess.run(command,cwd=work,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
        (output/'compile.log').write_bytes(build.stdout);build.check_returncode()
        for photo in sorted(data.glob('*.png')):
            image=Image.open(photo).convert('RGB')
            if image.size!=(1280,720): raise ValueError('expected 1280x720: '+str(photo))
            raw=work/'frame.bgr';raw.write_bytes(image.tobytes('raw','BGR'))
            run=subprocess.run([str(exe),str(raw)],cwd=work,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
            text=run.stdout.decode('utf-8',errors='replace')
            (output/(photo.stem+'.log')).write_text(text,encoding='utf-8');run.check_returncode()
            detections,segments=parse(text)
            reference=expected_counts[int(photo.stem[-2:])-1] if photo.stem.startswith('screen_') else None
            result=dict(image=photo.name,detections=detections,segments=segments,
                reference_count=reference,reference_kind='historical C output; not independent coordinate ground truth',
                status=('PASS_COUNT_PORTALS_AND_RAYS' if len(detections)==reference and len(segments)==2 and {'PORTAL_A','PORTAL_B'}<=set(d['type'] for d in detections)
                        else 'DIFFERENT_FROM_REFERENCE') if reference is not None else 'OBSERVED_WITHOUT_CURRENT_LABELS')
            results.append(result);figure(photo,result,output/(photo.stem+'_comparison.png'))
            print(photo.name,len(detections),len(segments),result['status'],flush=True)
    (output/'results.json').write_text(json.dumps(dict(
        environment='host C replay',pixel_format='BGR888',resolution=[1280,720],
        timed_stability='NOT_TESTED_BY_STILL_PHOTO',raw_camera_frames=False,
        pose_accuracy='NO_INDEPENDENT_GROUND_TRUTH',images=results),indent=2)+'\n',encoding='utf-8')
    if any(r['status']=='DIFFERENT_FROM_REFERENCE' for r in results): raise SystemExit(1)


if __name__=='__main__':
    main()
