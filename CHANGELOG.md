# Changelog

## 0.1.0 — 2026-11-24

- H7C assembly STEP with the joint motors.
- STEP files for the 43 machined parts of the base and the J1–J7 links, under English names. Like the other repositories, the model has no tool flange.
- Bill of materials in both READMEs, one table per sub-assembly with a preview of every part, its STEP link, quantity, envelope and mass.
- `bom.csv` and `parts.json` with the same data, Chinese names and SHA-256 for each part, plus the joint motors.
- Manufacturing notes: 6061 aluminium, GB/T 1804-2000 class m general tolerances, 120-mesh sandblast and natural anodizing.
- An isometric view, front, left and top views, a highlighted view of each sub-assembly in the arm, and a preview of each part.
- `tools/verify.py` and tests that check hashes, units, local paths, BOM, the README BOM sections and links without CAD tools.
