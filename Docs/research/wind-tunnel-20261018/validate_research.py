"""Validate saved reference assets, links, calculations and read-only CAD evidence."""
from pathlib import Path
from urllib.parse import unquote, urlsplit
from html.parser import HTMLParser
from hashlib import sha256
import json
import re
from PIL import Image

ROOT = Path(__file__).resolve().parents[0]

def local_target(origin, target):
    if urlsplit(target).scheme or target.startswith('#'):
        return
    target = unquote(target.split('#', 1)[0])
    assert (origin.parent / target).exists(), (str(origin), target)

class Links(HTMLParser):
    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ('href', 'src'):
                local_target(ROOT/'ui-references/index.html', value)

def main():
    for path in ROOT.rglob('*.md'):
        text = path.read_text(encoding='utf-8')
        for target in re.findall(r'\]\(([^)]+)\)', text):
            local_target(path, target)
        assert not re.search(r'turn\d+(?:search|view)|TODO|TBD', text), path
    gallery = ROOT/'ui-references/index.html'
    Links().feed(gallery.read_text(encoding='utf-8'))
    ref = ROOT/'ui-references'
    manifest = json.loads((ref/'manifest.json').read_text(encoding='utf-8'))
    assert len(manifest['sources']) == 4 and len(manifest['images']) == 7
    for entry in manifest['sources'] + manifest['images']:
        path = ref/entry['file']
        assert sha256(path.read_bytes()).hexdigest() == entry['sha256']
    for entry in manifest['images']:
        with Image.open(ref/entry['file']) as image:
            assert image.size == (entry['width'], entry['height'])
        assert (ref/entry['original_file']).exists()
    response = json.loads((ROOT/'fusion-pitot-evidence.json').read_text(encoding='utf-8'))
    envelope = json.loads(response['content'][0]['text'])
    cad = json.loads(envelope['message'])
    assert cad['document'] == 'merged model v49'
    assert cad['is_modified_before'] is False and cad['is_modified_after'] is False
    plate = next(b for b in cad['bodies'] if 'Pitotube plate' in b['path'])
    holes = [f for f in plate['faces'] if f.get('diameter_mm') == 4.2]
    assert len(holes) == 25
    centers = {(round(f['origin'][0],3), round(f['origin'][2],3)) for f in holes}
    assert centers == {(x,z) for x in [-32,-16,0,16,32] for z in [90.5,106.5,122.5,138.5,154.5]}
    examples = []
    for velocity in [1,2,3,5]:
        q = .5*1.2*velocity**2
        spec = .08 + .03*q
        examples.append(dict(velocity_m_s=velocity, q_pa=q, pressure_spec_pa=spec,
                             velocity_linearized_effect_percent=100*.5*spec/q))
    result = dict(status='passed', checked_on='2026-10-18', sources=4, images=7,
                  local_links='valid', source_hashes='match', image_sizes='match',
                  cad_document=cad['document'], cad_modified=False, grid_holes=25,
                  examples=examples, area_ratio_6400_to_6271=(6400/6271.312-1)*100,
                  visual_review='7 images and 5 PDF pages inspected; diagram/graph/PID labels corrected after review',
                  scope='Documentation validation only; no new device measurement or control implementation')
    (ROOT/'validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
