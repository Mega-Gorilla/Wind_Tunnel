"""Execute native OpenFOAM locally with task-scoped environment and retained logs."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[0]
OF=ROOT/'tools/openfoam2606/msys64/home/ofuser/OpenFOAM/OpenFOAM-v2606'
BIN=OF/'platforms/win64MingwDPInt32Opt/bin'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('case');ap.add_argument('commands',nargs='+');args=ap.parse_args()
    case=(ROOT/'cases'/args.case).resolve()
    assert case.is_relative_to(ROOT/'cases') and case.is_dir()
    env=os.environ.copy()
    env.update(WM_PROJECT_DIR=OF.as_posix(),WM_PROJECT='OpenFOAM',WM_PROJECT_VERSION='v2606',
               FOAM_ETC=(OF/'etc').as_posix(),FOAM_SIGFPE='true')
    env['PATH']=str(BIN)+os.pathsep+env['PATH']
    for command in args.commands:
        parts=command.split(','); exe=parts.pop(0)
        cmd=[str(BIN/(exe+'.exe')),'-case',case.as_posix(),*parts]
        suffix=('_'+parts[parts.index('-func')+1]) if '-postProcess' in parts and '-func' in parts else ''
        if exe=='checkMesh' and '-allGeometry' in parts:suffix='_extended'
        log=case/f'log.{exe}{suffix}'
        began=time.time()
        print(f'START {case.name} {exe} {parts}',flush=True)
        with log.open('w',encoding='utf-8') as out:
            result=subprocess.run(cmd,cwd=case,env=env,stdout=out,stderr=subprocess.STDOUT)
        record=dict(command=cmd,exit_code=result.returncode,elapsed_s=time.time()-began,log=str(log))
        with (case/'execution.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(record)+'\n')
        print(json.dumps(record),flush=True)
        print('\n'.join(log.read_text(errors='replace').splitlines()[-18:]),flush=True)
        if result.returncode: raise SystemExit(result.returncode)
        if exe=='checkMesh' and '-allGeometry' not in parts and 'Mesh OK.' not in log.read_text(errors='replace'):
            raise SystemExit('Standard mesh quality check failed; do not launch a solver on this mesh.')

if __name__=='__main__':main()
