"""Artifact checks are deliberately separate from scientific validation."""
import ast
import hashlib
import json
from pathlib import Path
import re
import numpy as np
from analyze_runs import ROOT, REPORT, weighted_window


def main():
    failures=[]
    for p in ROOT.glob('*.py'):
        try:ast.parse(p.read_text(encoding='utf-8-sig'))
        except SyntaxError as err:failures.append(str(err))
    for doc in [REPORT/'REPORT.md',REPORT/'METHOD.md',ROOT/'README.md',ROOT/'LINUX_ENVIRONMENT.md']:
        text=doc.read_text(encoding='utf-8')
        for dest in re.findall(r'\]\(([^)]+)\)',text):
            if '://' in dest or dest.startswith('#'):continue
            if not (doc.parent/dest.split('#')[0]).exists():failures.append(f'Missing link: {doc.name}: {dest}')
    for file in (REPORT/'results').glob('*.json'):
        try:json.loads(file.read_text(),parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
        except Exception as err:failures.append(f'Invalid JSON: {file.name}: {err}')
    data=json.loads((REPORT/'results/run_summary.json').read_text())
    selected=['fitted_B_empty','fitted_B_plate','fitted_B_urans_renumbered','fitted_F_empty',
              'fitted_F_urans','linux_B_urans','linux_F_urans','linux_F_empty_urans']
    for name in selected:
        item=data[name]
        if not item['ended']:failures.append(f'Run still active or incomplete: {name}')
        if len(item.get('last_grid25_Uy_ms',[]))!=25:failures.append(f'Incorrect probe count: {name}')
        history=[json.loads(s) for s in (ROOT/'cases'/name/'execution.jsonl').read_text().splitlines()]
        solver='pimpleFoam' if 'urans' in name else 'simpleFoam'
        solvers=[r for r in history if Path(r['log']).name.startswith('log.'+solver+'.')]
        if not solvers or solvers[-1]['exit_code']!=0:failures.append(f'No successful solver exit: {name}')
    for name in ['linux_B_urans','linux_F_urans','linux_F_empty_urans']:
        case=ROOT/'cases'/name
        provenance=json.loads((case/'linux_clone_provenance.json').read_text())
        meta=json.loads((case/'case_metadata.json').read_text())
        target_time=meta.get('target_time',provenance['source_time'])
        for field,expected in provenance['processor0_field_sha256'].items():
            # Initial checkpoint is retained separately from later saved fields.
            path=case/'processor0'/target_time/field
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                failures.append(f'Initial checkpoint mismatch: {name}/{field}')
    snap=json.loads((REPORT/'results/snapshot_comparison.json').read_text())
    calc=(np.array(snap['plate_Uy_ms'])/np.array(snap['empty_Uy_ms'])-1)*100
    if not np.allclose(calc,snap['point_difference_percent']):failures.append('Snapshot formula mismatch')
    test=weighted_window(np.array([0.,.2,1.]),np.array([[0.],[.4],[2.]]),.1,.9)
    if not np.isclose(test['mean'][0],1.):failures.append('Time-weighted mean self-test failed')
    mesh=json.loads((REPORT/'results/mesh_audit.json').read_text())
    if abs(mesh['blockage_error_percentage_points'])>.001:failures.append('Unexpected blockage mismatch')
    quality=json.loads((REPORT/'results/mesh_quality.json').read_text())
    if any(v['full_mesh_pass'] for v in quality.values()):failures.append('Review changed mesh status')
    result={'client_date':'2026-10-19','artifact_checks_passed':not failures,'failures':failures,
            'selected_solver_runs_exited_normally':not any('Run ' in f or 'solver' in f for f in failures),
            'aborted_pilot':'fitted_B_urans, intentionally terminated after pressure-iteration limit',
            'mesh_all_extended_checks_passed':False,'grid_convergence_established':False,
            'stationary_transient_statistics_established':False,'time_step_independence_established':False,
            'physical_validation_performed':False,'calibration_eligible':False}
    (REPORT/'results/validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    if failures:raise SystemExit(1)

if __name__=='__main__':main()
