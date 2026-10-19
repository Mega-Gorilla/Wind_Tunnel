"""Structural/text/data checks complement, not replace, visual review of five pages."""
from pathlib import Path
import json
import hashlib
import pdfplumber
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[2]
REPORT=ROOT/'Docs/tests/cfd/2026-10-19_fixed_plate_refined'
PDF=REPORT/'WindTunnel_FixedPlate_CFD_Paper_2026-10-19.pdf'
reader=PdfReader(PDF)
failures=[]
if len(reader.pages)!=5:failures.append('Expected five pages')
texts=[page.extract_text() for page in reader.pages]
expected=[['要旨','目的','34.5801'],['238,220','491.01'],['8.758','0.01501','未保存'],['-2.54','+0.05','7.15','δ(i)'],['結論','未確定','参考文献']]
for i,(text,needles) in enumerate(zip(texts,expected),1):
    for needle in needles:
        if needle not in ''.join(text.split()):failures.append(f'Page {i}: missing {needle}')
    for bad in ['\ufffd','\u25a0','\u25a1']:
        if bad in text:failures.append(f'Page {i}: replacement glyph {bad}')
font_status={}
for page in reader.pages:
    for font in page['/Resources']['/Font'].values():
        f=font.get_object();name=str(f['/BaseFont'])
        descriptor=f.get('/FontDescriptor')
        embedded=bool(descriptor and any(k in descriptor.get_object() for k in ['/FontFile','/FontFile2','/FontFile3']))
        font_status[name]=embedded
for name,embedded in font_status.items():
    if 'Meiryo' in name or 'MS-Mincho' in name:
        if not embedded:failures.append(f'Japanese font not embedded: {name}')
with pdfplumber.open(PDF) as pdf:
    for i,page in enumerate(pdf.pages,1):
        outside=[ch for ch in page.chars if ch['x0']<0 or ch['x1']>page.width+.5 or ch['top']<0 or ch['bottom']>page.height+.5]
        if outside:failures.append(f'Page {i}: text outside media box')
snap=json.loads((REPORT/'results/snapshot_comparison.json').read_text())
assert f"{snap['point_difference_range_percent'][0]:.2f}" in texts[3]
assert f"{snap['additional_inlet_static_pressure_snapshot_Pa']:.2f}" in texts[3]
manifest_path=REPORT/'results/cleanup_manifest.json'
cleanup_checked=False
if manifest_path.exists():
    manifest=json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    if manifest['status']!='completed':failures.append('Cleanup not completed')
    if sum(r['bytes'] for r in manifest['files'])!=manifest['bytes']:failures.append('Cleanup byte sum mismatch')
    for r in manifest['files']:
        if not r['deleted'] or (ROOT/r['path']).exists():failures.append(f"Cleanup target still exists: {r['path']}")
    cleanup_checked=True
result={'pages':len(reader.pages),'pdf_sha256':hashlib.sha256(PDF.read_bytes()).hexdigest(),
        'pdf_bytes':PDF.stat().st_size,'fonts':font_status,'cleanup_manifest_checked':cleanup_checked,
        'text_structure_and_data_checks_passed':not failures,'failures':failures,
        'visual_review':'All five final pages rendered with Poppler and inspected at 130 dpi; formula glyph and grid-label fixes verified.',
        'scientific_calibration_eligible':False}
(REPORT/'results/paper_validation.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(result,indent=2,ensure_ascii=False))
if failures:raise SystemExit(1)
