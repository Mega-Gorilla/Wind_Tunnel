"""Export selected Fusion geometry without changing the active design."""
import json
from pathlib import Path
import adsk.core
import adsk.fusion

def run(_context: str):
    app = adsk.core.Application.get()
    doc = app.activeDocument
    assert doc and doc.name == 'merged model v49'
    before = doc.isModified
    design = adsk.fusion.Design.cast(app.activeProduct)
    prefix = ''.join(chr(c) for c in (0x6e2c,0x5b9a,0x80f4))
    rows = []
    for occ in design.rootComponent.allOccurrences:
        name = occ.component.name
        group = None
        if name.startswith(prefix) and 'v3' in name and '+' not in occ.fullPathName:
            group = 'test_section'
        elif name == 'Pitotube plate':
            group = 'plate'
        elif name.startswith('Pitotube.f3d'):
            group = 'probe_reference'
        if group is None:
            continue
        for proxy in occ.bRepBodies:
            body = proxy.nativeObject or proxy
            calc = body.meshManager.createMeshCalculator()
            calc.surfaceTolerance = 0.002  # cm: 0.02 mm tessellation tolerance
            calc.maxSideLength = 0.25     # cm: 2.5 mm
            mesh = calc.calculate()
            assert mesh
            verts = []
            for p in mesh.nodeCoordinates:
                p.transformBy(occ.transform2)
                verts.append([p.x*10,p.y*10,p.z*10])
            bb = proxy.boundingBox
            expected = [bb.minPoint.x*10,bb.minPoint.y*10,bb.minPoint.z*10,
                        bb.maxPoint.x*10,bb.maxPoint.y*10,bb.maxPoint.z*10]
            actual = [min(p[i] for p in verts) for i in range(3)]+[max(p[i] for p in verts) for i in range(3)]
            error = max(abs(a-b) for a,b in zip(actual,expected))
            assert error < .05, (occ.fullPathName,error)
            rows.append(dict(group=group,path=occ.fullPathName,name=body.name,
                             bbox_mm=expected,mesh_bbox_error_mm=error,vertices_mm=verts,
                             triangles=list(mesh.nodeIndices)))
    assert sum(r['group']=='plate' for r in rows)==1
    assert sum(r['group']=='test_section' for r in rows)==1
    result = dict(document=doc.name,version=doc.dataFile.versionNumber,
                  modified_before=before,modified_after=doc.isModified,
                  tolerance_mm=.02,units='mm',bodies=rows)
    dest=Path('D:/codes/Wind_Tunnel/analysis/plate_cfd_20261018/geometry')
    dest.mkdir(parents=True,exist_ok=True)
    (dest/'fusion_geometry.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(dict(document=doc.name,modified_before=before,modified_after=doc.isModified,
                         bodies=[dict(group=r['group'],triangles=len(r['triangles'])//3,
                                      bbox_error_mm=r['mesh_bbox_error_mm']) for r in rows])))
