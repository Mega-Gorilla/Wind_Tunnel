"""Read-only Git payload audit. Never contacts hardware or prints secret values.

--staged reads actual index blobs, not unstaged worktree content. --documents
also extracts PDF text (pypdf required); it is not OCR or a disclosure guarantee.
"""
import argparse
from collections import Counter
import io
import json
from pathlib import Path
import posixpath
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
MAX_BYTES = 50 * 1024 * 1024
TEXT_EXT = {'.py', '.c', '.h', '.md', '.txt', '.json', '.jsonl', '.csv', '.tsv',
            '.ps1', '.sh', '.js', '.cjs', '.mjs', '.html', '.css', '.xml', '.svg',
            '.yml', '.yaml', '.ini', '.cfg', '.service', '.desktop', '.wrl', '.step', '.stp'}
REQUIRED = (
    'Electronics/pico/pcb_rev_e/WindTunnel_Pico_Carrier_RevE.kicad_pro',
    'Electronics/pico/pcb_rev_e/WindTunnel_Pico_Carrier_RevE.kicad_sch',
    'Electronics/pico/pcb_rev_e/WindTunnel_Pico_Carrier_RevE.kicad_pcb',
    'Electronics/pico/pcb_rev_e/Carrier.kicad_sym',
    'Electronics/manufacturing/RevE/WindTunnel_Pico_Carrier_RevE_JLCPCB_Gerber.zip',
    'Electronics/pico/firmware/control_main.py', 'software/control/windtunnel/app.py',
    'Docs/README.md', '.gitignore', '.gitattributes', 'CONTRIBUTING.md',
)
SECRET_RULES = {
    'private-key': re.compile(r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'),
    'github-token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b'),
    'aws-access-key': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'credential-url': re.compile(r'https?://[^\s/:]+:[^\s/@]+@'),
    'literal-credential': re.compile(
        r'''(?i)\b(?:password|passwd|api[_-]?key|access[_-]?token|client[_-]?secret|psk)\b["']?\s*[:=]\s*["']([^"'\r\n]{4,})["']'''),
}


def git(*args, data=None):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], input=data)


def secret_findings(name, text):
    found = []
    for rule, pattern in SECRET_RULES.items():
        for match in pattern.finditer(text):
            # Exact, explicitly non-secret documentation placeholders only.
            if rule == 'literal-credential' and match.group(1) in {
                '<PASSWORD>', '<TOKEN>', 'REPLACE_ME', 'EXAMPLE_ONLY', 'not-a-secret'}:
                continue
            found.append({'file': name, 'line': text.count('\n', 0, match.start()) + 1,
                          'rule': rule})
    return found


def is_text(name):
    p = Path(name)
    return (p.suffix.lower() in TEXT_EXT or p.suffix.startswith('.kicad_')
            or p.name in {'fp-lib-table', 'sym-lib-table', '.gitignore', '.gitattributes'}
            or '/system/' in name or p.name.endswith('Properties'))


def public_findings(name, text):
    """Detect personal profile paths, without returning their values."""
    rules = {
        'personal-windows-path': r'(?i)[A-Z]:[/\\]+Users[/\\]+[A-Z0-9_.-]+',
        'personal-home-path': r'/home/(?!ofuser/)[A-Za-z0-9_.-]+',
    }
    return [{'file': name, 'line': text.count('\n', 0, match.start()) + 1, 'rule': rule}
            for rule, pattern in rules.items() for match in re.finditer(pattern, text)]


def public_path_error(name, policy):
    """Allow only reviewed standalone CAD; catch CAD hidden in archives too."""
    suffix = Path(name).suffix.lower()
    if suffix in policy['cad_extensions'] and name not in policy['allowed_cad']:
        return 'unreviewed-cad'
    if name in policy['excluded_files']:
        return 'excluded-publication-file'
    if any(name.startswith(prefix) for prefix in policy['excluded_prefixes']):
        return 'excluded-publication-prefix'
    return None


def normalize_link(origin, target):
    from urllib.parse import unquote, urlsplit
    target = target.strip('<>').split('#', 1)[0].split('?', 1)[0]
    if not target or urlsplit(target).scheme:
        return None
    return posixpath.normpath(posixpath.join(posixpath.dirname(origin), unquote(target)))


def is_present(target, paths):
    return target in paths or any(p.startswith(target.rstrip('/') + '/') for p in paths)


def staged_files():
    entries = []
    for entry in git('ls-files', '--stage', '-z').split(b'\0'):
        if not entry:
            continue
        meta, path = entry.split(b'\t', 1)
        mode, oid, stage = meta.decode().split()
        if stage != '0':
            raise RuntimeError('Unmerged index; resolve conflicts before auditing')
        entries.append((path.decode('utf-8'), mode, oid))
    with subprocess.Popen(['git', '-C', str(ROOT), 'cat-file', '--batch'],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE) as proc:
        for name, mode, oid in entries:
            proc.stdin.write((oid + '\n').encode())
            proc.stdin.flush()
            header = proc.stdout.readline().split()
            size = int(header[2])
            blob = proc.stdout.read(size)
            if proc.stdout.read(1) != b'\n':
                raise RuntimeError('Invalid git cat-file framing')
            yield name, mode, blob
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError('git cat-file failed')


def worktree_files():
    names = git('ls-files', '--cached', '--others', '--exclude-standard', '-z')
    for name in sorted(set(n.decode('utf-8') for n in names.split(b'\0') if n)):
        path = ROOT / name
        if path.is_symlink():
            yield name, '120000', b''
        elif path.is_file():
            yield name, '100644', path.read_bytes()
        else:
            raise RuntimeError('Missing candidate: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true')
    parser.add_argument('--documents', action='store_true')
    parser.add_argument('--public', action='store_true', help='Enforce reviewed CAD and public-document boundaries')
    args = parser.parse_args()
    if args.documents:
        from pypdf import PdfReader
    paths, texts, folded = set(), {}, {}
    errors, secrets_found, local_links = [], [], []
    count = Counter()
    total = 0
    largest = []
    policy = None
    if args.public:
        policy_path = 'tools/repository/publication_policy.json'
        policy = json.loads(git('show', ':' + policy_path) if args.staged
                            else (ROOT / policy_path).read_bytes())

    def inspect(name, blob, nested=False):
        if policy:
            rule = public_path_error(name, policy)
            if rule:
                errors.append({'file': name, 'rule': rule})
        if is_text(name):
            text = blob.decode('utf-8-sig', errors='replace')
            secrets_found.extend(secret_findings(name, text))
            if policy:
                secrets_found.extend(public_findings(name, text))
            if not nested:
                texts[name] = text
            count['text_files'] += 1
        elif name.lower().endswith('.pdf') and args.documents:
            try:
                reader = PdfReader(io.BytesIO(blob))
                text = '\n'.join(page.extract_text() or '' for page in reader.pages)
                text += '\n' + str(reader.metadata)
                secrets_found.extend(secret_findings(name, text))
                if policy:
                    secrets_found.extend(public_findings(name, text))
                count['pdf_files'] += 1
            except Exception as exc:
                errors.append({'file': name, 'rule': 'pdf-extraction', 'error_type': type(exc).__name__})
        elif name.lower().endswith(('.zip', '.xlsx', '.docx', '.pptx')):
            try:
                with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                    members = archive.infolist()
                    if len(members) > 10000 or sum(m.file_size for m in members) > 128 * 1024 * 1024:
                        errors.append({'file': name, 'rule': 'archive-review-required'})
                        return
                    for member in members:
                        if member.is_dir():
                            continue
                        if member.flag_bits & 1:
                            errors.append({'file': name, 'rule': 'encrypted-archive'})
                            continue
                        if not nested:
                            inspect(name + '::' + member.filename, archive.read(member), True)
                count['archives'] += 1
            except (zipfile.BadZipFile, RuntimeError):
                errors.append({'file': name, 'rule': 'unreadable-archive'})

    for name, mode, blob in (staged_files() if args.staged else worktree_files()):
        paths.add(name)
        if name.casefold() in folded and folded[name.casefold()] != name:
            errors.append({'file': name, 'rule': 'case-collision'})
        folded[name.casefold()] = name
        if mode == '120000' or mode == '160000':
            errors.append({'file': name, 'rule': 'symlink-or-embedded-repo'})
        parts = set(name.split('/'))
        if parts & {'.local', '.runtime', '.venv', 'node_modules', '__pycache__'}:
            errors.append({'file': name, 'rule': 'private-or-generated-path'})
        if len(blob) > MAX_BYTES:
            errors.append({'file': name, 'rule': 'over-50-MiB', 'bytes': len(blob)})
        total += len(blob)
        largest.append((len(blob), name))
        inspect(name, blob)
    if not paths:
        errors.append({'rule': 'empty-payload'})
    for name in REQUIRED:
        if name not in paths:
            errors.append({'file': name, 'rule': 'missing-required-file'})

    missing_links = []
    for name, text in texts.items():
        if name.endswith('.md'):
            # Drop code fences: template paths and examples are not hyperlinks.
            prose = re.sub(r'```.*?```', '', text, flags=re.S)
            for raw in re.findall(r'\]\(([^)]+)\)', prose):
                target = normalize_link(name, raw)
                if target and not is_present(target, paths):
                    missing_links.append((name, target))
                elif target:
                    count['local_links'] += 1
        if name.endswith(('fp-lib-table', 'sym-lib-table', '.kicad_pcb', '.kicad_sch')):
            refs = re.findall(r'\((?:uri|model)\s+"\$\{KIPRJMOD\}/([^"\n]+)"', text)
            if name.endswith('.kicad_sch'):
                refs += re.findall(r'\(property\s+"Sheetfile"\s+"([^"\n]+)"', text)
            if name.endswith('.kicad_pcb'):
                refs += ['WindTunnel.pretty/' + fp + '.kicad_mod' for fp in
                         set(re.findall(r'\(footprint\s+"WindTunnel:([^"\n]+)"', text))]
            for ref in refs:
                target = normalize_link(name, ref)
                count['kicad_references'] += 1
                if target is None or not is_present(target, paths):
                    errors.append({'file': name, 'target': ref, 'rule': 'missing-kicad-dependency'})
            if re.search(r'\((?:uri|model)\s+"(?:[A-Za-z]:[/\\]|/home/|/Users/)', text):
                errors.append({'file': name, 'rule': 'absolute-kicad-dependency'})

    if missing_links:
        candidates = sorted(set(t for _, t in missing_links))
        proc = subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '--no-index', '-z', '--stdin'],
                              input=b'\0'.join(t.encode() for t in candidates) + b'\0',
                              capture_output=True)
        if proc.returncode not in (0, 1):
            raise RuntimeError('git check-ignore failed')
        ignored = set(x.decode() for x in proc.stdout.split(b'\0') if x)
        for name, target in missing_links:
            if is_present(target.casefold(), {p.casefold() for p in paths}):
                errors.append({'file': name, 'target': target, 'rule': 'link-case-mismatch'})
            elif target in ignored:
                local_links.append({'file': name, 'target': target})
                if args.public:
                    errors.append({'file': name, 'target': target, 'rule': 'non-public-link-target'})
            else:
                errors.append({'file': name, 'target': target, 'rule': 'missing-link-target'})
    result = dict(passed=not (errors or secrets_found), source='index' if args.staged else 'worktree',
                  files=len(paths), bytes=total, public_policy=bool(policy), checks=dict(count), errors=errors,
                  secret_findings=secrets_found, local_only_links=local_links,
                  largest=[{'file': n, 'bytes': s} for s, n in sorted(largest, reverse=True)[:8]],
                  limitations=['Pattern-based scan, not a guarantee of absence of secrets.',
                               'PDF text extraction is not OCR; images and opaque CAD need owner review.',
                               'ERC/DRC and hardware operation are not performed.'])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
