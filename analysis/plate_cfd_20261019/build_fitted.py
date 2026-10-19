"""Extrude a conformal section into convex prisms/hexahedra.

All y stations share the exact section connectivity; plate-footprint cells are
removed only between y=0 and 5 mm. Empty and plate cases use identical stations.
"""
from pathlib import Path
import argparse
import json
import numpy as np

ROOT = Path(__file__).resolve().parent


def header(name, cls='dictionary'):
    return f'FoamFile {{ version 2.0; format ascii; class {cls}; object {name}; }}\n'


def put(case, name, body, cls='dictionary'):
    p = case/name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(header(p.name, cls)+body+'\n', encoding='ascii')


def stations(scale=1):
    def reach(distance, first, growth, cap):
        widths, total = [], 0
        while total < distance:
            width = min(first*growth**len(widths), cap, distance-total)
            if distance-total < 1.35*width:
                width = distance-total
            widths.append(width)
            total += width
        return np.cumsum([0, *widths])
    up = -reach(.2, .0001/scale, 1.45, .016/scale)[::-1]
    down = .005 + reach(.195, .0001/scale, 1.35, .012/scale)
    plate = np.linspace(0, .005, 7*scale+1)
    return np.concatenate([up[:-1], plate, down[1:]])


def mesh(case, label, present, scale, custom_stations=None):
    src = np.load(ROOT/'meshes'/label/'section.npz')
    xy, conn, solid = src['points']/1000, src['cells'], src['solid']
    nc, npnt = len(conn), len(xy)
    y = np.asarray(custom_stations) if custom_stations is not None else stations(scale)
    active = np.ones((len(y)-1, nc), bool)
    if present:
        active[((y[:-1]+y[1:])/2 >= 0) & ((y[:-1]+y[1:])/2 <= .005)] = ~solid
    cell_ids = np.full(active.shape, -1, dtype=np.int32)
    cell_ids[active] = np.arange(active.sum(), dtype=np.int32)
    edges = {}
    for i, row in enumerate(conn):
        nodes = row[row >= 0].tolist()
        for a, b in zip(nodes, nodes[1:]+nodes[:1]):
            key = tuple(sorted((a, b)))
            edges.setdefault(key, []).append((i, a, b))
    assert max(map(len, edges.values())) == 2
    # Store every face in fixed-width arrays; point count is 3 or 4.
    faces, owners, neighbours, patches = [], [], [], []
    def add(nodes, owner, neighbour=-1, patch=-1):
        if neighbour >= 0 and owner > neighbour:
            owner, neighbour = neighbour, owner
            nodes = nodes[::-1]
        faces.append(nodes+[-1]*(4-len(nodes)))
        owners.append(owner); neighbours.append(neighbour); patches.append(patch)
    for j in range(len(y)):
        below = cell_ids[j-1] if j else np.full(nc, -1)
        above = cell_ids[j] if j < len(y)-1 else np.full(nc, -1)
        for i in np.flatnonzero((below >= 0) | (above >= 0)):
            nodes = (conn[i][conn[i] >= 0]+j*npnt).tolist()
            if below[i] >= 0:
                add(nodes[::-1], int(below[i]), int(above[i]), 1 if j == len(y)-1 else 3)
            else:
                add(nodes, int(above[i]), patch=0 if j == 0 else 3)
    for j in range(len(y)-1):
        for attached in edges.values():
            available = [item for item in attached if active[j, item[0]]]
            if not available:
                continue
            i, a, b = available[0]
            nodes = [a+j*npnt, a+(j+1)*npnt, b+(j+1)*npnt, b+j*npnt]
            neighbour = int(cell_ids[j, available[1][0]]) if len(available) == 2 else -1
            add(nodes, int(cell_ids[j, i]), neighbour, 2 if len(attached) == 1 else 3)
    faces = np.asarray(faces, dtype=np.int32)
    owner, neighbour, patch = map(np.asarray, (owners, neighbours, patches))
    internal = np.flatnonzero(neighbour >= 0)
    internal = internal[np.lexsort((neighbour[internal], owner[internal]))]
    boundary = [np.flatnonzero((neighbour < 0) & (patch == p)) for p in range(4)]
    order = np.concatenate([internal, *boundary])
    faces, owner = faces[order], owner[order]
    points = np.array([(x, yy, z) for yy in y for x, z in xy])
    used = np.unique(faces[faces >= 0])
    mapping = np.full(len(points), -1, dtype=np.int32)
    mapping[used] = np.arange(len(used))
    faces[faces >= 0] = mapping[faces[faces >= 0]]
    points = points[used]
    poly = case/'constant/polyMesh'
    poly.mkdir(parents=True, exist_ok=True)
    def write_list(name, cls, n, lines):
        with (poly/name).open('w', encoding='ascii') as out:
            out.write(header(name, cls)+f'{n}\n(\n')
            out.writelines(lines)
            out.write(')\n')
    write_list('points', 'vectorField', len(points),
               (f'({x:.12g} {yy:.12g} {z:.12g})\n' for x, yy, z in points))
    write_list('faces', 'faceList', len(faces),
               (f'{len(nodes)}('+ ' '.join(map(str, nodes))+')\n'
                for row in faces for nodes in [row[row >= 0].tolist()]))
    write_list('owner', 'labelList', len(owner), (f'{v}\n' for v in owner))
    write_list('neighbour', 'labelList', len(internal), (f'{v}\n' for v in neighbour[internal]))
    start = len(internal)
    names = ['inlet', 'outlet', 'duct', 'plate']
    parts = []
    for name, indices in zip(names, boundary):
        parts.append(f'{name} {{ type {"patch" if name in names[:2] else "wall"}; nFaces {len(indices)}; startFace {start}; }}')
        start += len(indices)
    put(case, 'constant/polyMesh/boundary', '4\n(\n'+'\n'.join(parts)+'\n)', 'polyBoundaryMesh')
    metadata = json.loads((ROOT/'meshes'/label/'metadata.json').read_text())
    metadata.update(case=case.name, plate_present=present, cells=int(active.sum()),
                    faces=len(faces), points=len(points), axial_stations_m=y.tolist(),
                    nominal_velocity_ms=3, rho_kgm3=1.2, nu_m2s=1.5e-5,
                    probe_plane_m=-.055052965769097906, probe_present=False,
                    model='constant-section 3D kOmegaSST', source_mesh=label)
    (case/'case_metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(json.dumps({k: metadata[k] for k in ['case', 'cells', 'faces', 'points']}, indent=2), flush=True)


def dictionaries(case):
    put(case,'constant/transportProperties','transportModel Newtonian;\nnu [0 2 -1 0 0 0 0] 1.5e-5;')
    put(case,'constant/turbulenceProperties','simulationType RAS;\nRAS { RASModel kOmegaSST; turbulence on; printCoeffs on; }')
    fields = {
        'U': ('volVectorField','[0 1 -1 0 0 0 0]','(0 3 0)', 'fixedValue; value uniform (0 3 0);', 'zeroGradient;', 'noSlip;'),
        'p': ('volScalarField','[0 2 -2 0 0 0 0]','0','zeroGradient;','fixedValue; value uniform 0;','zeroGradient;'),
        'k': ('volScalarField','[0 2 -2 0 0 0 0]','.00135','fixedValue; value uniform .00135;','inletOutlet; inletValue uniform .00135; value uniform .00135;','kqRWallFunction; value uniform .00135;'),
        'omega': ('volScalarField','[0 0 -1 0 0 0 0]','13.416407865','fixedValue; value uniform 13.416407865;','inletOutlet; inletValue uniform 13.416407865; value uniform 13.416407865;','omegaWallFunction; value uniform 13.416407865;'),
        'nut': ('volScalarField','[0 2 -1 0 0 0 0]','0','calculated; value uniform 0;','calculated; value uniform 0;','nutUSpaldingWallFunction; value uniform 0;'),
    }
    for name,(cls,dim,val,ib,ob,wb) in fields.items():
        put(case,'0/'+name,f'dimensions {dim};\ninternalField uniform {val};\nboundaryField {{ inlet {{ type {ib} }} outlet {{ type {ob} }} "(duct|plate)" {{ type {wb} }} }}',cls)
    put(case,'system/fvSchemes','''
ddtSchemes { default steadyState; }
gradSchemes { default cellLimited Gauss linear 1; }
divSchemes { default none; div(phi,U) bounded Gauss linearUpwind grad(U);
 div(phi,k) bounded Gauss upwind; div(phi,omega) bounded Gauss upwind;
 div((nuEff*dev2(T(grad(U))))) Gauss linear; }
laplacianSchemes { default Gauss linear limited .5; }
interpolationSchemes { default linear; }
snGradSchemes { default limited .5; }
wallDist { method meshWave; }
''')
    put(case,'system/fvSolution','''
solvers {
 p { solver GAMG; tolerance 1e-8; relTol .03; smoother GaussSeidel; }
 "(U|k|omega)" { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol .05; }
}
SIMPLE { nNonOrthogonalCorrectors 0; residualControl { p 1e-5; U 1e-6; "(k|omega)" 1e-6; } }
relaxationFactors { fields { p .2; } equations { U .4; k .4; omega .4; } }
''')
    probes = '\n'.join(f'({x/1000} -.0550529657691 {z/1000})'
                       for z in [32,16,0,-16,-32] for x in [-32,-16,0,16,32])
    funcs = f'''
gridProbes {{ type probes; libs ("libsampling.dll"); interpolationScheme cellPoint;
 writeControl timeStep; writeInterval 1; fields (U p k); probeLocations ({probes}); }}
inletFlux {{ type surfaceFieldValue; libs ("libfieldFunctionObjects.dll"); writeControl timeStep; writeInterval 1;
 regionType patch; name inlet; operation sum; fields (phi); writeFields false; }}
outletFlux {{ type surfaceFieldValue; libs ("libfieldFunctionObjects.dll"); writeControl timeStep; writeInterval 1;
 regionType patch; name outlet; operation sum; fields (phi); writeFields false; }}
inletP {{ type surfaceFieldValue; libs ("libfieldFunctionObjects.dll"); writeControl timeStep; writeInterval 1;
 regionType patch; name inlet; operation areaAverage; fields (p); writeFields false; }}
yPlus {{ type yPlus; libs ("libfieldFunctionObjects.dll"); writeControl writeTime; }}
'''
    put(case,'system/controlDict',f'''
application simpleFoam; startFrom latestTime; startTime 0; stopAt endTime; endTime 500;
deltaT 1; writeControl timeStep; writeInterval 100; purgeWrite 2;
writeFormat binary; writePrecision 10; writeCompression off; timeFormat general; timePrecision 8;
runTimeModifiable true; functions {{ {funcs} }}
''')
    old_sample = ROOT.parent/'plate_cfd_20261018/cases/medium_repaired_plate/system/sample'
    if old_sample.exists():
        (case/'system/sample').write_text(old_sample.read_text(), encoding='ascii')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--label', default='fitted_A')
    ap.add_argument('--scale', type=int, default=1)
    ap.add_argument('--case-label')
    ap.add_argument('--stations-json', type=Path)
    ap.add_argument('--only', choices=['both','empty','plate'], default='both')
    args = ap.parse_args()
    for present in [False, True]:
        suffix = 'plate' if present else 'empty'
        if args.only not in ('both', suffix):
            continue
        case = ROOT/'cases'/f'{args.case_label or args.label}_{suffix}'
        if (case/'case_metadata.json').exists():
            raise RuntimeError('Refusing to overwrite an existing case: '+str(case))
        dictionaries(case)
        custom = json.loads(args.stations_json.read_text())['axial_stations_m'] if args.stations_json else None
        mesh(case, args.label, present, args.scale, custom)


if __name__ == '__main__':
    main()
