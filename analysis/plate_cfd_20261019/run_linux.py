"""Restricted, case-scoped Docker runner with local append-only provenance."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import time

ROOT=Path(__file__).resolve().parent
IMAGE='opencfd/openfoam-run@sha256:4229997e74defb81548222d511b8e3b95b98305e5df41b8e88b031813fe47eeb'


def main():
    ap=argparse.ArgumentParser();ap.add_argument('case');ap.add_argument('commands',nargs='+')
    ap.add_argument('--ranks',type=int,default=0)
    ap.add_argument('--cpu-start',type=int,default=0);args=ap.parse_args()
    case=(ROOT/'cases'/args.case).resolve()
    assert case.is_relative_to(ROOT/'cases') and case.is_dir() and args.case.startswith('linux_')
    for command in args.commands:
        parts=command.split(',')
        app=[parts[0],'-case','/case',*parts[1:]]
        if args.ranks:app=['mpirun','--allow-run-as-root','--oversubscribe','-np',str(args.ranks),*app,'-parallel']
        cmd=['docker','run','--rm','--name','wt-cfd-'+args.case.lower().replace('_','-'),
             '--network','none','--cpuset-cpus',f'{args.cpu_start}-{args.cpu_start+max(args.ranks,2)-1}','--memory','8g','--shm-size','512m',
             '--cap-drop','ALL','--security-opt','no-new-privileges',
             '--mount',f'type=bind,source={case.as_posix()},target=/case',
             '--workdir','/case','--entrypoint','/bin/bash',IMAGE,'-lc',shlex.join(app)]
        log=case/f'log.{parts[0]}.{time.time_ns()}'; started=time.time()
        print('START',args.case,command,'ranks',args.ranks,flush=True)
        with log.open('w',encoding='utf-8') as out:
            result=subprocess.run(cmd,stdout=out,stderr=subprocess.STDOUT)
        record=dict(command=cmd,exit_code=result.returncode,elapsed_s=time.time()-started,log=str(log),image=IMAGE)
        with (case/'execution.jsonl').open('a',encoding='utf-8') as out:out.write(json.dumps(record)+'\n')
        raw=log.read_text(errors='replace')
        print(json.dumps(record),flush=True);print('\n'.join(raw.splitlines()[-24:]),flush=True)
        if result.returncode:raise SystemExit(result.returncode)
        if parts[0]=='checkMesh' and 'Mesh OK.' not in raw:
            if not ((case/'mesh_diagnostic_acceptance.json').exists() and 'Failed 1 mesh checks.' in raw
                    and 'Cells with small determinant' in raw and 'Concave cell check OK.' in raw
                    and 'Face tets OK.' in raw and 'Face interpolation weight check OK.' in raw
                    and 'Face volume ratio check OK.' in raw):
                raise SystemExit('Linux mesh validation failed beyond reviewed diagnostic warning')
            print('DIAGNOSTIC ONLY: small determinant warning remains.',flush=True)

if __name__=='__main__':main()
