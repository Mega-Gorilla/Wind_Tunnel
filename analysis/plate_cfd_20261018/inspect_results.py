"""Read simulation logs and numerical output; no acceptance claim is inferred from exit status."""
import io
import json
import re
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[0]

def numeric(path):
    text=path.read_text().replace('(',' ').replace(')',' ')
    return np.atleast_2d(np.loadtxt(io.StringIO(text)))

def latest(folder):
    dirs=[p for p in folder.iterdir() if p.is_dir() and re.fullmatch(r'[\d.eE+-]+',p.name)]
    return max(dirs,key=lambda p:float(p.name))

def summary(case):
    result={'case':case.name}
    log=case/'log.simpleFoam'
    if not log.exists():return result
    text=log.read_text(errors='replace')
    ts=re.findall(r'^Time = (\S+)',text,re.M)
    result['iteration']=int(float(ts[-1])) if ts else None
    result['finished']='\nEnd\n' in text
    result['residual_control_converged']='SIMPLE solution converged' in text
    result['residuals']={}
    blocks=re.split(r'^Time = \S+\s*$',text,flags=re.M)
    completed=[b for b in blocks[1:] if 'ExecutionTime' in b]
    for fld,res in re.findall(r'Solving for (\w+), Initial residual = ([0-9.eE+-]+)',completed[-1] if completed else text):
        result['residuals'][fld]=max(result['residuals'].get(fld,0),float(res))
    checks=case/'log.checkMesh'
    if checks.exists():
        s=checks.read_text();result['standard_mesh_ok']='Mesh OK.' in s
        cells=re.search(r'^\s*cells:\s*(\d+)',s,re.M);result['cells']=int(cells[1]) if cells else None
    pp=case/'postProcessing'
    if not (pp/'gridProbes/0/U').exists():return result
    u=numeric(pp/'gridProbes/0/U'); uy=u[:,2::3]
    result['last_probe_iteration']=int(u[-1,0])
    result['tip_uy_last_ms']=uy[-1].tolist()
    end=uy[u[:,0]>=u[-1,0]-100]
    result['tip_last100_max_range_percent_Ubulk']=float(np.max(np.ptp(end,axis=0))/3*100)
    result['tip_last100_max_change_percent_Ubulk']=float(np.max(np.abs(end[-1]-end[0]))/3*100)
    p=numeric(pp/'inletP/0/surfaceFieldValue.dat')
    result['inlet_static_pressure_Pa']=float(p[-1,1]*1.2)
    endp=p[p[:,0]>=p[-1,0]-100,1]*1.2
    result['pressure_last100_range_Pa']=float(np.ptp(endp))
    qi=numeric(pp/'inletFlux/0/surfaceFieldValue.dat')[-1,1]
    qo=numeric(pp/'outletFlux/0/surfaceFieldValue.dat')[-1,1]
    result['inlet_Q_m3s']=float(-qi);result['flow_imbalance_percent']=float(abs(qi+qo)/abs(qi)*100)
    return result

if __name__=='__main__':
    results=[summary(p) for p in sorted((ROOT/'cases').iterdir()) if p.is_dir()]
    (ROOT/'status_snapshot.json').write_text(json.dumps(results,indent=2))
    for row in results:
        print(json.dumps({k:v for k,v in row.items() if k!='tip_uy_last_ms'},indent=2))
