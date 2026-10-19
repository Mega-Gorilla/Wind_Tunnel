"""Sanity checks for the final numerical evidence bundle."""
import json
from pathlib import Path
import numpy as np
from inspect_results import numeric, latest, summary
from report_paths import RESULTS_ROOT

ROOT=Path(__file__).resolve().parents[0]
selected=['coarse_empty','medium_empty','coarse_repaired_plate','medium_repaired_plate']
checks=[]
geo=json.loads((ROOT/'geometry/geometry_summary.json').read_text())
assert abs(geo['duct_area_mm2']-6271.312)/6271.312 < .0001
assert 0 < geo['plate_blockage_fraction'] < 1
assert not geo['cad_modified']
for name in selected:
    case=ROOT/'cases'/name
    status=summary(case)
    assert status['finished'],(name,'solver is still running')
    assert status['standard_mesh_ok'],(name,'standard mesh quality failed')
    folder=latest(case/'postProcessing/pointSamples')
    values=numeric(folder/'grid25_k_p_U.xy')
    assert len(values)==25 and np.isfinite(values).all(),(name,'invalid point samples')
    assert abs(float(folder.name)-status['iteration'])<1e-9,(name,'sample time != final iteration')
    assert np.allclose(values[:,1],-.0550529657691,atol=1e-9)
    assert 0<values[:,6].min()<values[:,6].max()<6,(name,'unexpected upstream flow')
    assert status['flow_imbalance_percent']<.1,(name,'flux imbalance >= 0.1%')
    mesh=json.loads((case/'mesh_metrics.json').read_text())
    checks.append({'case':name,'artifacts_consistent':True,'strict_residual_target_met':status['residual_control_converged'],
                   'inlet_area_mm2':mesh['patches']['inlet']['surface_area_mm2'],
                   'flux_imbalance_percent':status['flow_imbalance_percent']})
for label in ['coarse','medium']:
    a=next(x for x in checks if x['case']==label+'_empty')
    b=next(x for x in checks if x['case']==label+'_repaired_plate')
    assert abs(a['inlet_area_mm2']-b['inlet_area_mm2'])<1e-6
result={'artifact_integrity_checks_passed':True,'physical_validation_performed':False,
        'all_cases_strictly_converged':all(c['strict_residual_target_met'] for c in checks),
        'calibration_eligible':False,'case_checks':checks}
(RESULTS_ROOT/'validation.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
