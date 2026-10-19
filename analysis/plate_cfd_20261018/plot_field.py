"""Plot a sampled axial section with the actual CAD solid masked out."""
import argparse
from pathlib import Path
import numpy as np
import trimesh
from shapely.geometry import Polygon, GeometryCollection
from shapely import contains_xy
from scipy.interpolate import griddata
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from inspect_results import numeric,latest
from report_paths import RESULTS_ROOT

ROOT=Path(__file__).resolve().parents[0]
ap=argparse.ArgumentParser();ap.add_argument('case');ap.add_argument('--status',default='Preliminary CFD screening');args=ap.parse_args()
case=ROOT/'cases'/args.case
folder=latest(case/'postProcessing/sample')
arr=numeric(folder/'longitudinal_k_p_U.xy')
mesh=trimesh.load_mesh(ROOT/'geometry/plate-3.stl')
section=mesh.section(plane_origin=[0,72.5,122.5],plane_normal=[1,0,0])
solid=GeometryCollection()
for ring in section.discrete:
    coords=ring[:,[1,2]]-np.array([70,122.5])
    poly=Polygon(coords)
    if poly.is_valid:solid=solid.symmetric_difference(poly)
y=np.linspace(-140,140,561);z=np.linspace(-38,38,153);Y,Z=np.meshgrid(y,z)
uy=griddata(arr[:,[1,2]]*1000,arr[:,6],(Y,Z),method='linear')
uy[contains_xy(solid,Y,Z)]=np.nan
fig,ax=plt.subplots(figsize=(12,4.4),layout='constrained')
cm=plt.get_cmap('viridis').copy();cm.set_bad('#cccccc')
im=ax.pcolormesh(Y,Z,uy,shading='auto',cmap=cm,vmin=-1,vmax=6)
ax.axvline(-55.0529658,color='white',ls='--',lw=1.3)
ax.text(-57,33,'Comparison plane',color='white',ha='right',fontsize=9)
ax.axvspan(0,5,facecolor='none',edgecolor='white',lw=.6)
ax.annotate('Flow',(-95,0),(-128,0),color='white',arrowprops={'arrowstyle':'->','color':'white'},va='center')
ax.set(xlabel='Distance from plate upstream face [mm]',ylabel='Height from centre [mm]',
       title=f'{args.status}\nX = 0 section / {args.case}, iteration {folder.name} / nominal inlet 3 m/s')
ax.set_aspect('equal');fig.colorbar(im,ax=ax,label='Axial velocity Uy [m/s]',shrink=.75,extend='both')
dest=RESULTS_ROOT;dest.mkdir(parents=True,exist_ok=True)
path=dest/f'{args.case}_axial_section.png';fig.savefig(path,dpi=170)
print(path)
