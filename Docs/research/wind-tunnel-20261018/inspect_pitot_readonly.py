"""Read only: selected test-section and existing Pitot fixture geometry."""
import json
import re
import adsk.core
import adsk.fusion

def run(_context: str):
    app = adsk.core.Application.get()
    doc = app.activeDocument
    assert doc and 'merged model' in doc.name, 'Wrong active document'
    design = adsk.fusion.Design.cast(app.activeProduct)
    before = doc.isModified
    def point(p):
        return [round(v * 10, 5) for v in (p.x, p.y, p.z)]
    def vector(v):
        return [round(v.x, 7), round(v.y, 7), round(v.z, 7)]
    def bounds(b):
        return point(b.minPoint) + point(b.maxPoint)
    result = {'document': doc.name, 'version': doc.dataFile.versionNumber,
              'units': 'mm', 'is_modified_before': before, 'bodies': [],
              'root_occurrence_names': [o.component.name for o in design.rootComponent.occurrences]}
    for occ in design.rootComponent.allOccurrences:
        name = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), occ.component.name)
        test_section_prefix = ''.join(chr(c) for c in (0x6e2c, 0x5b9a, 0x80f4))
        if not (test_section_prefix in name or name == 'Pitotube plate' or name.startswith('Pitotube.f3d')):
            continue
        for body in occ.bRepBodies:
            row = {'path': occ.fullPathName, 'body': body.name,
                   'visible': body.isVisible, 'bbox': bounds(body.boundingBox), 'faces': []}
            for face in body.faces:
                geometry = face.geometry
                cylinder = adsk.core.Cylinder.cast(geometry)
                plane = adsk.core.Plane.cast(geometry)
                record = {'area_mm2': round(face.area * 100, 5), 'bbox': bounds(face.boundingBox)}
                if cylinder:
                    record.update(type='cylinder', diameter_mm=round(cylinder.radius*20, 5),
                                  origin=point(cylinder.origin), axis=vector(cylinder.axis))
                elif plane and face.area * 100 > 200:
                    record.update(type='plane', origin=point(plane.origin), normal=vector(plane.normal))
                else:
                    continue
                row['faces'].append(record)
            result['bodies'].append(row)
    result['is_modified_after'] = doc.isModified
    print(json.dumps(result, ensure_ascii=False))
