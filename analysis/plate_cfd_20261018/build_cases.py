"""Create auditable fixed-flow screening cases; never changes the Fusion model."""
import argparse
import json
from pathlib import Path
import numpy as np
import trimesh
from shapely.geometry import Polygon, box

ROOT = Path(__file__).resolve().parents[0]

def header(name, cls='dictionary'):
    return f'FoamFile {{ version 2.0; format ascii; class {cls}; object {name}; }}\n'

def put(case, name, text, cls='dictionary'):
    path = case / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header(path.name, cls) + text + '\n', encoding='ascii')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--base-mm',type=float,default=5); ap.add_argument('--label',default='coarse')
    ap.add_argument('--only',choices=['both','plate','empty'],default='both')
    ap.add_argument('--plate-layers',type=int,default=3)
    args=ap.parse_args()
    meta=json.loads((ROOT/'geometry/geometry_summary.json').read_text())
    xy=np.array(meta['duct_contour_xz_mm']); xy[:,1]-=122.5; xy/=1000
    duct=Polygon(xy).simplify(1e-6,preserve_topology=True)
    ring=box(-.060,-.060,.060,.060).difference(duct)
    wall=trimesh.creation.extrude_polygon(ring,height=.46,engine='earcut')
    transform=np.array([[1,0,0,0],[0,0,1,-.23],[0,1,0,0],[0,0,0,1]],float)
    wall.apply_transform(transform)
    plate=trimesh.load_mesh(ROOT/'geometry/plate-3.stl',process=True)
    plate.vertices=(plate.vertices-np.array([0,70,122.5]))/1000
    assert wall.is_watertight and plate.is_watertight
    n=int(round(90/args.base_mm)); ny=int(round(400/args.base_mm))
    points=[(x/1000,-.055052965769097906,z/1000) for z in [32,16,0,-16,-32] for x in [-32,-16,0,16,32]]
    point_text='\n'.join(f'({x:.9f} {y:.9f} {z:.9f})' for x,y,z in points)
    for include in [False,True]:
        if args.only=='plate' and not include:continue
        if args.only=='empty' and include:continue
        case=ROOT/'cases'/f'{args.label}_{"plate" if include else "empty"}'
        case.mkdir(parents=True,exist_ok=True)
        tri=case/'constant/triSurface';tri.mkdir(parents=True,exist_ok=True)
        wall.export(tri/'duct.stl');plate.export(tri/'plate.stl')
        put(case,'system/blockMeshDict',f'''
convertToMeters 1;
vertices ((-.045 -.2 -.045) (.045 -.2 -.045) (.045 .2 -.045) (-.045 .2 -.045)
          (-.045 -.2 .045) (.045 -.2 .045) (.045 .2 .045) (-.045 .2 .045));
blocks (hex (0 1 2 3 4 5 6 7) ({n} {ny} {n}) simpleGrading (1 1 1));
edges ();
boundary (
 inlet {{ type patch; faces ((0 1 5 4)); }}
 outlet {{ type patch; faces ((3 7 6 2)); }}
 outside {{ type wall; faces ((0 4 7 3) (1 2 6 5) (0 3 2 1) (4 5 6 7)); }}
);
mergePatchPairs ();
''')
        geo='duct.stl { type triSurfaceMesh; name duct; }'
        surf='duct { level (1 1); patchInfo { type wall; } }'
        if include:
            geo+='\nplate.stl { type triSurfaceMesh; name plate; }'
            surf+='\nplate { level (3 3); patchInfo { type wall; } }'
        put(case,'system/snappyHexMeshDict',f'''
castellatedMesh true; snap true; addLayers true;
geometry {{ {geo}
  testRegion {{ type searchableBox; min (-.043 -.085 -.043); max (.043 .05 .043); }}
}}
castellatedMeshControls {{
 maxLocalCells 1500000; maxGlobalCells 1500000; minRefinementCells 0;
 nCellsBetweenLevels 3; features ();
 refinementSurfaces {{ {surf} }}
 resolveFeatureAngle 30;
 refinementRegions {{ testRegion {{ mode inside; levels ((1e15 1)); }} }}
 locationInMesh (.00137 -.11213 .00237); allowFreeStandingZoneFaces true;
}}
snapControls {{ nSmoothPatch 3; tolerance 1.5; nSolveIter 50; nRelaxIter 5;
 nFeatureSnapIter 10; implicitFeatureSnap true; explicitFeatureSnap false; multiRegionFeatureSnap false; }}
addLayersControls {{ relativeSizes true;
 layers {{ "duct.*" {{ nSurfaceLayers 3; }} "plate.*" {{ nSurfaceLayers {args.plate_layers}; }} }}
 expansionRatio 1.2; finalLayerThickness .4; minThickness .08; nGrow 0;
 featureAngle 60; nRelaxIter 5; nSmoothSurfaceNormals 1; nSmoothNormals 3;
 nSmoothThickness 10; maxFaceThicknessRatio .5; maxThicknessToMedialRatio .3;
 minMedialAxisAngle 90; nBufferCellsNoExtrude 0; nLayerIter 60; nRelaxedIter 40;
}}
meshQualityControls {{
 #includeEtc "caseDicts/meshQualityDict"
 minVol 1e-18; maxBoundarySkewness 4; nSmoothScale 4; errorReduction .75;
 relaxed {{ maxNonOrtho 70; }}
}}
writeFlags (scalarLevels layerSets layerFields);
mergeTolerance 1e-7;
''')
        put(case,'constant/transportProperties','transportModel Newtonian;\nnu [0 2 -1 0 0 0 0] 1.5e-5;')
        put(case,'constant/turbulenceProperties','simulationType RAS;\nRAS { RASModel kOmegaSST; turbulence on; printCoeffs on; }')
        fields={
            'U': ('volVectorField','[0 1 -1 0 0 0 0]','(0 3 0)', 'fixedValue; value uniform (0 3 0);', 'zeroGradient;', 'noSlip;'),
            'p': ('volScalarField','[0 2 -2 0 0 0 0]','0','zeroGradient;','fixedValue; value uniform 0;','zeroGradient;'),
            'k': ('volScalarField','[0 2 -2 0 0 0 0]','.00135','fixedValue; value uniform .00135;','inletOutlet; inletValue uniform .00135; value uniform .00135;','kqRWallFunction; value uniform .00135;'),
            'omega': ('volScalarField','[0 0 -1 0 0 0 0]','13.416407865','fixedValue; value uniform 13.416407865;','inletOutlet; inletValue uniform 13.416407865; value uniform 13.416407865;','omegaWallFunction; value uniform 13.416407865;'),
            'nut': ('volScalarField','[0 2 -1 0 0 0 0]','0','calculated; value uniform 0;','calculated; value uniform 0;','nutUSpaldingWallFunction; value uniform 0;'),
        }
        for name,(cls,dim,val,ib,ob,wb) in fields.items():
            put(case,'0/'+name,f'dimensions {dim};\ninternalField uniform {val};\nboundaryField {{ inlet {{ type {ib} }} outlet {{ type {ob} }} "(duct|plate|outside).*" {{ type {wb} }} }}',cls)
        put(case,'system/fvSchemes','''
ddtSchemes { default steadyState; }
gradSchemes { default cellLimited Gauss linear 1; }
divSchemes { default none;
 div(phi,U) bounded Gauss linearUpwind grad(U);
 div(phi,k) bounded Gauss upwind;
 div(phi,omega) bounded Gauss upwind;
 div((nuEff*dev2(T(grad(U))))) Gauss linear;
}
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
SIMPLE { nNonOrthogonalCorrectors 1;
 residualControl { p 1e-5; U 1e-6; "(k|omega)" 1e-6; }
}
relaxationFactors { fields { p .3; } equations { U .6; k .5; omega .5; } }
''')
        functions=f'''
 gridProbes {{ type probes; libs ("libsampling.dll"); writeControl timeStep; writeInterval 10;
  fields (U p k); probeLocations ({point_text}); }}
 inletFlux {{ type surfaceFieldValue; libs ("libfieldFunctionObjects.dll"); writeControl timeStep; writeInterval 10;
  regionType patch; name inlet; operation sum; fields (phi); writeFields false; }}
 outletFlux {{ type surfaceFieldValue; libs ("libfieldFunctionObjects.dll"); writeControl timeStep; writeInterval 10;
  regionType patch; name outlet; operation sum; fields (phi); writeFields false; }}
 inletP {{ type surfaceFieldValue; libs ("libfieldFunctionObjects.dll"); writeControl timeStep; writeInterval 10;
  regionType patch; name inlet; operation areaAverage; fields (p); writeFields false; }}
 yPlus {{ type yPlus; libs ("libfieldFunctionObjects.dll"); writeControl writeTime; }}
'''
        put(case,'system/controlDict',f'''
application simpleFoam; startFrom latestTime; startTime 0; stopAt endTime; endTime 1000;
deltaT 1; writeControl timeStep; writeInterval 250; purgeWrite 2;
writeFormat ascii; writePrecision 9; writeCompression off; timeFormat general; timePrecision 6;
runTimeModifiable true; functions {{ {functions} }}
''')
        sets=[]
        for name,y in [('upstream',-.10),('tip',points[0][1]),('near',-.02),('wake',.02),('far',.10)]:
            pp='\n'.join(f'({x:.7f} {y:.10f} {z:.7f})' for z in np.linspace(-.037,.037,41) for x in np.linspace(-.037,.037,41) if duct.contains(__import__('shapely').Point(x,z)))
            sets.append(f'{name} {{ type cloud; axis xyz; points ({pp}); }}')
        # The x=0 plane cuts the central row of holes and ribs.
        pp='\n'.join(f'(0 {y:.7f} {z:.7f})' for z in np.linspace(-.038,.038,77) for y in np.linspace(-.14,.14,141))
        sets.append(f'longitudinal {{ type cloud; axis xyz; points ({pp}); }}')
        put(case,'system/sample',f'type sets; libs ("libsampling.dll"); interpolationScheme cellPoint; setFormat raw; fields (U p k); sets ( {" ".join(sets)} );')
        config=dict(case=case.name,solver='simpleFoam',nominal_velocity_ms=3,rho_kgm3=1.2,nu_m2s=1.5e-5,
                    inlet_ti=.01,turbulence_length_m=.005,base_mm=args.base_mm,plate_surface_cell_mm=90/n/8,
                    duct_contour_area_mm2=duct.area*1e6,plate_present=include,probe_present=False,
                    upstream_m=.2,downstream_m=.2,probe_plane_m=points[0][1],model='steady kOmegaSST RANS',
                    plate_layers=args.plate_layers,duct_layers=3,
                    limitations=['Constant-section surrogate, not full tunnel/fan','0.2 mm peripheral gaps may be underresolved','No Pitot probe body; no static-port calibration','Steady RANS does not resolve vortex shedding'])
        (case/'case_metadata.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
        print(case)

if __name__=='__main__': main()
