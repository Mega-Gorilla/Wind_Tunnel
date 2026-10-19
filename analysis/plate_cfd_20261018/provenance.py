"""Record reproducibility metadata and content hashes without credentials."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import os
from report_paths import REPORT_ROOT
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[0]
records={
 'created_utc':datetime.now(timezone.utc).isoformat(),
 'python':platform.python_version(),
 'libraries':{p:importlib.metadata.version(p) for p in ['numpy','scipy','matplotlib','trimesh','shapely','mapbox-earcut','networkx']},
 'sources':[
  {'url':'https://www.openfoam.com/openfoam-mingw-cross-compilation','purpose':'Official Windows native distribution instructions'},
  {'url':'https://sourceforge.net/projects/openfoam/files/v2606/OpenFOAM-v2606-windows-mingw.exe/download','purpose':'Installer obtained through official OpenFOAM download links'},
  {'url':'https://www.grc.nasa.gov/www/wind/valid/tutorial/iterconv.html','purpose':'Residual and engineering-output convergence checks'},
  {'url':'https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html','purpose':'Grid-sensitivity assessment; two meshes do not establish observed order'},
  {'url':'https://www.nist.gov/pml/sensor-science/fluid-metrology/wall-and-blockage-effects-air-speed-calibrations','purpose':'Calibration conditions and blockage/wall interference'},
  {'url':'https://doc.openfoam.com/2606/tools/processing/models/turbulence/ras/linear-evm/rtm/kOmegaSST/','purpose':'Turbulence model and inlet k/omega definitions'},
  {'url':'https://doc.openfoam.com/2312/tools/processing/boundary-conditions/rtm/derived/wall/nutUSpaldingWallFunction/','purpose':'Continuous Spalding turbulent-viscosity wall function'}
 ],
 'installation':{'location':str(ROOT/'tools/openfoam2606'),'installer_authenticode':'NotSigned',
                 'binary_banner':'Build 34e226dfe3-20211220 OPENFOAM=2606 version=v2606; LSB;label=32;scalar=64',
                 'method':'7-Zip extraction of official NSIS payload; no system-wide installation',
                 'pstream':'Bundled libPstream.dll-dummy copied to task-local libPstream.dll for serial execution',
                 'msmpi_installed':False,'freecad_installed':False},
 'hashes':{}
}
for pattern in ['*.py','*.md','case_selection.json','solver_adjustments.json','results/*.json','results/*.png','geometry/*.json','downloads/*.exe','cases/*/system/*','cases/*/constant/*Properties','cases/*/0/*','cases/*/log.*']:
 for p in sorted(ROOT.glob(pattern)):
  if p.is_file():records['hashes'][p.relative_to(ROOT).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
for path in sorted(REPORT_ROOT.rglob('*')):
 if path.is_file():records['hashes'][os.path.relpath(path,ROOT).replace('\\','/')]=hashlib.sha256(path.read_bytes()).hexdigest()
# Preserve the original measurement-time provenance as an immutable historical record.
(ROOT/'provenance_current.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
print('Wrote provenance_current.json:',len(records['hashes']),'hashes')
