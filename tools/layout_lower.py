#!/usr/bin/env python3
"""Place and route the lower (keypad and USB-C) board from its schematic.

    /usr/bin/python3 tools/layout_lower.py [--force]

Needs KiCad 9's `pcbnew` module and numpy.

Steps:
  1. read the netlist KiCad exports from the schematic; load every footprint
     from KiCad's library; place parts at the floorplan positions;
  2. route by script the two things an autorouter does badly: the 3 A VBUS
     path (1.5 mm) and the long run of the USB pair (kept side by side);
  3. route everything else with the project's own grid router (tools/gridrouter.py);
  4. pour ground on both layers and fill.
The result is only accepted by tools/check_lower.py (DRC with schematic parity).

88 x 56 mm, two layers.  Untested: not fabricated.  USB pair impedance is not
controlled on this two-layer stack; see the README.
"""
from __future__ import annotations

import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from gridrouter import GridRouter  # noqa: E402
from kicad_lib import children, parse, unq  # noqa: E402

PRJ = ROOT / "hardware/kicad/netscope-x1-lower"
NAME = "netscope-x1-lower"
FOOTPRINTS = Path("/usr/share/kicad/footprints")
CX, CY = 150.0, 100.0                      # board centre on the page
W, H = 88.0, 56.0

# ---- placement: ref -> (x, y, rotation, side), floorplan coordinates (centre origin, Y up) ----
KEY_CENTRE = {"SW1": (-22.0, 10.5), "SW2": (-22.0, -16.5), "SW3": (-35.5, -3.0), "SW4": (-8.5, -3.0),
              "SW5": (-22.0, -3.0), "SW6": (24.0, 11.0), "SW7": (24.0, -4.0), "SW8": (24.0, -19.0),
              "SW9": (38.0, 18.0)}
PLACE = {"J20": (0.0, -24.325, 180, "B"), "D30": (0.0, -17.5, 270, "B"),
         "R1": (3.0, -16.4, 90, "B"), "R2": (-3.0, -16.4, 90, "B"), "C1": (8.0, -22.0, 0, "F"),
         "J50": (-28.0, 23.0, 180, "F"), "J51": (24.5, 23.0, 180, "F"),
         "BZ1": (37.5, -4.0, 0, "F"), "R31": (35.5, 2.2, 0, "F"), "R32": (39.5, 2.2, 0, "F"),
         "H5": (-41.0, 15.0, 0, "F"), "H6": (-41.0, -24.0, 0, "F"), "H7": (41.0, 8.0, 0, "F"), "H8": (41.0, -24.0, 0, "F")}
for i, x in enumerate((-12.0, -4.0, 4.0, 12.0), 1):
    PLACE[f"LED{i}"] = (x, 25.0, 0, "F")
    PLACE[f"R2{i}"] = (x, 22.6, 0, "F")
for ref, (kx, ky) in KEY_CENTRE.items():
    n = ref[2:]
    PLACE[ref] = (kx - 3.25, ky + 2.25, 0, "F")            # footprint origin is pad 1, not the centre
    if ref == "SW9":                                        # power key: parts below, the cable connector is beside it
        PLACE[f"R1{n}"], PLACE[f"C1{n}"] = (36.5, 13.2, 0, "F"), (40.0, 13.2, 0, "F")
    else:
        PLACE[f"R1{n}"], PLACE[f"C1{n}"] = (kx + 5.7, ky + 1.3, 90, "F"), (kx + 5.7, ky - 1.9, 90, "F")

CLASSES = {"Power": (0.5, ["/VBUS"]), "USB": (0.2, ["/USB_DP", "/USB_DN"])}     # name -> (track width, nets)
TRACK, VIA, DRILL, CLEARANCE = 0.25, 0.6, 0.3, 0.2


def mm(v: float) -> int:
    return pcbnew.FromMM(v)


def P(x: float, y: float) -> "pcbnew.VECTOR2I":
    return pcbnew.VECTOR2I(mm(CX + x), mm(CY - y))


def xy(v) -> tuple[float, float]:
    return round(pcbnew.ToMM(v.x) - CX, 4), round(CY - pcbnew.ToMM(v.y), 4)


def read_netlist():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "n.net"
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(out),
                        str(PRJ / f"{NAME}.kicad_sch")], check=True, capture_output=True)
        tree = parse(out.read_text())
    comps = {}
    for c in children(children(tree, "components")[0], "comp"):
        get = lambda k: unq(children(c, k)[0][1]) if children(c, k) else ""   # noqa: E731
        comps[get("ref")] = {"value": get("value"), "footprint": get("footprint"), "uuid": get("tstamps")}
    nets = {}
    for n in children(children(tree, "nets")[0], "net"):
        nets[unq(children(n, "name")[0][1])] = [(unq(children(x, "ref")[0][1]), unq(children(x, "pin")[0][1]))
                                                for x in children(n, "node")]
    return comps, nets


class Copper:
    def __init__(self, board, netinfo):
        self.board, self.netinfo = board, netinfo
        self.stubs = []                                # escape stubs, trimmed after routing

    def track(self, net, layer, width, *pts, lock=True):
        for a, b in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(self.board)
            t.SetStart(P(*a))
            t.SetEnd(P(*b))
            t.SetWidth(mm(width))
            t.SetLayer(layer)
            t.SetNet(self.netinfo[net])
            t.SetLocked(lock)
            self.board.Add(t)
            if not lock:
                self.stubs.append(t)

    def via(self, net, at, dia=VIA, drill=DRILL, lock=True):
        v = pcbnew.PCB_VIA(self.board)
        v.SetPosition(P(*at))
        v.SetWidth(pcbnew.F_Cu, mm(dia))
        v.SetDrill(mm(drill))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNet(self.netinfo[net])
        v.SetLocked(lock)
        self.board.Add(v)


def build_board():
    comps, nets = read_netlist()
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)
    ds = board.GetDesignSettings()
    ns = ds.m_NetSettings
    default = ns.GetDefaultNetclass()
    default.SetClearance(mm(CLEARANCE))
    default.SetTrackWidth(mm(TRACK))
    default.SetViaDiameter(mm(VIA))
    default.SetViaDrill(mm(DRILL))
    for name, (width, members) in CLASSES.items():
        nc = pcbnew.NETCLASS(name)
        nc.SetClearance(mm(CLEARANCE))
        nc.SetTrackWidth(mm(width))
        nc.SetViaDiameter(mm(VIA))
        nc.SetViaDrill(mm(DRILL))
        ns.SetNetclass(name, nc)
        for net in members:
            ns.SetNetclassPatternAssignment(net, name)

    netinfo, pad_net = {}, {}
    for name, nodes in nets.items():
        netinfo[name] = pcbnew.NETINFO_ITEM(board, name)
        board.Add(netinfo[name])
        for ref, pin in nodes:
            pad_net[(ref, pin)] = name

    fps = {}
    for ref, c in comps.items():
        lib, name = c["footprint"].split(":")
        f = pcbnew.FootprintLoad(str(FOOTPRINTS / f"{lib}.pretty"), name)
        f.SetFPID(pcbnew.LIB_ID(lib, name))
        f.SetReference(ref)
        f.SetValue(c["value"])
        f.SetPath(pcbnew.KIID_PATH("/" + c["uuid"]))
        x, y, rot, side = PLACE[ref]
        board.Add(f)                                   # must be on a board before it can be flipped
        f.SetPosition(P(x, y))
        if side == "B":
            f.Flip(P(x, y), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        f.SetOrientationDegrees(rot)
        for pad in f.Pads():
            key = (ref, pad.GetNumber())
            if key in pad_net:
                pad.SetNet(netinfo[pad_net[key]])
        fps[ref] = f
    missing = set(PLACE) - set(fps)
    if missing:
        raise SystemExit(f"placed but not in the schematic: {sorted(missing)}")

    def pads(ref, num):
        return sorted(xy(p.GetPosition()) for p in fps[ref].Pads() if p.GetNumber() == num)

    # a flipped footprint is easy to get facing the wrong way: check the connector's pads face inwards
    assert all(y > -22.0 for _, y in pads("J20", "A6") + pads("J20", "A1")), "J20 faces the wrong way"
    # passives and small parts: reference designator on the fabrication layer, not the silkscreen
    for ref, f in fps.items():
        if ref[0] in "RCLDH":
            f.Reference().SetLayer(pcbnew.B_Fab if f.GetLayer() == pcbnew.B_Cu else pcbnew.F_Fab)

    cu = Copper(board, netinfo)
    F, B = pcbnew.F_Cu, pcbnew.B_Cu

    # ---- VBUS, 3 A: connector pads (back) -> vias -> 1.5 mm trunk on the front -> J51 pins 1-10 ----
    vb = sorted(set(pads("J20", "A4") + pads("J20", "A9")))            # the two combined VBUS pads
    assert len(vb) == 2, vb
    trunk_x, trunk_y = 14.0, 18.5
    for (px, py), sign in zip(vb, (-1, 1)):
        via_at = (sign * 3.0, -19.0)
        cu.track("/VBUS", B, 0.5, (px, py), (px, -19.6), via_at)
        cu.via("/VBUS", via_at, 0.8, 0.4)
    cu.track("/VBUS", F, 0.8, (-3.0, -19.0), (-3.0, -13.5), (trunk_x, -13.5))
    cu.track("/VBUS", F, 0.8, (3.0, -19.0), (trunk_x, -19.0))
    j51 = [pads("J51", str(n))[0] for n in range(1, 11)]
    x_far = max(p[0] for p in j51)
    cu.track("/VBUS", F, 1.5, (trunk_x, -19.0), (trunk_x, trunk_y), (x_far, trunk_y))
    for px, py in j51:
        cu.track("/VBUS", F, 0.25, (px, trunk_y), (px, py))

    # ---- USB pair: through the ESD part, then side by side up the middle and west towards J50 ----
    lanes = {}
    for net in ("/USB_DP", "/USB_DN"):
        nums = [n for (r, n), v in pad_net.items() if r == "D30" and v == net]
        (x1, y1), (x2, y2) = sorted((pads("D30", n)[0] for n in nums), key=lambda p: p[1])
        assert abs(x1 - x2) < 0.01, "D30 must be turned so each line's two pads are in a column"
        lanes[net] = (x1, y1, y2)
    left, right = sorted(lanes, key=lambda n: lanes[n][0])              # left lane is the inner one on the west turn
    a, d, t = 16.5, 0.5, 0.5 * math.tan(math.radians(22.5))
    gx, gy = pads("D30", "2")[0]                                        # ground pad, between the two lanes
    assert all(gy > lanes[n][1] for n in lanes), "D30 must be turned so its ground pad faces away from the connector"
    pocket = gy + 1.3                                                   # ground via sits here, lanes spread round it
    for net, sign, corner in ((left, -1, [(-0.25, a), (-0.25 - d, a + d)]),
                              (right, 1, [(0.25, a + t), (0.25 - d - 0.5 + t, a + d + 0.5)])):
        x, y_low, y_high = lanes[net]
        cu.track(net, B, 0.2, (x, y_low), (x, y_high), (sign * 0.8, y_high + 0.8 - abs(x)), (sign * 0.8, pocket + 0.9),
                 (sign * 0.25, pocket + 1.45), *corner, (-25.5, corner[1][1]))
    cu.track("/GND", B, 0.25, (gx, gy), (0.0, pocket))
    cu.via("/GND", (0.0, pocket))

    # ---- ground for the cable connectors: from the top end of each ground pad to a bus under the
    #      connector body, tied to both mounting pads and stitched to the back with vias ----
    bus_y = 22.6
    for ref, count in (("J50", 30), ("J51", 20)):
        mp = pads(ref, "MP")
        for n in range(1, count + 1):
            if pad_net.get((ref, str(n))) == "/GND":
                px, py = pads(ref, str(n))[0]
                cu.track("/GND", F, 0.2, (px, py), (px, bus_y))
        cu.track("/GND", F, 0.3, mp[0], (mp[0][0], bus_y), (mp[-1][0], bus_y), mp[-1])
        for vx in (mp[0][0] + 3.0, (mp[0][0] + mp[-1][0]) / 2, mp[-1][0] - 3.0):
            vx = round(vx * 4) / 4
            cu.track("/GND", F, 0.3, (vx, bus_y), (vx, 25.5))
            cu.via("/GND", (vx, 25.5))

    # ---- escape stubs: 0.5 mm pitch pads are left straight along the pad before any routing ----
    #      J50 pins 2-11 all head east: each stub is 0.5 mm longer than the one before, so the nets
    #      leave as a nested fan and none is boxed in by its neighbours.
    rank = 0
    for n in range(1, 31):
        net = pad_net.get(("J50", str(n)))
        if net and net != "/GND":
            px, py = pads("J50", str(n))[0]
            end = 20.0 - 0.5 * rank if n <= 11 else {"/CC1": 15.0, "/CC2": 14.5}.get(net, 20.0)   # CC: clear of the USB vias
            cu.track(net, F, 0.25, (px, py), (px, end), lock=False)
            rank += 1
    for num in ("A5", "B5", "A6", "B6", "A7", "B7"):
        px, py = pads("J20", num)[0]
        cu.track(pad_net[("J20", num)], B, 0.2, (px, py), (px, -19.75), lock=False)

    # ---- outline ----
    corners = [(-W / 2, -H / 2), (W / 2, -H / 2), (W / 2, H / 2), (-W / 2, H / 2)]
    for p, q in zip(corners, corners[1:] + corners[:1]):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(P(*p))
        s.SetEnd(P(*q))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)
    return board, fps, netinfo, nets, cu.stubs


def autoroute(board, nets, stubs):
    """Route every net that the script has not finished.  Returns the list of failures."""
    r = GridRouter(board, (CX, CY), (W, H), track=TRACK, clearance=CLEARANCE, via=VIA, drill=DRILL)
    width = {net: w for w, members in CLASSES.values() for net in members}

    def span(net):                                             # short nets first, ground last
        pts = [s["centre"] for s in r.shapes if s["kind"] == "pad" and s["net"] == net]
        return max(p[0] for p in pts) - min(p[0] for p in pts) + max(p[1] for p in pts) - min(p[1] for p in pts)

    j50 = {}
    for s in r.shapes:
        if s["kind"] == "pad" and s.get("ref") == "J50" and s["num"].isdigit() and s["net"]:
            j50.setdefault(s["net"], int(s["num"]))
    first = ["/USB_DP", "/USB_DN", "/CC1", "/CC2"]
    last = ["/+3V3_AON", "/VBUS", "/GND"]
    cable = sorted((n for n in j50 if n not in first + last), key=j50.get)
    local = sorted((n for n in nets if not n.startswith("unconnected-") and n not in j50 and n not in first + last), key=span)
    # the tight USB-C corner first, then the cable in pin order (so the fan-out nests), supplies and ground last
    order = first + cable + local + last
    r.drop_vias("/GND", lambda ref: ref[0] in "CRLB" and ref not in ("R1", "R2"))     # front passives: own ground via
    for net in order:
        r.tie_pads(net, width.get(net, TRACK))
        r.route(net, width.get(net, TRACK))
    r.stitch("/GND", 4.0)                                      # after ground is routed: ties the two pours together
    r.trim_stubs(stubs)
    return r.failed


def pour_ground(board, netinfo):
    inset = 0.4
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(netinfo["/GND"])
        z.SetZoneName("GND")
        z.SetLocalClearance(mm(0.25))
        z.SetMinThickness(mm(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)
        z.SetThermalReliefGap(mm(0.3))
        z.SetThermalReliefSpokeWidth(mm(0.5))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        o = z.Outline()
        o.NewOutline()
        for x, y in ((-W / 2 + inset, -H / 2 + inset), (W / 2 - inset, -H / 2 + inset),
                     (W / 2 - inset, H / 2 - inset), (-W / 2 + inset, H / 2 - inset)):
            o.Append(P(x, y))
        board.Add(z)


def silkscreen(board, fps):
    def text(s, x, y, layer, size=1.0, mirror=False):
        t = pcbnew.PCB_TEXT(board)
        t.SetText(s)
        t.SetPosition(P(x, y))
        t.SetLayer(layer)
        t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
        t.SetTextThickness(mm(size * 0.15))
        t.SetMirrored(mirror)
        board.Add(t)
    text("NetScope X1 lower board  rev A", 4.0, 12.0, pcbnew.F_SilkS, 1.2)
    text("J50", -41.0, 23.0, pcbnew.F_SilkS, 1.0)
    text("J51", 37.0, 26.0, pcbnew.F_SilkS, 1.0)
    fps["J50"].Reference().SetLayer(pcbnew.F_Fab)
    fps["J51"].Reference().SetLayer(pcbnew.F_Fab)
    fps["J20"].Reference().SetLayer(pcbnew.B_Fab)
    fps["BZ1"].Reference().SetPosition(P(37.5, -4.0))
    fps["SW6"].Reference().SetPosition(P(24.0, 5.6))
    text("NetScope X1 lower board rev A", 0.0, 4.0, pcbnew.B_SilkS, 1.5, True)
    text("USB-C: 3 A max", 12.0, -24.0, pcbnew.B_SilkS, 1.0, True)


def main() -> None:
    out = PRJ / f"{NAME}.kicad_pcb"
    if out.exists() and "--force" not in sys.argv:
        raise SystemExit(f"{out.name} exists. Use --force to regenerate it (hand edits are lost).")
    board, fps, netinfo, nets, stubs = build_board()
    work = Path(tempfile.mkdtemp(prefix="lower-"))
    before = len(board.GetTracks())
    failed = [] if "--no-autoroute" in sys.argv else autoroute(board, nets, stubs)
    silkscreen(board, fps)
    pour_ground(board, netinfo)
    tmp = work / out.name
    pcbnew.SaveBoard(str(tmp), board)
    board = pcbnew.LoadBoard(str(tmp))                 # zones can only be filled on a board loaded from a file
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(tmp), board)
    shutil.copyfile(tmp, out)
    shutil.copyfile(tmp.with_suffix(".kicad_pro"), out.with_suffix(".kicad_pro"))    # net classes live in the project file
    shutil.rmtree(work, ignore_errors=True)
    print(f"wrote {out.relative_to(ROOT)}: {len(fps)} footprints, {before} scripted and "
          f"{len(board.GetTracks()) - before} routed track segments and vias")
    for f in failed:
        print("  NOT ROUTED " + f)


if __name__ == "__main__":
    main()
