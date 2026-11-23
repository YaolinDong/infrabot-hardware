# Contributing

For fit or machining issues, give the part id from `bom.csv`, the feature and the measured dimension in millimetres. Name the mating part, such as a motor, bearing or neighbouring plate. A photo of the interference helps.

For a geometry change, exported STEP files replace the files under `parts/` and `assembly/` byte for byte. After a change, update the hashes, volume and mass in `parts.json`. Then run:

```bash
python3 -B tools/build_bom.py
python3 -B tools/render_previews.py
python3 -B tools/verify.py
python3 -B -m unittest discover -s tests -v
```

Do not commit native CAD files (`.SLDPRT`, `.SLDASM`). `tools/verify.py` rejects them.

Commits use English messages in the form `type(scope): description`.
