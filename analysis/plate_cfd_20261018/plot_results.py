"""Generate comparison plots from actual solver output; all captions identify CFD."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.interpolate import griddata
from inspect_results import numeric, latest, summary
from report_paths import RESULTS_ROOT

ROOT=Path(__file__).resolve().parents[0]
OUT=RESULTS_ROOT;OUT.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})

def case_path(label, kind):
    return ROOT/'cases'/f'{label}{"_repaired" if kind=="plate" else ""}_{kind}'

def sample(case, name):
    return numeric(latest(case/'postProcessing/sample')/(name+'_k_p_U.xy'))

def main():
    data={}
    for label in ['coarse','medium']:
        for kind in ['empty','plate']:
            c=case_path(label,kind)
            key=f'{label}_{kind}'
            data[key]=summary(c)
            sample_folder=latest(c/'postProcessing/pointSamples')
            samples=numeric(sample_folder/'grid25_k_p_U.xy')
            samples=np.array(sorted(samples,key=lambda r:(-round(r[2],8),round(r[0],8))))
            assert samples.shape == (25,8)
            data[key]['tip_uy_last_ms']=samples[:,6].tolist()
            data[key]['spatial_interpolation']='cellPoint'
            data[key]['sample_iteration']=float(sample_folder.name)
            assert data[key]['sample_iteration']==data[key]['iteration'],(c.name,'final samples are not ready')
    comparison={}
    fig,axes=plt.subplots(1,2,figsize=(12,4.4),layout='constrained')
    banner='CFD screening / NOT FOR CALIBRATION'
    if not all(row['residual_control_converged'] for row in data.values()):
        banner+=' / residual target not met in all cases'
    for label,color in [('coarse','#a55424'),('medium','#126a92')]:
        a=data[f'{label}_empty'];b=data[f'{label}_plate']
        ua=np.array(a['tip_uy_last_ms']);ub=np.array(b['tip_uy_last_ms'])
        diff=100*(ub-ua)/ua
        comparison[label]={'additional_inlet_static_pressure_Pa':b['inlet_static_pressure_Pa']-a['inlet_static_pressure_Pa'],
                           'point_velocity_effect_percent':diff.tolist(),
                           'max_abs_point_effect_percent':float(np.max(np.abs(diff))),
                           'point_effect_min_percent':float(diff.min()),'point_effect_max_percent':float(diff.max()),
                           'paired_inlet_flow_difference_percent':100*(b['inlet_Q_m3s']/a['inlet_Q_m3s']-1)}
        for kind,style in [('empty','--'),('plate','-')]:
            c=case_path(label,kind)
            p=numeric(c/'postProcessing/inletP/0/surfaceFieldValue.dat')
            axes[0].plot(p[:,0],p[:,1]*1.2,style,color=color,label=f'{label} / {kind}')
        axes[1].plot(np.arange(25),diff,'o-',color=color,label=label,ms=4)
    axes[0].set(xlabel='SIMPLE iteration (not physical time)',ylabel='Inlet static pressure [Pa]',title='CFD: pressure convergence; outlet = 0 Pa')
    axes[1].axhline(0,color='gray',lw=.7);axes[1].set(xlabel='Hole position (top row to bottom row)',ylabel='100 x (plate - empty) / empty [%]',title='CFD: axial velocity effect 55.05 mm upstream')
    ticks=np.arange(25);names=[f'{row}{col}' for row in 'EDCBA' for col in range(1,6)]
    axes[1].set_xticks(ticks,names,rotation=90,fontsize=7)
    for ax in axes:ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle(banner,fontsize=11)
    fig.savefig(OUT/'convergence_and_probe_comparison.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(12,4.3),layout='constrained')
    label='medium';base=np.array(data[f'{label}_empty']['tip_uy_last_ms']).reshape(5,5);plate=np.array(data[f'{label}_plate']['tip_uy_last_ms']).reshape(5,5)
    vmin=min(base.min(),plate.min());vmax=max(base.max(),plate.max())
    diff=(plate/base-1)*100
    for ax,vals,title in zip(axes,[base,plate,diff],['No plate [m/s]','Plate [m/s]','Difference [% of no plate]']):
        im=ax.imshow(vals,cmap='RdBu_r' if ax is axes[2] else 'viridis',vmin=(-max(abs(diff.min()),abs(diff.max())) if ax is axes[2] else vmin),vmax=(max(abs(diff.min()),abs(diff.max())) if ax is axes[2] else vmax))
        ax.set_xticks(range(5),range(1,6));ax.set_yticks(range(5),list('EDCBA'));ax.set_title(title)
        for i in range(5):
            for j in range(5):
                rgb=im.cmap(im.norm(vals[i,j]))[:3]
                ink='black' if np.dot(rgb,[.2126,.7152,.0722])>.55 else 'white'
                ax.text(j,i,f'{vals[i,j]:+.2f}' if ax is axes[2] else f'{vals[i,j]:.3f}',ha='center',va='center',color=ink,fontsize=8)
        fig.colorbar(im,ax=ax,shrink=.8)
    fig.suptitle(banner+'\n25 hole-aligned positions / nominal inlet 3 m/s / no physical Pitot body',fontsize=11)
    fig.savefig(OUT/'grid25_velocity.png',dpi=170);plt.close(fig)
    # Sparse cross-sections remain numerical sample maps, not an area-weighted traverse mean.
    fig,axes=plt.subplots(2,3,figsize=(12,7.8),layout='constrained')
    section_stats={}
    for col,name in enumerate(['tip','near','wake']):
        arr0=sample(case_path('medium','empty'),name);arr1=sample(case_path('medium','plate'),name)
        key0={(round(row[0],8),round(row[2],8)):row for row in arr0}
        paired=[(key0[(round(row[0],8),round(row[2],8))],row) for row in arr1 if (round(row[0],8),round(row[2],8)) in key0]
        aa=np.array([p[0] for p in paired]);bb=np.array([p[1] for p in paired])
        # columns: x y z k p Ux Uy Uz
        delta=100*(bb[:,6]-aa[:,6])/3
        section_stats[name]={'sample_count':len(bb),'max_abs_delta_percent_bulk':float(np.max(abs(delta))),
                             'rms_delta_percent_bulk':float(np.sqrt(np.mean(delta**2))),'range_plate_uy_ms':[float(bb[:,6].min()),float(bb[:,6].max())]}
        for row,vals,cmap in [(0,bb[:,6],'viridis'),(1,delta,'RdBu_r')]:
            ax=axes[row,col]
            im=ax.scatter(bb[:,0]*1000,bb[:,2]*1000,c=vals,s=11,marker='s',cmap=cmap,
                          vmin=0 if row==0 else -20,vmax=6 if row==0 else 20)
            ax.set_aspect('equal');ax.set(xlabel='X [mm]',ylabel='Z from centre [mm]',title=f'{name}: y={bb[0,1]*1000:.2f} mm')
            fig.colorbar(im,ax=ax,label='Uy [m/s]' if row==0 else '(plate - empty) / 3 m/s [%]',shrink=.8,extend='both')
            if row==1:ax.set_title(f'{name}: range {delta.min():+.2f} to {delta.max():+.2f}%')
    fig.suptitle(banner+'\nPlate velocity (top); difference from no plate (bottom); fixed colour limits',fontsize=11)
    fig.savefig(OUT/'section_comparison.png',dpi=170);plt.close(fig)
    mesh_change=np.array(comparison['medium']['point_velocity_effect_percent'])-np.array(comparison['coarse']['point_velocity_effect_percent'])
    result={'cases':data,'comparison':comparison,'section_samples':section_stats,
            'two_mesh_difference_max_percentage_points':float(np.max(abs(mesh_change))),
            'pressure_effect_two_mesh_difference_Pa':comparison['medium']['additional_inlet_static_pressure_Pa']-comparison['coarse']['additional_inlet_static_pressure_Pa']}
    result['absolute_velocity_two_mesh_difference_percent']={kind:float(np.max(abs(np.array(data[f'medium_{kind}']['tip_uy_last_ms'])/np.array(data[f'coarse_{kind}']['tip_uy_last_ms'])-1))*100) for kind in ['empty','plate']}
    (OUT/'comparison.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='cases'},indent=2))

if __name__=='__main__':main()
