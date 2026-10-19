"""Create a separate physical-time URANS case from a saved steady checkpoint.

The source remains intact. Processor field checkpoints are relabelled t=0;
steady iteration numbers must never be interpreted as physical seconds.
"""
from pathlib import Path
import argparse
import json
import shutil
from build_fitted import put

ROOT = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', default='fitted_B_plate')
    ap.add_argument('--target', default='fitted_B_urans')
    ap.add_argument('--end', type=float, default=.02)
    args=ap.parse_args()
    source, target=ROOT/'cases'/args.source, ROOT/'cases'/args.target
    if target.exists():
        raise RuntimeError('Refusing to overwrite a transient case')
    processors=sorted(source.glob('processor[0-9]*'))
    times=[p.name for p in processors[0].iterdir() if p.is_dir() and p.name.replace('.','',1).isdigit()]
    latest=max(times, key=float)
    assert all((p/latest/'U').exists() for p in processors)
    for directory in ['constant','system','0']:
        shutil.copytree(source/directory,target/directory)
    for processor in processors:
        dest=target/processor.name
        shutil.copytree(processor/'constant',dest/'constant')
        (dest/'0').mkdir()
        for name in ['U','p','k','omega','nut','phi']:
            if (processor/latest/name).exists():
                shutil.copy2(processor/latest/name,dest/'0'/name)
    for name in ['case_metadata.json','mesh_diagnostic_acceptance.json']:
        shutil.copy2(source/name,target/name)
    metadata=json.loads((target/'case_metadata.json').read_text())
    metadata.update(case=args.target, solver='pimpleFoam', model='transient kOmegaSST URANS diagnostic',
                    seed_case=args.source, seed_steady_iteration=latest,
                    time_origin='steady checkpoint relabelled physical t=0; not a converged flow guarantee',
                    ranks=len(processors), initial_pilot_end_s=args.end)
    (target/'case_metadata.json').write_text(json.dumps(metadata,indent=2))
    schemes=(target/'system/fvSchemes').read_text().replace('default steadyState','default backward').replace('bounded Gauss','Gauss')
    (target/'system/fvSchemes').write_text(schemes,encoding='ascii')
    put(target,'system/fvSolution','''
solvers {
 p { solver GAMG; tolerance 1e-7; relTol .03; smoother DICGaussSeidel; nPreSweeps 2; nPostSweeps 2; nFinestSweeps 2; }
 pFinal { $p; relTol 0; }
 "(U|k|omega)" { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol .05; }
 "(U|k|omega)Final" { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0; }
}
PIMPLE { nOuterCorrectors 1; nCorrectors 2; nNonOrthogonalCorrectors 0; momentumPredictor yes; }
relaxationFactors { equations { ".*" 1; } }
''')
    # Retain the same 25 interpolated probes, flux and pressure monitors.
    old_control=(source/'system/controlDict').read_text()
    functions=old_control[old_control.index('functions {')+len('functions {'):].rsplit('}',1)[0]
    functions+='''
wakeProbes { type probes; libs ("libsampling.dll"); interpolationScheme cellPoint;
 writeControl timeStep; writeInterval 1; fields (U p k);
 probeLocations ((0 .02 0) (.008 .02 0) (0 .05 0) (0 -.02 0)); }
statistics { type fieldAverage; libs ("libfieldFunctionObjects.dll");
 timeStart .01; restartOnRestart false; restartOnOutput false;
 fields (U { mean on; prime2Mean on; base time; } p { mean on; prime2Mean off; base time; }); }
'''
    put(target,'system/controlDict',f'''
application pimpleFoam; startFrom latestTime; startTime 0; stopAt endTime; endTime {args.end};
deltaT .0001; adjustTimeStep yes; maxCo 1; maxDeltaT .0005;
writeControl adjustableRunTime; writeInterval .005; purgeWrite 3;
writeFormat binary; writePrecision 10; writeCompression off; timeFormat general; timePrecision 10;
runTimeModifiable true; functions {{ {functions} }}
''')
    print(json.dumps(dict(target=str(target),seed_iteration=latest,ranks=len(processors),end_s=args.end),indent=2))


if __name__=='__main__':
    main()
