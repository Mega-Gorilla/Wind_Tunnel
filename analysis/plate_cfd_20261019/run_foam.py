"""Run the existing local native OpenFOAM with append-only command provenance."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent
OF = ROOT.parent/'plate_cfd_20261018/tools/openfoam2606/msys64/home/ofuser/OpenFOAM/OpenFOAM-v2606'
BIN = OF/'platforms/win64MingwDPInt32Opt/bin'


def run(case, command, ranks=0):
    env = os.environ.copy()
    env.update(WM_PROJECT_DIR=OF.as_posix(), WM_PROJECT='OpenFOAM', WM_PROJECT_VERSION='v2606',
               FOAM_ETC=(OF/'etc').as_posix(), FOAM_SIGFPE='true')
    env['PATH'] = str(BIN)+os.pathsep+env['PATH']
    parts = command.split(',')
    cmd = [str(BIN/(parts[0]+'.exe')), '-case', case.as_posix(), *parts[1:]]
    if ranks:
        parallel = ROOT/'tools/parallel_bin'
        env['PATH'] = str(parallel)+os.pathsep+env['PATH']
        env['MSMPI_BIN'] = str(parallel)
        env['MSMPI_LOCAL_ONLY'] = '1'
        cmd = [str(parallel/'mpiexec.exe'), '-n', str(ranks),
               str(parallel/(parts[0]+'.exe')), '-case', case.as_posix(), '-parallel', *parts[1:]]
    log = case/(f'log.{parts[0]}.'+str(time.time_ns()))
    print('START', case.name, command, flush=True)
    began = time.time()
    with log.open('w', encoding='utf-8') as out:
        result = subprocess.run(cmd, cwd=case, env=env, stdout=out, stderr=subprocess.STDOUT)
    record = dict(command=cmd, exit_code=result.returncode, elapsed_s=time.time()-began, log=str(log))
    with (case/'execution.jsonl').open('a', encoding='utf-8') as out:
        out.write(json.dumps(record)+'\n')
    print(json.dumps(record), flush=True)
    contents = log.read_text(errors='replace')
    print('\n'.join(contents.splitlines()[-30:]), flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)
    if parts[0]=='checkMesh' and 'Mesh OK.' not in contents:
        # A long, straight extruded slit can be convex and valid yet fail the
        # isotropy-sensitive determinant threshold. This is NOT a full pass.
        # Permit only explicitly reviewed diagnostic runs, never hide the flag.
        reviewed = case/'mesh_diagnostic_acceptance.json'
        permitted = (reviewed.exists() and 'Failed 1 mesh checks.' in contents
                     and 'Cells with small determinant' in contents
                     and 'Concave cell check OK.' in contents and 'Face tets OK.' in contents
                     and 'Face interpolation weight check OK.' in contents
                     and 'Face volume ratio check OK.' in contents)
        if not permitted:
            raise SystemExit('Mesh validation did not pass. Solver launch blocked.')
        print('DIAGNOSTIC ONLY: reviewed anisotropic-cell determinant warning remains.', flush=True)


if __name__ == '__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('case'); ap.add_argument('commands', nargs='+'); ap.add_argument('--ranks', type=int, default=0)
    args=ap.parse_args()
    case=(ROOT/'cases'/args.case).resolve()
    assert case.is_relative_to(ROOT/'cases') and case.is_dir()
    for command in args.commands:
        run(case, command, args.ranks)
