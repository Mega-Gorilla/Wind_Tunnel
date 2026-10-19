"""Separate axial-spacing sensitivity case; retains section shape/connectivity.

This is not an automatic accuracy improvement. A 0.5 mm first axial layer is
tested against B's 0.1 mm layer. Initial U/p/k/omega/nut are stretched with the
cell numbering; phi is recomputed. Initial transients must be discarded.
"""
from pathlib import Path
import json
import shutil
import re
import numpy as np
from scipy.optimize import brentq
from build_fitted import header

ROOT = Path(__file__).resolve().parent
source=ROOT/'cases/fitted_B_urans'
target=ROOT/'cases/fitted_F_urans'
if target.exists():
    raise RuntimeError('Target already exists')
shutil.copytree(source/'constant',target/'constant')
shutil.copytree(ROOT/'cases/fitted_B_urans_renumbered/system',target/'system')
(target/'0').mkdir()
for name in ['U','p','k','omega','nut']:
    shutil.copy2(source/'0'/name,target/'0'/name)
shutil.copy2(source/'mesh_diagnostic_acceptance.json',target/'mesh_diagnostic_acceptance.json')
meta=json.loads((source/'case_metadata.json').read_text())
ys=np.array(meta['axial_stations_m'])


def spacing(n, length):
    def widths(r):
        return np.minimum(.0005*r**np.arange(n),.012)
    r=brentq(lambda r:widths(r).sum()-length,1,3)
    return widths(r)


up_n=int((ys<0).sum())
down_n=int((ys>.005+1e-12).sum())
new_up=-np.cumsum(np.r_[0,spacing(up_n,.2)])[::-1]
new_down=.005+np.cumsum(spacing(down_n,.195))
new=np.r_[new_up[:-1],ys[(ys>=0)&(ys<=.005+1e-12)],new_down]
assert len(new)==len(ys) and np.all(np.diff(new)>0)
path=target/'constant/polyMesh/points'
text=path.read_text()
rows=re.findall(r'^\(([^()]+)\)$',text,re.M)
points=np.array([[float(v) for v in row.split()] for row in rows])
assert len(points)==meta['points']
indices=np.argmin(abs(points[:,1,None]-ys),axis=1)
assert np.max(abs(points[:,1]-ys[indices]))<1e-10
points[:,1]=new[indices]
with path.open('w',encoding='ascii') as out:
    out.write(header('points','vectorField')+f'{len(points)}\n(\n')
    out.writelines(f'({x:.12g} {y:.12g} {z:.12g})\n' for x,y,z in points)
    out.write(')\n')
meta.update(case=target.name,axial_stations_m=new.tolist(),source_case=source.name,
            first_axial_layer_mm=.5,axial_cap_mm=12,
            initial_field_mapping='same-cell-index axial stretch, phi recomputed; discard startup',
            validation_status='axial-spacing sensitivity diagnostic; not a mesh-converged solution')
(target/'case_metadata.json').write_text(json.dumps(meta,indent=2))
print(json.dumps(dict(case=target.name,layers=len(new)-1,min_axial_mm=min(np.diff(new))*1000,max_axial_mm=max(np.diff(new))*1000)))
