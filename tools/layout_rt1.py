#!/usr/bin/env python3
"""Place and route the RT-1 board from its schematic, with KiCad's Python API.

    /usr/bin/python3 tools/layout_rt1.py [--force]     # needs KiCad 9's `pcbnew`

Reads the netlist KiCad exports from rt-1.kicad_sch, loads each part's
footprint from KiCad's library, and writes rt-1.kicad_pcb: two layers,
17.8 x 39.9 mm, jack at the bottom edge, one diode + resistor row per pair.

Routing plan (all dimensions in mm, origin at jack pin 1, "height" = distance
behind the pin row):
  * front copper: the four anode nets leave the jack, turn left under the
    jack body and run up a channel on the left edge to their rows.  Nets from
    pins further right turn higher and take an inner channel and a nearer
    row, so nothing crosses.
  * back copper: each cathode net runs straight up from its jack pin to a via
    in the gap below its row; a front track takes it along the gap and round
    the right-hand end of the resistor.

Every position is taken from the placed footprints' pads, so the tracks end
on pad centres.  The result is only accepted by tools/check_rt1.py (DRC with
schematic parity).  Untested: not fabricated.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from kicad_lib import children, parse, unq  # noqa: E402

PRJ = ROOT / "hardware/remote-terminator/kicad/rt-1"
FOOTPRINTS = Path("/usr/share/kicad/footprints")
OX, OY = 100.0, 100.0                 # jack pin 1 on the page
TRACK, VIA, VIA_DRILL = 0.25, 0.6, 0.3
X_LEFT, X_RIGHT = -4.6, 13.2          # board edges
Y_FRONT = -14.6                       # jack face (height below the pins)
ROW0, PITCH = 8.5, 4.6                # first row height and row pitch
X_DIODE, X_RES, X_RETURN = 1.0, 7.6, 12.0
# pair (anode pin, cathode pin) -> row, nearest the jack first.  The order is what makes
# the front-copper channel planar: anode pins 7, 4, 3, 1 from right to left.
ROW_OF_ANODE = {7: 0, 4: 1, 3: 2, 1: 3}
TURN = {1: 3.8, 3: 4.3, 4: 4.8, 7: 5.3}            # height where each anode net turns left
CHANNEL = {1: -3.6, 3: -3.1, 4: -2.6, 7: -2.1}     # x of its run up the left edge


def mm(v: float) -> int:
    return pcbnew.FromMM(v)


def P(x: float, h: float) -> "pcbnew.VECTOR2I":
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY - h))


def xh(v) -> tuple[float, float]:
    return round(pcbnew.ToMM(v.x) - OX, 4), round(OY - pcbnew.ToMM(v.y), 4)


def read_netlist():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "rt-1.net"
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(out),
                        str(PRJ / "rt-1.kicad_sch")], check=True, capture_output=True)
        tree = parse(out.read_text())
    comps = {}
    for c in children(children(tree, "components")[0], "comp"):
        get = lambda k: unq(children(c, k)[0][1]) if children(c, k) else ""   # noqa: E731
        comps[get("ref")] = {"value": get("value"), "footprint": get("footprint"), "uuid": get("tstamps")}
    nets = {}
    for n in children(children(tree, "nets")[0], "net"):
        name = unq(children(n, "name")[0][1])
        nets[name] = [(unq(children(x, "ref")[0][1]), unq(children(x, "pin")[0][1])) for x in children(n, "node")]
    return comps, nets


class Router:
    def __init__(self, board):
        self.board = board

    def track(self, net, layer, *pts):
        for a, b in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(self.board)
            t.SetStart(P(*a))
            t.SetEnd(P(*b))
            t.SetWidth(mm(TRACK))
            t.SetLayer(layer)
            t.SetNet(net)
            self.board.Add(t)

    def via(self, net, at):
        v = pcbnew.PCB_VIA(self.board)
        v.SetPosition(P(*at))
        v.SetWidth(pcbnew.F_Cu, mm(VIA))
        v.SetDrill(mm(VIA_DRILL))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNet(net)
        self.board.Add(v)


def text(board, s, x, h, layer, size=1.0, mirror=False, angle=0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(P(x, h))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(size * 0.15))
    t.SetMirrored(mirror)
    t.SetTextAngleDegrees(angle)
    board.Add(t)
    return t


def main() -> None:
    out = PRJ / "rt-1.kicad_pcb"
    if out.exists() and "--force" not in sys.argv:
        raise SystemExit("rt-1.kicad_pcb exists. Use --force to regenerate it (hand edits are lost).")
    comps, nets = read_netlist()
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)

    netinfo, pad_net = {}, {}
    for name, nodes in nets.items():
        netinfo[name] = pcbnew.NETINFO_ITEM(board, name)
        board.Add(netinfo[name])
        for ref, pin in nodes:
            pad_net[(ref, pin)] = name

    pairs = {}                                   # element index -> (anode pin, cathode pin)
    for i in range(1, 5):
        a = next(int(p) for r, p in nets[pad_net[(f"D{i}", "2")]] if r == "J1")
        c = next(int(p) for r, p in nets[pad_net[(f"R{i}", "2")]] if r == "J1")
        pairs[i] = (a, c)
    row_h = {i: ROW0 + PITCH * ROW_OF_ANODE[a] for i, (a, _) in pairs.items()}
    top = max(row_h.values()) + 2.9

    place = {"J1": (0.0, 0.0, 0)}
    for i in pairs:
        place[f"D{i}"] = (X_DIODE, row_h[i], 180)      # turned so the anode pad is on the left
        place[f"R{i}"] = (X_RES, row_h[i], 0)
    fps = {}
    for ref, c in comps.items():
        lib, name = c["footprint"].split(":")
        f = pcbnew.FootprintLoad(str(FOOTPRINTS / f"{lib}.pretty"), name)
        f.SetFPID(pcbnew.LIB_ID(lib, name))
        f.SetReference(ref)
        f.SetValue(c["value"])
        f.SetPath(pcbnew.KIID_PATH("/" + c["uuid"]))
        x, h, rot = place[ref]
        f.SetPosition(P(x, h))
        f.SetOrientationDegrees(rot)
        for pad in f.Pads():
            key = (ref, pad.GetNumber())
            if key in pad_net:
                pad.SetNet(netinfo[pad_net[key]])
        board.Add(f)
        fps[ref] = f

    def pad(ref, num):
        return xh(next(p for p in fps[ref].Pads() if p.GetNumber() == num).GetPosition())

    r = Router(board)
    for i, (a, c) in pairs.items():
        h = row_h[i]
        anode, mid, cathode = (netinfo[pad_net[k]] for k in ((f"D{i}", "2"), (f"D{i}", "1"), (f"R{i}", "2")))
        # anode: jack pin -> turn left -> up the left channel -> diode
        jx, jh = pad("J1", str(a))
        dx, dh = pad(f"D{i}", "2")
        r.track(anode, pcbnew.F_Cu, (jx, jh), (jx, TURN[a]), (CHANNEL[a], TURN[a]), (CHANNEL[a], dh), (dx, dh))
        # diode cathode -> resistor
        r.track(mid, pcbnew.F_Cu, pad(f"D{i}", "1"), pad(f"R{i}", "1"))
        # cathode: jack pin -> straight up on the back -> via below the row -> round the resistor's right end
        cx, ch = pad("J1", str(c))
        gap = h - PITCH / 2
        rx, rh = pad(f"R{i}", "2")
        r.track(cathode, pcbnew.B_Cu, (cx, ch), (cx, gap))
        r.via(cathode, (cx, gap))
        r.track(cathode, pcbnew.F_Cu, (cx, gap), (X_RETURN, gap), (X_RETURN, rh), (rx, rh))

    # outline
    corners = [(X_LEFT, Y_FRONT), (X_RIGHT, Y_FRONT), (X_RIGHT, top), (X_LEFT, top)]
    for a, b in zip(corners, corners[1:] + corners[:1]):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(P(*a))
        s.SetEnd(P(*b))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)

    # reference designators sit on the part body (also on the fabrication layer)
    for i in pairs:
        for ref, x in ((f"R{i}", X_RES), (f"D{i}", X_DIODE)):
            t = fps[ref].Reference()
            t.SetPosition(P(x, row_h[i]))
            t.SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
            t.SetTextThickness(mm(0.12))
            t.SetTextAngleDegrees(0)
    fps["J1"].Reference().SetPosition(P(4.4, -4.0))

    # back silkscreen: identity, write-on ID box, element table.  Heights are chosen to miss the four vias.
    cx = (X_LEFT + X_RIGHT) / 2
    back = pcbnew.B_SilkS
    text(board, "NetScope RT-1", cx, top - 1.4, back, 1.2, True)
    text(board, "ID", 10.6, top - 4.7, back, 1.8, True)
    text(board, "rev A", 10.6, top - 7.3, back, 0.9, True)
    box = pcbnew.PCB_SHAPE(board)
    box.SetShape(pcbnew.SHAPE_T_RECT)
    box.SetStart(P(2.6, top - 3.2))
    box.SetEnd(P(8.2, top - 8.2))
    box.SetLayer(back)
    box.SetWidth(mm(0.15))
    board.Add(box)
    for i, line in zip(sorted(pairs), (13.9, 12.5, 9.1, 7.7)):
        a, c = pairs[i]
        text(board, f"{a}>{c}  D{i} R{i} {comps[f'R{i}']['value'].split(' ')[0]}", cx, line, back, 0.9, True)
    text(board, "anode > cathode", cx, 4.9, back, 0.8, True)

    with tempfile.TemporaryDirectory() as scratch:          # SaveBoard also writes a project file
        tmp = Path(scratch) / out.name
        pcbnew.SaveBoard(str(tmp), board)
        shutil.copyfile(tmp, out)
    w, l = X_RIGHT - X_LEFT, top - Y_FRONT
    print(f"wrote {out.relative_to(ROOT)}: {w:.1f} x {l:.1f} mm, {len(fps)} footprints, "
          f"{len(board.GetTracks())} track segments and vias")


if __name__ == "__main__":
    main()
