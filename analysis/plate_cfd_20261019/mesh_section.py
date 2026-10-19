"""Generate a conformal, CAD-section-fitted triangulation (millimetres).

The source Fusion export is read-only.  This is a constant-section surrogate,
not a reconstruction of the entire wind tunnel.  No CFD result is implied.
"""
from pathlib import Path
import argparse
import json
import sys
import numpy as np
import shapely
from shapely.geometry import Polygon, Point
from shapely import affinity
import trimesh
import gmsh

ROOT = Path(__file__).resolve().parent
OLD = ROOT.parent / 'plate_cfd_20261018'


def rings(mesh, y):
    section = mesh.section(plane_origin=[0, y, 122.5], plane_normal=[0, 1, 0])
    return [p for line in section.discrete
            if (p := Polygon(line[:, [0, 2]])).is_valid and p.area > .001]


def geometry():
    duct = min((p for p in rings(trimesh.load_mesh(OLD/'geometry/test_section-0.stl'), -60)
                if p.contains(Point(0, 122.5))), key=lambda p: p.area)
    plate_rings = rings(trimesh.load_mesh(OLD/'geometry/plate-3.stl'), 72.5)
    outer = max(plate_rings, key=lambda p: p.area)
    blocked = outer
    for p in plate_rings:
        if p is not outer:
            blocked = blocked.difference(p)
    duct = affinity.translate(duct, yoff=-122.5)
    blocked = affinity.translate(blocked, yoff=-122.5).intersection(duct)
    # Remove only collinear/tiny STL-section segments; retain the source polygons
    # for area-error auditing and classification.
    return duct, blocked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--label', default='fitted_coarse')
    ap.add_argument('--edge', type=float, default=.8)
    ap.add_argument('--core', type=float, default=2.5)
    ap.add_argument('--gap', type=float, default=.1)
    ap.add_argument('--bl', action='store_true')
    ap.add_argument('--recombine', action='store_true')
    ap.add_argument('--aniso', action='store_true')
    ap.add_argument('--structured-strip', action='store_true')
    args = ap.parse_args()
    folder = ROOT/'meshes'/args.label
    folder.mkdir(parents=True, exist_ok=True)
    duct, blocked = geometry()
    simple_duct = shapely.set_precision(duct.simplify(.002, preserve_topology=True), .002)
    simple_blocked = shapely.set_precision(blocked.simplify(.002, preserve_topology=True), .002).intersection(simple_duct)
    gmsh.initialize()
    gmsh.option.setNumber('General.Verbosity', 2)
    gmsh.model.add(args.label)
    occ = gmsh.model.occ

    def surface(poly):
        loops = []
        for ring in [poly.exterior, *poly.interiors]:
            coords = np.asarray(ring.coords)[:-1]
            pts = [occ.addPoint(float(x), float(y), 0) for x, y in coords]
            curves = [occ.addLine(p, pts[(i+1) % len(pts)]) for i, p in enumerate(pts)]
            loops.append(occ.addCurveLoop(curves))
        return occ.addPlaneSurface(loops)

    d = surface(simple_duct)
    parts = list(simple_blocked.geoms) if hasattr(simple_blocked, 'geoms') else [simple_blocked]
    solids = [surface(p) for p in parts]
    strips = []
    if args.structured_strip:
        for xx, yy, dx, dy in [(-40,-30,.5,60),(39.5,-30,.5,60),(-30,-40,60,.5),(-30,39.5,60,.5)]:
            strips.append(occ.addRectangle(xx, yy, 0, dx, dy))
    _, fragment_map = occ.fragment([(2, d)], [(2, p) for p in [*solids, *strips]])
    solid_surfaces = [tag for mapping in fragment_map[1:len(solids)+1] for dim, tag in mapping if dim == 2]
    if args.structured_strip:
        occ.removeAllDuplicates()
    occ.synchronize()
    gmsh.option.setNumber('Mesh.Algorithm', 6)
    gmsh.option.setNumber('Mesh.MeshSizeFromPoints', 0)
    gmsh.option.setNumber('Mesh.MeshSizeExtendFromBoundary', 0)
    gmsh.option.setNumber('Mesh.MeshSizeFromCurvature', 0)
    gmsh.option.setNumber('Mesh.MeshSizeMax', args.core)
    # A distance field refines rib/collar boundaries; the peripheral strip has
    # an explicit small target. All units here are mm.
    curves = [tag for dim, tag in gmsh.model.getEntities(1)]
    dist = gmsh.model.mesh.field.add('Distance')
    gmsh.model.mesh.field.setNumbers(dist, 'CurvesList', curves)
    gmsh.model.mesh.field.setNumber(dist, 'Sampling', 100)
    threshold = gmsh.model.mesh.field.add('Threshold')
    for key, val in {'InField': dist, 'SizeMin': args.edge, 'SizeMax': args.core,
                     'DistMin': .1, 'DistMax': 3.0}.items():
        gmsh.model.mesh.field.setNumber(threshold, key, val)
    gmsh.model.mesh.field.setAsBackgroundMesh(threshold)

    def local_size(dim, tag, x, y, z, lc):
        # For the 0.2 mm perimeter gap, prevent an unresolvable 1-cell shortcut.
        wall_dist = simple_duct.boundary.distance(Point(x, y))
        if wall_dist < .205:
            return min(lc, args.gap)
        if wall_dist < 1.0:
            return min(lc, args.gap + (wall_dist-.205)*1.5)
        return lc

    if args.bl:
        bl = gmsh.model.mesh.field.add('BoundaryLayer')
        gmsh.model.mesh.field.setNumbers(bl, 'CurvesList', curves)
        gmsh.model.mesh.field.setNumbers(bl, 'ExcludedSurfacesList', solid_surfaces)
        for key, val in {'Size': args.gap, 'SizeFar': args.core, 'Thickness': .55,
                         'Ratio': 1.35, 'Quads': 1, 'IntersectMetrics': 1}.items():
            gmsh.model.mesh.field.setNumber(bl, key, val)
        gmsh.model.mesh.field.setAsBoundaryLayer(bl)
    elif args.aniso:
        outer_curves = [tag for dim, tag in gmsh.model.getBoundary(gmsh.model.getEntities(2), combined=True, oriented=False)]
        aniso = gmsh.model.mesh.field.add('AttractorAnisoCurve')
        gmsh.model.mesh.field.setNumbers(aniso, 'CurvesList', outer_curves)
        for key, val in {'DistMin': .205, 'DistMax': 1.5, 'SizeMinNormal': args.gap,
                         'SizeMinTangent': args.edge, 'SizeMaxNormal': args.core,
                         'SizeMaxTangent': args.core, 'Sampling': 500}.items():
            gmsh.model.mesh.field.setNumber(aniso, key, val)
        combined = gmsh.model.mesh.field.add('IntersectAniso')
        gmsh.model.mesh.field.setNumbers(combined, 'FieldsList', [aniso, threshold])
        gmsh.model.mesh.field.setAsBackgroundMesh(combined)
        gmsh.option.setNumber('Mesh.Algorithm', 7)
        gmsh.option.setNumber('Mesh.AnisoMax', 100)
    else:
        gmsh.model.mesh.setSizeCallback(local_size)
    if args.recombine:
        gmsh.option.setNumber('Mesh.RecombineAll', 1)
        gmsh.option.setNumber('Mesh.RecombinationAlgorithm', 1)
    structured = []
    if args.structured_strip:
        for _, tag in gmsh.model.getEntities(2):
            xmin,ymin,_,xmax,ymax,_ = occ.getBoundingBox(2, tag)
            dx, dy = xmax-xmin, ymax-ymin
            boundary = gmsh.model.getBoundary([(2,tag)], oriented=False)
            if len(boundary) != 4 or min(dx,dy) > .501:
                continue
            if abs(occ.getMass(2,tag)-dx*dy) > 1e-3:
                continue
            for dim, curve in boundary:
                length = occ.getMass(1,curve)
                spacing = args.gap if length < .501 else args.edge
                gmsh.model.mesh.setTransfiniteCurve(curve, int(np.ceil(length/spacing))+1)
            gmsh.model.mesh.setTransfiniteSurface(tag)
            gmsh.model.mesh.setRecombine(2,tag)
            structured.append(tag)
    gmsh.model.mesh.generate(2)
    tags, coords, _ = gmsh.model.mesh.getNodes()
    coords = np.asarray(coords).reshape(-1, 3)[:, :2]
    order = np.argsort(tags)
    tags, coords = tags[order], coords[order]
    types, _, nodes = gmsh.model.mesh.getElements(2)
    cells = []
    for etype, conn in zip(types, nodes):
        assert etype in (2, 3), etype
        n = 3 if etype == 2 else 4
        cells.extend(np.searchsorted(tags, np.asarray(conn).reshape(-1, n)).tolist())
    area, centroids, valid_cells = [], [], []
    for cell in cells:
        p = coords[cell]
        signed = np.sum(p[:, 0]*np.roll(p[:, 1], -1)-p[:, 1]*np.roll(p[:, 0], -1))/2
        if signed < 0:
            cell.reverse()
        p = coords[cell]
        if len(cell) == 4:
            e = np.roll(p, -1, axis=0)-p
            turns = e[:, 0]*np.roll(e[:, 1], -1)-e[:, 1]*np.roll(e[:, 0], -1)
            if min(turns) <= 1e-10:
                choices = [[(0,1,2),(0,2,3)],[(0,1,3),(1,2,3)]]
                for pair in choices:
                    pp = [p[list(t)] for t in pair]
                    aa = [np.cross(t[1]-t[0], t[2]-t[0])/2 for t in pp]
                    if min(aa) > 1e-12:
                        for t, a in zip(pair, aa):
                            valid_cells.append([cell[k] for k in t])
                            area.append(float(a)); centroids.append(p[list(t)].mean(axis=0))
                        break
                else:
                    raise ValueError('Invalid quad')
                continue
        valid_cells.append(cell)
        area.append(abs(signed))
        centroids.append(p.mean(axis=0))
    cells = valid_cells
    area, centroids = np.array(area), np.array(centroids)
    if abs(area.sum()-simple_duct.area) > .01:
        raise ValueError(f'Mesh area {area.sum()} differs from CAD {simple_duct.area}')
    is_solid = shapely.contains_xy(simple_blocked, centroids[:, 0], centroids[:, 1])
    metadata = dict(label=args.label, node_count=len(coords), cell_count=len(cells),
                    triangles=sum(len(c)==3 for c in cells), quads=sum(len(c)==4 for c in cells), boundary_layer=args.bl, anisotropic=args.aniso,
                    structured_strip_surfaces=structured,
                    edge_mm=args.edge, core_mm=args.core, gap_target_mm=args.gap,
                    source_area_mm2=duct.area, mesh_area_mm2=float(area.sum()),
                    source_blocked_area_mm2=blocked.area, mesh_blocked_area_mm2=float(area[is_solid].sum()),
                    source_blockage=float(blocked.area/duct.area),
                    mesh_blockage=float(area[is_solid].sum()/area.sum()),
                    simplification_tolerance_mm=.002, precision_grid_mm=.002, gmsh_version=gmsh.__version__)
    conn = np.full((len(cells), 4), -1, dtype=np.int32)
    for i, cell in enumerate(cells):
        conn[i, :len(cell)] = cell
    np.savez_compressed(folder/'section.npz', points=coords, cells=conn, solid=is_solid)
    (folder/'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    gmsh.write(str(folder/'section.msh'))
    gmsh.finalize()
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    main()
