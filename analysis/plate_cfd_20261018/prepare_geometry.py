"""Inspect CAD mesh sections and prepare geometry evidence in original millimetres."""
import json
from pathlib import Path
import numpy as np
import trimesh
from shapely.geometry import Polygon, Point
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[0]

def polygons_at(mesh,y):
    section=mesh.section(plane_origin=[0,y,122.5],plane_normal=[0,1,0])
    assert section is not None
    polygons=[]
    for path in section.discrete:
        coords=path[:,[0,2]]
        poly=Polygon(coords)
        if poly.is_valid and poly.area>.001:
            polygons.append(poly)
    return polygons

def main():
    data=json.loads((ROOT/'geometry/fusion_geometry.json').read_text(encoding='utf-8'))
    meshes={}
    inventory=[]
    for body in data['bodies']:
        mesh=trimesh.Trimesh(vertices=np.array(body['vertices_mm']),faces=np.array(body['triangles']).reshape(-1,3),process=True)
        mesh.export(ROOT/'geometry'/f'{body["group"]}-{len(inventory)}.stl')
        inventory.append(dict(group=body['group'],watertight=bool(mesh.is_watertight),volume_mm3=float(mesh.volume),triangles=len(mesh.faces)))
        if body['group'] in ('test_section','plate'):
            meshes[body['group']]=mesh
    duct_rings=polygons_at(meshes['test_section'],-60)
    containing=[p for p in duct_rings if p.contains(Point(0,122.5))]
    duct=min(containing,key=lambda p:p.area)
    plate_rings=polygons_at(meshes['plate'],72.5)
    outer=max(plate_rings,key=lambda p:p.area)
    solid=outer
    for ring in plate_rings:
        if ring is not outer:
            solid=solid.difference(ring)
    blocked=solid.intersection(duct)
    geometry=dict(document=data['document'],cad_modified=data['modified_after'],mesh_inventory=inventory,
                  duct_area_mm2=duct.area,plate_blocked_area_mm2=blocked.area,
                  plate_blockage_fraction=blocked.area/duct.area,
                  duct_contour_xz_mm=list(map(list,duct.exterior.coords)),
                  plate_sections_count=len(plate_rings),plate_plane_y_mm=72.5,
                  probe_leading_bound_y_mm=14.947034230902094)
    (ROOT/'geometry/geometry_summary.json').write_text(json.dumps(geometry,indent=2),encoding='utf-8')
    fig,axes=plt.subplots(1,2,figsize=(11,5.2),layout='constrained')
    for ax in axes:
        x,z=duct.exterior.xy
        ax.plot(x,np.asarray(z)-82.5,color='#34475c',lw=2)
        ax.set_aspect('equal');ax.set_xlabel('CAD X [mm]');ax.set_ylabel('Height from lower wall [mm]')
        ax.set_xlim(-44,44);ax.set_ylim(-4,84);ax.grid(alpha=.2)
    axes[0].set_title('Open section / exact CAD contour')
    axes[1].set_title('Plate inside flow section / CAD Y = 72.5 mm')
    parts=list(blocked.geoms) if hasattr(blocked,'geoms') else [blocked]
    for part in parts:
        x,z=part.exterior.xy;axes[1].fill(x,np.asarray(z)-82.5,color='#db7e49')
        for hole in part.interiors:
            x,z=hole.xy;axes[1].fill(x,np.asarray(z)-82.5,color='white')
    for ax in axes:
        for x in [-32,-16,0,16,32]:
            ax.scatter([x]*5,[8,24,40,56,72],s=10,color='#125e83',zorder=4)
    fig.suptitle(f'Geometry check: area {duct.area:.2f} mm²; plate blockage {100*blocked.area/duct.area:.1f}%\nGeometry only - not a CFD flow result',fontsize=13)
    fig.savefig(ROOT/'geometry/section_and_plate.png',dpi=160)
    print(json.dumps({k:v for k,v in geometry.items() if k!='duct_contour_xz_mm'},indent=2))

if __name__=='__main__':main()
