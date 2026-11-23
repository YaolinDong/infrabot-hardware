# SPDX-License-Identifier: MIT
# Copyright (c) 2026 YaolinDong
import csv
import json
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import verify  # noqa: E402


class Files(unittest.TestCase):
    def test_snapshot_passes(self):
        self.assertEqual(verify.check(), [])

    def test_bom_matches_parts(self):
        parts = json.loads((ROOT / 'parts.json').read_text())['parts']
        rows = list(csv.DictReader((ROOT / 'bom.csv').read_text().splitlines()))
        machined = [r for r in rows if r['category'] == 'machined']
        self.assertEqual([r['item'] for r in machined], [p['id'] for p in parts])
        self.assertEqual(sum(int(r['quantity']) for r in machined), 48)
        motors = {r['item']: int(r['quantity']) for r in rows if r['category'] == 'purchased'}
        self.assertEqual(sum(motors.values()), 7)

    def test_mass_follows_volume(self):
        meta = json.loads((ROOT / 'parts.json').read_text())
        density = meta['density_g_per_cm3'] / 1000
        for p in meta['parts']:
            self.assertAlmostEqual(p['mass_g'], p['volume_mm3'] * density, delta=0.06, msg=p['id'])

    def test_readme_bom_lists_every_part(self):
        parts = json.loads((ROOT / 'parts.json').read_text())['parts']
        for name in ['README.md', 'README.zh-CN.md']:
            text = (ROOT / name).read_text()
            for p in parts:
                self.assertIn(f'({p["step"]})', text, msg=f'{name}: {p["id"]}')
                self.assertTrue((ROOT / 'docs' / 'images' / 'parts' / f'{p["id"]}.png').exists())

    def test_images_share_one_size(self):
        sizes = {}
        for png in sorted((ROOT / 'docs' / 'images').rglob('*.png')):
            head = png.read_bytes()[:24]
            self.assertEqual(head[:8], b'\x89PNG\r\n\x1a\n', msg=png.name)
            sizes[png.relative_to(ROOT).as_posix()] = struct.unpack('>II', head[16:24])
        self.assertEqual(set(sizes.values()), {(1200, 900)}, msg=sizes)

    def test_every_link_has_parts(self):
        links = {p['link'] for p in json.loads((ROOT / 'parts.json').read_text())['parts']}
        self.assertEqual(links, {'baselink', *(f'link{i}' for i in range(1, 8))})


class Rejects(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for name in ['parts.json', 'bom.csv']:
            shutil.copy(ROOT / name, self.tmp / name)
        meta = json.loads((ROOT / 'parts.json').read_text())
        self.part = meta['parts'][-1]
        self.small = {'assembly': self.part, 'parts': [self.part],
                      'density_g_per_cm3': meta['density_g_per_cm3']}
        (self.tmp / 'parts.json').write_text(json.dumps(self.small))
        target = self.tmp / self.part['step']
        target.parent.mkdir(parents=True)
        shutil.copy(ROOT / self.part['step'], target)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def errors(self):
        return [e for e in verify.check(self.tmp) if 'bom.csv' not in e]

    def test_clean_copy(self):
        self.assertEqual(self.errors(), [])

    def test_modified_step(self):
        with (self.tmp / self.part['step']).open('ab') as f:
            f.write(b'\n')
        self.assertTrue(any('SHA-256' in e for e in self.errors()))

    def test_native_cad(self):
        (self.tmp / 'parts' / 'x.SLDPRT').write_bytes(b'')
        self.assertTrue(any('native CAD' in e for e in self.errors()))

    def test_unlisted_step(self):
        shutil.copy(self.tmp / self.part['step'], self.tmp / 'parts' / 'extra.step')
        self.assertTrue(any('not listed' in e for e in self.errors()))

    def test_stale_readme_bom(self):
        section = verify.build_bom.bom_section(self.small['parts'], 'en')
        (self.tmp / 'README.md').write_text(f'# x\n\n{section}\n')
        self.assertEqual(verify.build_bom.stale_readmes(self.tmp), [])
        (self.tmp / 'README.md').write_text(f'# x\n\n{section.replace("| 1 |", "| 2 |")}\n')
        self.assertEqual(verify.build_bom.stale_readmes(self.tmp), ['README.md'])

    def test_local_path(self):
        bad = self.tmp / 'bad.step'
        bad.write_bytes(b"ISO-10303-21;\nSI_UNIT(.MILLI.,.METRE.)\nFILE_NAME('/home/someone/x.step');")
        self.assertTrue(any('local file path' in e for e in verify.check_step(bad)))


if __name__ == '__main__':
    unittest.main()
