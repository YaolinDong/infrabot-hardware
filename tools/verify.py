#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 YaolinDong
"""Check the downloadable files without CAD tools: hashes, units, BOM and links."""
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_bom  # noqa: E402

MM = re.compile(rb'SI_UNIT\s*\(\s*\.MILLI\.\s*,\s*\.METRE\.\s*\)')
HOME_PATH = re.compile(rb'(/home/|/Users/|[A-Z]:\\\\)[^\'"\s]+')
LINK = re.compile(r'!?\[[^\]\n]*\]\(([^)\n]+)\)')
IMG_SRC = re.compile(r'<img[^>]*\ssrc="([^"]+)"')
NATIVE = {'.sldprt', '.sldasm', '.slddrw', '.f3d', '.ipt', '.iam', '.prt', '.asm'}


def check_step(path):
    data = path.read_bytes()
    errors = []
    if not data.startswith(b'ISO-10303-21;'):
        errors.append(f'{path}: not a STEP file')
    if not MM.search(data):
        errors.append(f'{path}: length unit is not millimetres')
    if HOME_PATH.search(data):
        errors.append(f'{path}: contains a local file path')
    return errors


def check(root=ROOT):
    errors = []
    meta = json.loads((root / 'parts.json').read_text())
    listed = [meta['assembly']] + meta['parts']
    for entry in listed:
        path = root / entry['step']
        if not path.is_file():
            errors.append(f'missing {entry["step"]}')
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            errors.append(f'{entry["step"]}: SHA-256 differs from parts.json')
        errors += check_step(path)
    ids = [p['id'] for p in meta['parts']]
    if len(ids) != len(set(ids)):
        errors.append('duplicate part id in parts.json')
    on_disk = {p.relative_to(root).as_posix() for p in root.glob('**/*.step')}
    for extra in sorted(on_disk - {e['step'] for e in listed}):
        errors.append(f'{extra}: not listed in parts.json')
    for path in root.rglob('*'):
        if '.git' in path.parts:
            continue
        if path.suffix.lower() in NATIVE:
            errors.append(f'{path.relative_to(root)}: native CAD file')
    if (root / 'bom.csv').read_text() != build_bom.render(root):
        errors.append('bom.csv is stale; run python3 -B tools/build_bom.py')
    for name in build_bom.stale_readmes(root):
        errors.append(f'{name}: BOM section is stale; run python3 -B tools/build_bom.py')
    for doc in root.glob('**/*.md'):
        if '.git' in doc.parts:
            continue
        text = doc.read_text()
        for target in LINK.findall(text) + IMG_SRC.findall(text):
            url = urlsplit(target)
            if url.scheme or target.startswith('#'):
                continue
            if not (doc.parent / unquote(url.path)).exists():
                errors.append(f'{doc.relative_to(root)}: broken link {target}')
    return errors


def main():
    errors = check()
    for e in errors:
        print('error:', e)
    if not errors:
        print('ok')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
