#!/usr/bin/env python3
"""Seed the main-board .kicad_pcb from the floorplan, using KiCad's own Python API.

    python3 tools/seed_kicad_pcb.py [--force]      # needs KiCad 9's `pcbnew` module

Writes hardware/kicad/netscope-x1/netscope-x1.kicad_pcb with:
  * the board outline (88 x 88 mm plus the microSD tab) on Edge.Cuts,
  * the four M2.5 mounting holes as real footprints (KiCad library copy),
  * every floorplan part as a labelled rectangle: front parts on Dwgs.User,
    back parts on Cmts.User.  These are placement GUIDES, not footprints.

It is a starting file for layout, not a layout: no part footprints, no nets,
no tracks, and the 6-layer stack-up is KiCad's default, not a fab stack-up.
Unlike the schematic this file is meant to be edited by hand afterwards, so
the script refuses to overwrite it without --force.
"""
import shutil
import sys
import tempfile
from pathlib import Path

import pcbnew
import yaml

ROOT = Path(__file__).resolve().parents[1]
FLOORPLAN = ROOT / "hardware/pcb/floorplan.yaml"
OUT = ROOT / "hardware/kicad/netscope-x1/netscope-x1.kicad_pcb"
HOLE_LIB = Path("/usr/share/kicad/footprints/MountingHole.pretty")
HOLE_FP = "MountingHole_2.7mm_M2.5"
CX, CY = 150.0, 105.0          # board centre on the A4 page, mm


def pt(x: float, y: float) -> "pcbnew.VECTOR2I":
    """Floorplan (origin at board centre, Y up) to KiCad page coordinates (Y down)."""
    return pcbnew.VECTOR2I(pcbnew.FromMM(CX + x), pcbnew.FromMM(CY - y))


def outline(size, tabs):
    """Closed outline for a centred rectangle with rectangular tabs on its top edge."""
    w, h = size[0] / 2, size[1] / 2
    pts = [(-w, -h), (w, -h), (w, h)]
    for x0, y0, x1, y1 in sorted(tabs, key=lambda t: -t[2]):
        if abs(y0 - h) > 1e-6:
            raise SystemExit("only tabs on the top edge are supported")
        pts += [(x1, h), (x1, y1), (x0, y1), (x0, h)]
    pts.append((-w, h))
    return pts


def add_line(board, a, b, layer, width=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(pt(*a))
    s.SetEnd(pt(*b))
    s.SetLayer(layer)
    s.SetWidth(pcbnew.FromMM(width))
    board.Add(s)


def add_rect(board, x, y, w, h, layer):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_RECT)
    s.SetStart(pt(x - w / 2, y + h / 2))
    s.SetEnd(pt(x + w / 2, y - h / 2))
    s.SetLayer(layer)
    s.SetWidth(pcbnew.FromMM(0.1))
    board.Add(s)


def add_text(board, text, x, y, layer, size=1.0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetPosition(pt(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(size), pcbnew.FromMM(size)))
    t.SetTextThickness(pcbnew.FromMM(size * 0.15))
    board.Add(t)


def main() -> None:
    if OUT.exists() and "--force" not in sys.argv:
        raise SystemExit(f"{OUT.relative_to(ROOT)} exists; it is hand-edited after seeding. Use --force to replace it.")
    fp = yaml.safe_load(FLOORPLAN.read_text())
    main_board = fp["boards"]["main"]
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(6)
    pts = outline(main_board["size"], main_board.get("tabs", []))
    for a, b in zip(pts, pts[1:] + pts[:1]):
        add_line(board, a, b, pcbnew.Edge_Cuts)
    holes = guides = 0
    for ref, side, x, y, w, h, _height, *flags in main_board["place"]:
        if "hole" in flags:
            f = pcbnew.FootprintLoad(str(HOLE_LIB), HOLE_FP)
            f.SetReference(ref)
            f.SetValue("M2.5")
            f.SetPosition(pt(x, y))
            board.Add(f)
            holes += 1
            continue
        layer = pcbnew.Dwgs_User if side == "F" else pcbnew.Cmts_User
        add_rect(board, x, y, w, h, layer)
        add_text(board, ref, x, y, layer, 1.0 if min(w, h) >= 4 else 0.6)
        guides += 1
    top = main_board["size"][1] / 2 + 12
    add_text(board, "NetScope X1 main board, rev A draft. OUTLINE AND PLACEMENT GUIDES ONLY: not laid out.",
             0, top + 4, pcbnew.Dwgs_User, 1.5)
    add_text(board, "Rectangles: Dwgs.User = front-side parts, Cmts.User = back-side parts (seen through the board).",
             0, top, pcbnew.Dwgs_User, 1.2)
    # SaveBoard also writes a default project file beside the board, which would wipe the
    # generated net classes: save in a scratch directory and take only the board file.
    with tempfile.TemporaryDirectory() as scratch:
        tmp = Path(scratch) / OUT.name
        pcbnew.SaveBoard(str(tmp), board)
        shutil.copyfile(tmp, OUT)
    print(f"wrote {OUT.relative_to(ROOT)}: outline {len(pts)} edges, {holes} mounting holes, {guides} placement guides")


if __name__ == "__main__":
    main()
