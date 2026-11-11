# 12 - Mechanical

Source: `mechanical/enclosure.py` (CadQuery, parametric). Outputs in `mechanical/out/`: STEP, STL and 3MF for each printable part, an assembly STEP with keep-out volumes for the bought-in modules, five SVG line drawings and `check_report.md`.

Regenerate: `pip install cadquery && python mechanical/enclosure.py`. The script exits non-zero if any part is not a single valid solid, if a shell clashes with a module keep-out, or if the depth stack does not fit. Those checks caught two real errors while this was written (a bumper cut in two by its port windows; a PCB wider than the screw bosses).

## Rev A concept

| | |
|---|---|
| Envelope | 108 x 212 x 40 mm (114 x 218 with bumper) |
| Parts | Front shell, rear shell, battery door, TPU bumper |
| Shell mass | About 173 g of PC/ABS + 63 g bumper (computed from volume) |
| Estimated device mass | About 600-650 g with a 3-cell pack (about 210 g), display, board and hardware. Estimate, not weighed |
| Display | Portrait, behind a raised 1.5 mm bezel lip that stands proud of the glass |
| Keys | D-pad + OK on the left, Back / Home / Fn on the right; 11 mm openings |
| Ports | Two RJ45 on the top end, USB-C on the bottom end |
| Grip | Ribs both sides of the battery door; bumper band |
| Lanyard | Reinforced lug with a through hole, top-left corner |
| Service | Six M2.5 screws into heat-set inserts; battery behind a two-screw door |

## What is not done

- **Display module dimensions are TBC.** Active area (62.1 x 110.4 mm) is from the maker's page; the 90 x 143.5 x 8 mm module envelope is from retailer listings. Get the mechanical drawing before printing.
- No draft angles, ribs, snap fits, lip-and-groove at the split, or gasket: it will 3D-print, it will not mould.
- Battery door has no latch or seal detail; the door opening has no support lip.
- Keypad (silicone web with actuators and light pipes) is not modelled.
- Depth margin at the battery is 0.6 mm. Too tight for a real pack with wrap and tolerance: expect the depth to grow 1-2 mm.
- No ingress rating is designed. IP54 would need gasketed seams and port covers.
- **No realistic renders.** Only line drawings are produced here. Import `netscope_x1_assembly.step` into Fusion 360, KeyShot or Blender for renders.
- No editable native CAD besides the CadQuery script; STEP imports into any MCAD tool.

## Printing the fit-check

Front and rear shells: MJF or SLS nylon, or FDM in PETG/ASA at 0.2 mm with the outer face down. Bumper: TPU 95A. Fit M2.5 heat-set inserts in the six front bosses.
