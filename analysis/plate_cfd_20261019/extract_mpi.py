"""Extract signed, bundled MS-MPI payloads locally without installing a service.

The bootstrapper contains two OLE MSI streams. 7-Zip extracts their embedded
CABs. Original signed bootstrapper is retained; no system files are modified.
"""
from pathlib import Path
import subprocess
import json
import hashlib

ROOT = Path(__file__).resolve().parent
src = ROOT.parent/'plate_cfd_20261018/tools/openfoam2606/thirdParty/msmpisetup.exe'
payload = src.read_bytes()
magic = bytes.fromhex('d0cf11e0a1b11ae1')
offsets, pos = [], 0
while (pos := payload.find(magic, pos)) >= 0:
    offsets.append(pos)
    pos += 8
out = ROOT/'tools/msmpi_payloads'
out.mkdir(parents=True, exist_ok=True)
for i, start in enumerate(offsets):
    end = offsets[i+1] if i+1<len(offsets) else len(payload)
    msi = out/f'payload_{i}.msi'
    msi.write_bytes(payload[start:end])
    subprocess.run(['D:/Program Files/7-Zip/7z.exe','x',str(msi),'-y',f'-o{out/str(i)}'], check=True)
(out/'provenance.json').write_text(json.dumps(dict(source=str(src), sha256=hashlib.sha256(payload).hexdigest(),
                                                  offsets=offsets, system_installation=False), indent=2))
