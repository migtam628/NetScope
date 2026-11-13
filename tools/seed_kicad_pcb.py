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
import subprocess
import sys
import tempfile
from pathlib import Path

import pcbnew
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kicad_lib import children, parse, unq  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FLOORPLAN = ROOT / "hardware/pcb/floorplan.yaml"
OUT = ROOT / "hardware/kicad/netscope-x1/netscope-x1.kicad_pcb"
HOLE_LIB = Path("/usr/share/kicad/footprints/MountingHole.pretty")
HOLE_FP = "MountingHole_2.7mm_M2.5"
CX, CY = 150.0, 105.0          # board centre on the A4 page, mm


FP_DIR = Path("/usr/share/kicad/footprints")
TURN = {"J50": 180, "J51": 180}                           # back-side cable connectors: cable leaves at the bottom edge
FACING = {ref: (lambda f, p: all(pcbnew.ToMM(pad.GetPosition().y) < CY - p[3] + 1.0          # pads inboard of the body
                                 for pad in f.Pads() if pad.GetNumber().isdigit())
                and next(pad for pad in f.Pads() if pad.GetNumber() == "1").GetPosition().x > pt(p[2], 0).x)  # pin 1 on the right
          for ref in ("J50", "J51")}


def read_netlist():
    """Parts that have a footprint in the schematic (the captured sheets), and the net of each of their pads."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "n.net"
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(out),
                        str(OUT.with_suffix(".kicad_sch"))], check=True, capture_output=True)
        tree = parse(out.read_text())
    comps = {}
    for c in children(children(tree, "components")[0], "comp"):
        get = lambda k: unq(children(c, k)[0][1]) if children(c, k) and len(children(c, k)[0]) > 1 else ""   # noqa: E731
        if get("footprint"):
            sheet = unq(children(children(c, "sheetpath")[0], "tstamps")[0][1])
            comps[get("ref")] = {"value": get("value"), "footprint": get("footprint"), "path": sheet + get("tstamps")}
    pad_net = {}
    for n in children(children(tree, "nets")[0], "net"):
        for x in children(n, "node"):
            ref = unq(children(x, "ref")[0][1])
            if ref in comps:
                pad_net[(ref, unq(children(x, "pin")[0][1]))] = unq(children(n, "name")[0][1])
    return comps, pad_net


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
    comps, pad_net = read_netlist()                       # parts on sheets captured for real, with footprints
    netinfo = {}
    for name in sorted(set(pad_net.values())):
        netinfo[name] = pcbnew.NETINFO_ITEM(board, name)
        board.Add(netinfo[name])
    placed, parked = 0, 0
    spot = {p[0]: p for p in main_board["place"]}
    for ref in sorted(comps):
        lib, name = comps[ref]["footprint"].split(":")
        f = pcbnew.FootprintLoad(str(FP_DIR / f"{lib}.pretty"), name)
        f.SetFPID(pcbnew.LIB_ID(lib, name))
        f.SetReference(ref)
        f.SetValue(comps[ref]["value"])
        f.SetPath(pcbnew.KIID_PATH(comps[ref]["path"]))
        board.Add(f)
        if ref in spot:                                    # floorplan position: centre the courtyard on it
            _, side, x, y, *_ = spot[ref]
            f.SetPosition(pt(x, y))
            if side == "B":
                f.Flip(pt(x, y), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
            f.SetOrientationDegrees(TURN.get(ref, 0))
            box = f.GetCourtyard(pcbnew.B_CrtYd if side == "B" else pcbnew.F_CrtYd).BBox()
            centre = box.Centre()
            f.Move(pcbnew.VECTOR2I(pt(x, y).x - centre.x, pt(x, y).y - centre.y))
            placed += 1
        else:                                              # no floorplan position yet: parked beside the board
            f.SetPosition(pt(-main_board["size"][0] / 2 - 8 - 5 * (parked // 12), 40 - 6 * (parked % 12)))
            parked += 1
        for pad in f.Pads():
            if (ref, pad.GetNumber()) in pad_net:
                pad.SetNet(netinfo[pad_net[(ref, pad.GetNumber())]])
    for ref, check in FACING.items():                      # flipped connectors are easy to get facing the wrong way
        f = board.FindFootprintByReference(ref)
        if f and not check(f, spot[ref]):
            raise SystemExit(f"{ref} faces the wrong way")
    for ref, side, x, y, w, h, _height, *flags in main_board["place"]:
        if ref in comps:
            continue
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
    add_text(board, "NetScope X1 main board, rev A draft. NOT LAID OUT: outline, guides, and footprints of the captured sheets.",
             0, top + 4, pcbnew.Dwgs_User, 1.5)
    add_text(board, "Parts beside the board have no position yet. Nothing is routed.", 0, top - 4, pcbnew.Dwgs_User, 1.2)
    add_text(board, "Rectangles: Dwgs.User = front-side parts, Cmts.User = back-side parts (seen through the board).",
             0, top, pcbnew.Dwgs_User, 1.2)
    # SaveBoard also writes a default project file beside the board, which would wipe the
    # generated net classes: save in a scratch directory and take only the board file.
    with tempfile.TemporaryDirectory() as scratch:
        tmp = Path(scratch) / OUT.name
        pcbnew.SaveBoard(str(tmp), board)
        shutil.copyfile(tmp, OUT)
    print(f"wrote {OUT.relative_to(ROOT)}: outline {len(pts)} edges, {holes} mounting holes, {guides} placement guides, "
          f"{placed} real footprints placed, {parked} parked beside the board, {len(netinfo)} nets")


if __name__ == "__main__":
    main()
