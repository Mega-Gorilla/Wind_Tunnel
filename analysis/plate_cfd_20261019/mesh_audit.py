"""Audit and plot the improved mesh; figures contain no CFD flow claims."""
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from shapely.geometry import Polygon, LineString
from mesh_section import geometry

ROOT = Path(__file__).resolve().parent
REPORT = ROOT.parents[1]/'Docs/tests/cfd/2026-10-19_fixed_plate_refined'


def main():
    (REPORT/'figures').mkdir(parents=True, exist_ok=True)
    (REPORT/'results').mkdir(parents=True, exist_ok=True)
    duct, blocked = geometry()
    data = np.load(ROOT/'meshes/fitted_B/section.npz')
    points, cells, solid = data['points'], data['cells'], data['solid']
    polygons = [points[row[row >= 0]] for row in cells]
    shapes = [Polygon(p) for p in polygons]
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.8), layout='constrained')
    windows = [(-41,41,-41,41), (-5,5,-5,5), (38.9,40.05,-1.5,1.5)]
    titles = ['CAD-fitted cross-section', 'Central 4.2 mm hole / ribs', 'Nominal 0.2 mm peripheral gap']
    for ax, limits, title in zip(axes, windows, titles):
        colors = np.where(solid, '#df9863', '#e9f4f8')
        ax.add_collection(PolyCollection(polygons, facecolors=colors, edgecolors='#3f5263', linewidths=.22))
        ax.set(xlim=limits[:2], ylim=limits[2:], xlabel='X [mm]', ylabel='Z [mm]', title=title)
        ax.set_aspect('equal')
    fig.suptitle('Improved mesh B: geometry and grid only (not a velocity result)')
    fig.savefig(REPORT/'figures/mesh_detail.png', dpi=180)
    plt.close(fig)
    samples = []
    for xsign in [-1,1]:
        for z in [-30,-15,1.1,15,30]:
            line = LineString([(xsign*39.8,z),(xsign*40,z)])
            lengths = [p.intersection(line).length for p,s in zip(shapes, solid) if not s and p.intersects(line)]
            lengths = [v for v in lengths if v > 1e-7]
            samples.append(dict(side='left' if xsign<0 else 'right', z_mm=z,
                                cells_across_gap=len(lengths), segments_mm=lengths,
                                covered_mm=sum(lengths)))
    metadata = json.loads((ROOT/'meshes/fitted_B/metadata.json').read_text())
    metadata['gap_line_samples'] = samples
    metadata['area_relative_error_percent'] = (metadata['mesh_area_mm2']/metadata['source_area_mm2']-1)*100
    metadata['blockage_error_percentage_points'] = (metadata['mesh_blockage']-metadata['source_blockage'])*100
    (REPORT/'results/mesh_audit.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    sources = [ROOT.parent/'plate_cfd_20261018/geometry'/f for f in ['fusion_geometry.json','plate-3.stl','test_section-0.stl']]
    sources += [ROOT/'meshes/fitted_B/section.npz', ROOT/'mesh_section.py', ROOT/'build_fitted.py']
    provenance = dict(client_date='2026-10-19', document='merged model v49 (saved export, read-only)',
                      files=[dict(path=str(p.relative_to(ROOT.parents[1])), sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sources])
    (REPORT/'results/geometry_provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
    print(json.dumps(metadata, indent=2))


if __name__=='__main__':
    main()
