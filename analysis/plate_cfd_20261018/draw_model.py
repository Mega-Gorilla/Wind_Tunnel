"""Schematic of CFD boundaries; not a flow-result figure."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT=Path(__file__).resolve().parents[0]
fig,ax=plt.subplots(figsize=(11,3.8),layout='constrained')
ax.plot([-200,200],[40,40],color='#34475c',lw=3)
ax.plot([-200,200],[-40,-40],color='#34475c',lw=3)
ax.add_patch(Rectangle((0,-40),5,80,facecolor='#db7e49',alpha=.8))
ax.axvline(-55.0529658,ymin=.20,ymax=.73,color='#14788d',lw=2,ls='--')
ax.annotate('25 comparison points\n55.05 mm upstream',(-55.05,-38),(-112,-85),arrowprops={'arrowstyle':'->'},ha='center',color='#14788d')
ax.annotate('CAD grid plate\n5 mm thick',(2.5,35),(55,78),arrowprops={'arrowstyle':'->'},ha='center',color='#a5501d')
ax.annotate('Flow +y',(-105,0),(-175,0),arrowprops={'arrowstyle':'->','lw':2},va='center')
ax.text(-200,60,'Inlet\nU = 3 m/s',ha='center')
ax.text(200,60,'Outlet\np = 0 Pa',ha='center')
ax.text(103,-15,'80 mm outer envelope\n(actual CAD corner shape)',ha='center',fontsize=10)
ax.set(xlim=(-228,228),ylim=(-100,100),xlabel='Streamwise position from plate upstream face [mm]',ylabel='Height from section centre [mm]',title='CFD model schematic / same inlet flow with and without plate')
ax.set_xticks([-200,-100,-55.05,0,100,200],['-200','-100','-55.05','0','100','200'])
ax.set_yticks([-40,0,40]);ax.grid(axis='x',alpha=.13)
ax.spines[['top','right']].set_visible(False)
fig.savefig(ROOT/'geometry/model_extent.png',dpi=160)
print('Wrote geometry/model_extent.png')
