"""Check effective open area and wall layer representation of the generated mesh."""
import argparse
import json
import re
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[0]

def list_body(path):
    text=path.read_text()
    text=re.sub(r'/\*.*?\*/','',text,flags=re.S)
    text=re.sub(r'//[^\n]*','',text)
    m=re.search(r'\n\s*(\d+)\s*\n\(',text)
    assert m,path
    return int(m[1]),text[m.end():]

def metrics(case):
    mesh=case/'constant/polyMesh'
    n,s=list_body(mesh/'points')
    points=np.array([np.fromstring(x,sep=' ') for x in re.findall(r'\(([^()]+)\)',s)[:n]])
    n,s=list_body(mesh/'faces')
    faces=[np.fromstring(x,sep=' ',dtype=np.int64) for x in re.findall(r'\d+\(([^()]+)\)',s)[:n]]
    patches={}
    text=(mesh/'boundary').read_text()
    for name,body in re.findall(r'(\w+)\s*\{([^{}]*)\}',text):
        start=re.search(r'startFace\s+(\d+)',body);cnt=re.search(r'nFaces\s+(\d+)',body)
        if not start or not cnt:continue
        a=int(start[1]);b=a+int(cnt[1]);areas=[];vectors=[]
        for f in faces[a:b]:
            p=points[f]; v=np.sum(np.cross(p,np.roll(p,-1,axis=0)),axis=0)/2
            areas.append(np.linalg.norm(v));vectors.append(v)
        vv=np.array(vectors)
        patches[name]={'faces':b-a,'surface_area_mm2':float(np.sum(areas)*1e6),
                       'positive_y_projection_mm2':float(np.maximum(vv[:,1],0).sum()*1e6) if len(vv) else 0,
                       'negative_y_projection_mm2':float(np.maximum(-vv[:,1],0).sum()*1e6) if len(vv) else 0}
    result={'case':case.name,'patches':patches}
    if 'plate' in patches:
        result['plate_projected_blockage_fraction']=patches['plate']['positive_y_projection_mm2']/patches['inlet']['surface_area_mm2']
    (case/'mesh_metrics.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('case');args=ap.parse_args();metrics(ROOT/'cases'/args.case)
