"""Traceable diagnostic plots: physical time is never mixed with iteration."""
import json
import re
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from mesh_section import geometry, rings, OLD
from analyze_runs import ROOT, REPORT, CASES, series, summarize
import trimesh
from shapely import affinity
from shapely.geometry import LineString

plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
COLORS={'fitted_B_urans_renumbered':'#6a65a9','fitted_F_urans':'#156c83',
        'linux_F_urans':'#db7531','linux_F_empty_urans':'#3a8a52'}
LABELS={'fitted_B_urans_renumbered':'Mesh B, Windows, plate',
        'fitted_F_urans':'Mesh F, Windows, plate',
        'linux_F_urans':'Mesh F, Linux continuation, plate',
        'linux_F_empty_urans':'Mesh F, Linux, empty'}


def write_json(name,data):
    (REPORT/'results'/name).write_text(json.dumps(data,indent=2,allow_nan=False),encoding='utf-8')


def quality():
    result={}
    for name in ['fitted_B_plate','fitted_F_urans','fitted_F_empty','linux_F_urans','linux_F_empty_urans']:
        logs=sorted((ROOT/'cases'/name).glob('log.checkMesh.*'))
        if not logs:continue
        raw=logs[-1].read_text(errors='replace')
        def value(pattern):
            found=re.search(pattern,raw)
            return float(found[1]) if found else None
        result[name]={'log':str(logs[-1].relative_to(ROOT)),
            'cells':value(r'\n\s*cells:\s+(\d+)'),
            'max_nonorthogonality_deg':value(r'Mesh non-orthogonality Max:\s*([\d.eE+-]+)'),
            'max_skewness':value(r'Max skewness =\s*([\d.eE+-]+)'),
            'max_aspect_ratio':value(r'Max aspect ratio =\s*([\d.eE+-]+)'),
            'small_determinant_cells':value(r'Cells with small determinant.*number of cells:\s*(\d+)'),
            'concave_check_pass':'Concave cell check OK.' in raw,
            'full_mesh_pass':'Mesh OK.' in raw,'one_failed_check':'Failed 1 mesh checks.' in raw}
    write_json('mesh_quality.json',result)


def thickness():
    duct,mid=geometry()
    mesh=trimesh.load_mesh(OLD/'geometry/plate-3.stl')
    data=[]
    for y in [70.01,71.25,72.5,73.75,74.99]:
        polys=rings(mesh,y);outer=max(polys,key=lambda p:p.area);solid=outer
        for p in polys:
            if p is not outer:solid=solid.difference(p)
        solid=affinity.translate(solid,yoff=-122.5).intersection(duct)
        data.append({'source_Y_mm':y,'blocked_area_mm2':solid.area,
                     'symmetric_difference_from_midpoint_mm2':solid.symmetric_difference(mid).area})
    write_json('thickness_section_audit.json',{'model':'midpoint section extruded over 5 mm',
        'source_section_samples':data,'note':'Five sampled planes, not a proof for every CAD section.'})


def plots():
    fig,axs=plt.subplots(2,2,figsize=(12.5,8),layout='constrained')
    for name in ['fitted_B_plate','fitted_F_empty']:
        t,p=series(ROOT/'cases'/name,'inletP')
        axs[0,0].plot(t,p[:,0]*1.2,label='Mesh B plate' if 'plate' in name else 'Mesh F empty')
    axs[0,0].set(xlabel='SIMPLE iteration (not seconds)',ylabel='Inlet static pressure [Pa]',title='Steady iterations: not strictly converged')
    axs[0,0].legend(fontsize=8)
    for name in COLORS:
        case=ROOT/'cases'/name;t,p=series(case,'inletP')
        if not len(t):continue
        axs[0,1].plot(t*1000,p[:,0]*1.2,color=COLORS[name],label=LABELS[name])
        ti,qi=series(case,'inletFlux');to,qo=series(case,'outletFlux')
        if len(ti) and len(to):
            common=to[(to>=ti[0])&(to<=ti[-1])]
            incoming=np.interp(common,ti,qi[:,0]); outgoing=np.interp(common,to,qo[:,0])
            imbalance=abs(incoming+outgoing)/abs(incoming)*100
            axs[1,0].semilogy(common*1000,np.maximum(imbalance,1e-10),color=COLORS[name])
        tu,u=series(case,'gridProbes','U')
        if len(tu):axs[1,1].plot(tu*1000,u[:,12*3+1],color=COLORS[name])
    axs[0,1].set(xlabel='Physical time from each initialization [ms]',ylabel='Inlet static pressure [Pa]',title='URANS startup, not a stationary average')
    axs[0,1].legend(fontsize=7.5)
    axs[1,0].set(xlabel='Physical time [ms]',ylabel='Inlet / outlet flux imbalance [%]',title='Mass conservation does not certify accuracy')
    axs[1,1].set(xlabel='Physical time [ms]',ylabel='Centre-point streamwise velocity [m/s]',title='Probe plane 55.053 mm upstream of plate')
    fig.suptitle('CFD diagnostics only | 400 mm / 3 m/s = 133 ms nominal flow-through time',fontsize=12)
    fig.savefig(REPORT/'figures/convergence_diagnostics.png',dpi=170);plt.close(fig)

    # Same-mesh snapshots are useful for diagnosing bias, but not a converged effect estimate.
    _,u0=series(ROOT/'cases/fitted_F_empty','gridProbes','U')
    t1,u1=series(ROOT/'cases/fitted_F_urans','gridProbes','U')
    empty=u0[-1,1::3].reshape(5,5);plate=u1[-1,1::3].reshape(5,5)
    effect=(plate/empty-1)*100
    fig,axs=plt.subplots(1,3,figsize=(12.5,4.4),layout='constrained')
    vmin=min(empty.min(),plate.min());vmax=max(empty.max(),plate.max())
    m=None
    for ax,data,title in zip(axs[:2],[empty,plate],['Empty / steady iteration 150',f'Plate / startup t={t1[-1]*1000:.2f} ms']):
        m=ax.imshow(data,origin='upper',extent=[-40,40,-40,40],vmin=vmin,vmax=vmax,cmap='viridis')
        ax.set(title=title,xlabel='X [mm]',ylabel='Z [mm]',xticks=[-32,-16,0,16,32],yticks=[-32,-16,0,16,32])
    fig.colorbar(m,ax=axs[:2],label='Uy [m/s]',shrink=.8)
    limit=max(abs(effect.min()),abs(effect.max()))
    m=axs[2].imshow(effect,origin='upper',extent=[-40,40,-40,40],vmin=-limit,vmax=limit,cmap='RdBu_r')
    axs[2].set(title='Snapshot difference, not calibration',xlabel='X [mm]',ylabel='Z [mm]',xticks=[-32,-16,0,16,32],yticks=[-32,-16,0,16,32])
    for row in range(5):
        for col in range(5):axs[2].text(-32+16*col,32-16*row,f'{effect[row,col]:+.2f}',ha='center',va='center',fontsize=11,color='black',bbox=dict(facecolor='white',alpha=.8,pad=.3,edgecolor='none'))
    fig.colorbar(m,ax=axs[2],label='100 (Uy plate / Uy empty - 1) [%]',shrink=.8)
    fig.suptitle('25 sampled points shown as tiles, not area averages | Different startup histories')
    fig.savefig(REPORT/'figures/grid25_startup_comparison.png',dpi=170);plt.close(fig)
    write_json('snapshot_comparison.json',{'status':'unconverged diagnostic snapshots; not calibration eligible',
        'plate_case':'fitted_F_urans','plate_physical_time_s':float(t1[-1]),
        'empty_case':'fitted_F_empty','empty_steady_iteration':150,
        'empty_Uy_ms':empty.tolist(),'plate_Uy_ms':plate.tolist(),
        'point_difference_percent':effect.tolist(),
        'point_difference_range_percent':[float(effect.min()),float(effect.max())],
        'additional_inlet_static_pressure_snapshot_Pa':summarize('fitted_F_urans')['last_inlet_static_pressure_Pa']-summarize('fitted_F_empty')['last_inlet_static_pressure_Pa']})


def benchmark():
    output={}
    for name in ['fitted_B_urans_renumbered','linux_B_urans','fitted_F_urans','linux_F_urans','linux_F_empty_urans']:
        logs=sorted((ROOT/'cases'/name).glob('log.pimpleFoam.*'))
        if not logs:continue
        raw=logs[-1].read_text(errors='replace')
        steps=[]
        for match in re.finditer(r'^Time = ([\d.eE+-]+)\n(.*?)(?=^Time = |\Z)',raw,re.M|re.S):
            clock=re.search(r'ExecutionTime = ([\d.eE+-]+) s\s+ClockTime = ([\d.eE+-]+) s',match[2])
            if clock:steps.append({'physical_time_s':float(match[1]),'wall_clock_s':float(clock[2])})
        output[name]={'build':re.search(r'^Build\s*:\s*(.*)$',raw,re.M)[1],
                      'first_six_steps':steps[:6],'last_step':steps[-1] if steps else None,
                      'completed_steps':len(steps)}
    write_json('runtime_comparison.json',{'caveat':'Different OpenFOAM builds and adaptive time steps; not a controlled operating-system-only speedup benchmark.', 'cases':output})


def axial():
    files=list((ROOT/'cases/fitted_F_urans/postProcessing/sample').glob('*/longitudinal_k_p_U.xy'))
    if not files:return
    file=max(files,key=lambda p:float(p.parent.name));data=np.loadtxt(file)
    data=data[np.all(np.isfinite(data),axis=1)&(np.abs(data).max(axis=1)<1e10)]
    ys=np.unique(data[:,1])*1000;zs=np.unique(data[:,2])*1000
    velocity=np.full((len(zs),len(ys)),np.nan)
    velocity[np.searchsorted(zs,data[:,2]*1000),np.searchsorted(ys,data[:,1]*1000)]=data[:,6]
    fig,ax=plt.subplots(figsize=(12,4.2),layout='constrained')
    cmap=plt.get_cmap('RdBu_r').copy();cmap.set_bad('#cccccc')
    im=ax.pcolormesh(ys,zs,velocity,shading='nearest',cmap=cmap,vmin=-3,vmax=6)
    _,blocked=geometry();cuts=blocked.intersection(LineString([(0,-40),(0,40)]))
    for segment in getattr(cuts,'geoms',[cuts]):
        if segment.length<=0:continue
        _,z0,_,z1=segment.bounds
        ax.add_patch(Rectangle((0,z0),5,z1-z0,color='#707070',zorder=3))
    ax.axvline(-55.0529657691,color='black',ls='--',lw=1)
    ax.annotate('Flow +Y',xy=(-95,32),xytext=(-130,32),arrowprops=dict(arrowstyle='->'),va='center')
    ax.set(xlabel='Y from plate upstream face [mm]',ylabel='Z [mm]',ylim=(-40,40),
           title=f'CFD central slice X=0 | Startup t={float(file.parent.name)*1000:.2f} ms, not time-averaged')
    fig.colorbar(im,ax=ax,label='Streamwise velocity Uy [m/s]',extend='both')
    fig.savefig(REPORT/'figures/axial_startup.png',dpi=170);plt.close(fig)
    write_json('axial_sample.json',{'case':'fitted_F_urans','time_s':float(file.parent.name),
        'source':str(file.relative_to(ROOT)), 'finite_sample_count':len(data),
        'sample_Uy_range_ms':[float(data[:,6].min()),float(data[:,6].max())],
        'note':'Finite spatial samples, not full-field extrema. Missing samples remain masked; solids shown in grey.'})


def main():
    quality();thickness();plots();benchmark();axial()
    write_json('run_summary.json',{n:summarize(n) for n in CASES if (ROOT/'cases'/n).exists()})
    print((REPORT/'results/snapshot_comparison.json').read_text()[-650:])

if __name__=='__main__':main()
