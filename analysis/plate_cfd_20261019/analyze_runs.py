"""Summarize measured solver outputs; never substitute planned data for results."""
import argparse
import json
from pathlib import Path
import re
import numpy as np

ROOT=Path(__file__).resolve().parent
REPORT=ROOT.parents[1]/'Docs/tests/cfd/2026-10-19_fixed_plate_refined'
CASES=['fitted_B_empty','fitted_B_plate','fitted_B_urans',
       'fitted_B_urans_renumbered','fitted_F_empty','fitted_F_urans',
       'linux_B_urans','linux_F_urans','linux_F_empty_urans']


def series(case, function, filename='surfaceFieldValue.dat'):
    rows={}
    for file in sorted((case/'postProcessing'/function).glob('*/'+filename),key=lambda p:float(p.parent.name)):
        for line in file.read_text(errors='replace').splitlines():
            if not line.strip() or line.startswith('#'):
                continue
            vals=np.fromstring(line.replace('(',' ').replace(')',' '),sep=' ')
            if len(vals)>1 and np.all(np.isfinite(vals)):
                rows[float(vals[0])]=vals[1:]
    if not rows:
        return np.array([]),np.empty((0,0))
    times=np.array(sorted(rows))
    return times,np.array([rows[t] for t in times])


def weighted_window(t, data, begin, end):
    if len(t)<2 or begin<t[0]-1e-12 or end>t[-1]+1e-12 or end<=begin:
        return None
    ts=np.r_[begin,t[(t>begin)&(t<end)],end]
    ys=np.stack([np.interp(ts,t,data[:,i]) for i in range(data.shape[1])],axis=1)
    mean=np.trapezoid(ys,ts,axis=0)/(end-begin)
    variance=np.trapezoid((ys-mean)**2,ts,axis=0)/(end-begin)
    return dict(begin=float(begin),end=float(end),duration=float(end-begin),
                mean=mean.tolist(),resolved_temporal_std=np.sqrt(variance).tolist())


def summarize(name):
    case=ROOT/'cases'/name
    transient='urans' in name
    logs=sorted(case.glob('log.'+('pimpleFoam' if transient else 'simpleFoam')+'.*'))
    raw='\n'.join(p.read_text(errors='replace') for p in logs)
    time_values=re.findall(r'^Time = ([\d.eE+-]+)',raw,re.M)
    dt_values=[float(s) for s in re.findall(r'^deltaT = ([\d.eE+-]+)',raw,re.M)]
    co_values=[float(s) for s in re.findall(r'Courant Number mean: [\d.eE+-]+ max: ([\d.eE+-]+)',raw)]
    linear=re.findall(r'GAMG:  Solving for p, Initial residual = ([\d.eE+-]+), Final residual = ([\d.eE+-]+), No Iterations (\d+)',raw)
    t,p=series(case,'inletP')
    tu,u=series(case,'gridProbes','U')
    ti,qi=series(case,'inletFlux'); to,qo=series(case,'outletFlux')
    summary=dict(case=name,transient=transient,
                 last_started_time_or_iteration=float(time_values[-1]) if time_values else None,
                 last_monitor_time_or_iteration=float(t[-1]) if len(t) else None,
                 samples=len(t),solver_logs=[str(p.relative_to(ROOT)) for p in logs],
                 ended=bool(logs and 'Finalising parallel run' in logs[-1].read_text(errors='replace')))
    checkpoints=[]
    for path in (case/'processor0').glob('*/U'):
        try:checkpoints.append(float(path.parent.name))
        except ValueError:pass
    summary['latest_saved_full_field_time_or_iteration']=max(checkpoints) if checkpoints else None
    summary['last_monitor_has_full_field']=bool(len(t) and checkpoints and np.isclose(max(checkpoints),t[-1],rtol=1e-9,atol=1e-12))
    if len(t):
        summary['last_inlet_static_pressure_Pa']=float(p[-1,0]*1.2)
    if len(tu):
        summary['last_grid25_Uy_ms']=u[-1].reshape(-1,3)[:,1].tolist()
    if len(ti) and len(to):
        common=to[(to>=ti[0])&(to<=ti[-1])]
        out=np.interp(common,to,qo[:,0]); incoming=np.interp(common,ti,qi[:,0])
        imbalance=abs(out+incoming)/abs(incoming)*100
        summary['last_flux_imbalance_percent']=float(imbalance[-1])
        summary['maximum_flux_imbalance_percent']=float(max(imbalance))
    if dt_values:
        summary['deltaT_range_s']=[min(dt_values),max(dt_values)]
        summary['logged_max_Co']=max(co_values)
        summary['last_deltaT_s']=dt_values[-1]
    if linear:
        summary['max_pressure_linear_iterations']=max(int(v[2]) for v in linear)
        summary['pressure_solves_at_200_or_more']=sum(int(v[2])>=200 for v in linear)
        summary['last_pressure_linear_solve']=dict(initial=float(linear[-1][0]),final=float(linear[-1][1]),iterations=int(linear[-1][2]))
    if len(t)>2:
        if transient:
            begin=max(t[0], .01 if t[-1]>.015 else t[-1]/2)
            summary['exploratory_pressure_window_Pa']=weighted_window(t,p*1.2,begin,t[-1])
            if len(tu) and tu[-1]>=t[-1]:
                summary['exploratory_grid25_Uy_window_ms']=weighted_window(tu,u[:,1::3],begin,t[-1])
        else:
            mask=t>=max(t[0],t[-1]-30)
            summary['last30_inlet_static_pressure_range_Pa']=(np.array([min(p[mask,0]),max(p[mask,0])])*1.2).tolist()
    return summary


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--save',action='store_true');args=ap.parse_args()
    result={name:summarize(name) for name in CASES if (ROOT/'cases'/name).exists()}
    if args.save:
        (REPORT/'results').mkdir(parents=True,exist_ok=True)
        (REPORT/'results/run_summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    for name,item in result.items():
        print(json.dumps({k:item[k] for k in ['case','last_monitor_time_or_iteration','samples','ended','last_inlet_static_pressure_Pa','last_flux_imbalance_percent','last_deltaT_s'] if k in item}))


if __name__=='__main__':main()
