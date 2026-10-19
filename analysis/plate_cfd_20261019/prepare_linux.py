"""Create independent Linux cases, preserving native logs and checkpoints."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT=Path(__file__).resolve().parent


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('source');ap.add_argument('target')
    ap.add_argument('--time',default='0')
    ap.add_argument('--end',type=float,required=True)
    ap.add_argument('--average-start',type=float,default=.15)
    ap.add_argument('--transient-template')
    ap.add_argument('--reset-time',action='store_true')
    args=ap.parse_args()
    source=(ROOT/'cases'/args.source).resolve(); target=(ROOT/'cases'/args.target).resolve()
    assert source.is_relative_to(ROOT/'cases') and target.is_relative_to(ROOT/'cases')
    if target.exists():raise RuntimeError('Refusing to overwrite existing Linux case')
    processors=sorted(source.glob('processor[0-9]*'))
    assert processors and all((p/args.time/'U').exists() for p in processors)
    for name in ['constant','system']:
        origin=ROOT/'cases'/args.transient_template if name=='system' and args.transient_template else source
        shutil.copytree(origin/name,target/name)
    shutil.copy2(source/'system/decomposeParDict',target/'system/decomposeParDict')
    target_time='0' if args.reset_time else args.time
    for p in processors:
        dest=target/p.name
        shutil.copytree(p/'constant',dest/'constant')
        (dest/target_time).mkdir()
        for name in ['U','p','k','omega','nut','phi']:
            if (p/args.time/name).exists():shutil.copy2(p/args.time/name,dest/target_time/name)
    for name in ['case_metadata.json','mesh_diagnostic_acceptance.json']:
        shutil.copy2(source/name,target/name)
    for p in (target/'system').iterdir():
        if p.is_file():p.write_text(p.read_text().replace('.dll','.so'),encoding='ascii')
    control=target/'system/controlDict'; text=control.read_text()
    text=re.sub(r'stopAt\s+\w+;', 'stopAt endTime;', text)
    text=re.sub(r'endTime\s+[^;]+;',f'endTime {args.end};',text)
    text=re.sub(r'timeStart\s+[^;]+;',f'timeStart {args.average_start};',text)
    text=text.replace('type fieldAverage;', 'type fieldAverage; writeControl writeTime;')
    # Align the first full-field write with a short pilot endpoint. Shortening
    # endTime during a run can otherwise leave only monitors, not a final field.
    save_period=min(.005,args.end-float(target_time))
    if save_period<=0:raise ValueError('End time must exceed the checkpoint time')
    text=re.sub(r'(writeControl adjustableRunTime;\s*writeInterval)\s+[^;]+;',
                rf'\g<1> {save_period:.12g};',text)
    text=text.replace('purgeWrite 3;', 'purgeWrite 2;')
    control.write_text(text,encoding='ascii')
    meta=json.loads((target/'case_metadata.json').read_text())
    meta.update(case=args.target,linux_seed_case=args.source,linux_seed_time=args.time,
                image_tag='opencfd/openfoam-run:2606',end_requested=args.end,
                field_average_start=args.average_start,
                target_time=target_time,transient_template=args.transient_template,
                linux_changes=['library suffix only in clone', 'fieldAverage saves only at solver write times',
                               'restart from specified native checkpoint; old average state excluded'],
                validation_status='Linux comparison diagnostic, not a validated calibration')
    if args.transient_template:
        meta.update(solver='pimpleFoam',model='transient kOmegaSST URANS diagnostic')
    (target/'case_metadata.json').write_text(json.dumps(meta,indent=2))
    files=[p for p in (target/'processor0'/target_time).iterdir() if p.is_file()]
    (target/'linux_clone_provenance.json').write_text(json.dumps({
        'source':args.source,'source_time':args.time,'ranks':len(processors),
        'processor0_field_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    },indent=2))
    print(json.dumps({'target':str(target),'ranks':len(processors),'time':args.time}))

if __name__=='__main__':main()
