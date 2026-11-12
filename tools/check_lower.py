#!/usr/bin/env python3
"""Check the lower (keypad and USB-C) board KiCad project.  Needs kicad-cli 9 and KiCad's libraries.

    python3 tools/check_lower.py [--fab DIR]

1. ERC on the schematic: any violation fails.
2. Cable pinout: every J50 / J51 pin carries the net tools/gen_lower.py assigns.
3. Cross-board nets: the cable nets map onto exactly the block-netlist nets that the
   floorplan says cross between the two boards, no more and no fewer.
4. Circuit rules: every key net has a switch, a pull-up to the always-on rail and a
   capacitor to ground; every LED has a series resistor; both CC pins have 5.1 k to ground;
   both pads of each USB data line are joined.
5. DRC on the board with schematic parity: any violation, unconnected item or parity
   issue fails.

With --fab, and only if everything passed, writes Gerbers, drill, placement, BOM,
schematic PDF and board images into DIR.

A pass means the files are self-consistent.  Nothing has been fabricated or measured.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from gen_lower import BLOCK_NET, J50, J51, KEYS, LEDS, NAME  # noqa: E402
from kicad_lib import children, parse, unq  # noqa: E402

PRJ = ROOT / "hardware/kicad/netscope-x1-lower"
SCH, PCB = PRJ / f"{NAME}.kicad_sch", PRJ / f"{NAME}.kicad_pcb"


def cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["kicad-cli", *args], capture_output=True, text=True)


def main() -> int:
    if not shutil.which("kicad-cli"):
        print("kicad-cli not found: install KiCad 9 to run this check")
        return 2
    problems: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="lower-check-"))

    # 1. ERC
    cli("sch", "erc", "--format", "json", "--severity-all", "-o", str(tmp / "erc.json"), str(SCH))
    found = [v for s in json.loads((tmp / "erc.json").read_text())["sheets"] for v in s["violations"]]
    for v in found:
        problems.append(f"ERC {v['severity']}: {v['description']} [{'; '.join(i['description'] for i in v['items'])}]")
    print(f"ERC: {len(found)} violations")

    cli("sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(tmp / "n.net"), str(SCH))
    tree = parse((tmp / "n.net").read_text())
    value = {unq(children(c, "ref")[0][1]): unq(children(c, "value")[0][1])
             for c in children(children(tree, "components")[0], "comp")}
    net_of, members = {}, {}
    for n in children(children(tree, "nets")[0], "net"):
        name = unq(children(n, "name")[0][1]).lstrip("/")
        for x in children(n, "node"):
            node = (unq(children(x, "ref")[0][1]), unq(children(x, "pin")[0][1]))
            net_of[node] = name
            members.setdefault(name, set()).add(node)

    # 2. cable pinout
    for ref, table in (("J50", J50), ("J51", J51)):
        for i, want in enumerate(table, 1):
            got = net_of.get((ref, str(i)), "")
            if want is None:
                if not got.startswith("unconnected-"):
                    problems.append(f"{ref} pin {i} should be unconnected, carries {got}")
            elif got != want:
                problems.append(f"{ref} pin {i}: {got or 'nothing'} in the schematic, {want} in the pin table")
    print(f"cable pinout: J50 {len(J50)} pins, J51 {len(J51)} pins checked against the tables in gen_lower.py")

    # 3. cross-board nets against the block netlist and the floorplan
    block = yaml.safe_load((ROOT / "hardware/netlist/netscope-x1.yaml").read_text())
    plan = yaml.safe_load((ROOT / "hardware/pcb/floorplan.yaml").read_text())["boards"]
    on = {p[0]: b for b in plan for p in plan[b]["place"]}
    crossing = {n["name"] for n in block["nets"]
                if len({on.get(node.split(".")[0]) for node in n["nodes"]} - {None}) > 1}
    cable = {net for net in J50 + J51 if net}
    mapped = {BLOCK_NET[net] for net in cable}
    if mapped != crossing:
        problems.append(f"cross-board nets differ: cables carry {sorted(mapped)}, block netlist and floorplan say {sorted(crossing)}")
    print(f"cross-board nets: {len(cable)} cable nets map onto {len(mapped)} block nets; floorplan says {len(crossing)} cross")

    # 4. circuit rules
    for ref, net, _legend in KEYS:
        refs = {r for r, _ in members.get(net, ())}
        r = [x for x in refs if x.startswith("R")]
        c = [x for x in refs if x.startswith("C")]
        if ref not in refs or len(r) != 1 or len(c) != 1:
            problems.append(f"{net}: expected the switch, one resistor and one capacitor, found {sorted(refs)}")
            continue
        if {net_of[(r[0], "1")], net_of[(r[0], "2")]} != {net, "+3V3_AON"} or value[r[0]] != "10k":
            problems.append(f"{net}: pull-up {r[0]} is not 10k to +3V3_AON")
        if {net_of[(c[0], "1")], net_of[(c[0], "2")]} != {net, "GND"}:
            problems.append(f"{net}: {c[0]} is not from the key line to ground")
        if {net_of[(ref, "1")], net_of[(ref, "2")]} != {net, "GND"}:
            problems.append(f"{net}: {ref} does not switch the line to ground")
    for led in LEDS:
        r = [x for x, _ in members.get(led, ()) if x.startswith("R")]
        if len(r) != 1 or {net_of[(r[0], "1")], net_of[(r[0], "2")]} != {led, f"{led}_A"} \
                or net_of.get((led, "2")) != f"{led}_A" or net_of.get((led, "1")) != "GND":
            problems.append(f"{led}: expected cable -> resistor -> LED anode, cathode to ground")
    for cc in ("CC1", "CC2"):
        r = [x for x, _ in members.get(cc, ()) if x.startswith("R")]
        if len(r) != 1 or value[r[0]] != "5k1" or "GND" not in (net_of[(r[0], "1")], net_of[(r[0], "2")]):
            problems.append(f"{cc}: expected one 5k1 resistor to ground")
    for net, pins in (("USB_DP", ("A6", "B6")), ("USB_DN", ("A7", "B7")), ("VBUS", ("A4", "A9", "B4", "B9"))):
        if any(net_of.get(("J20", p)) != net for p in pins):
            problems.append(f"J20: pins {pins} are not all on {net}")
    print(f"circuit rules: {len(KEYS)} keys, {len(LEDS)} LEDs, CC pull-downs and USB-C pin pairs checked")

    # 5. DRC with parity
    cli("pcb", "drc", "--schematic-parity", "--severity-all", "--format", "json", "-o", str(tmp / "drc.json"), str(PCB))
    drc = json.loads((tmp / "drc.json").read_text())
    counts = {k: len(drc.get(k, [])) for k in ("violations", "unconnected_items", "schematic_parity")}
    for k in counts:
        for v in drc.get(k, []):
            problems.append(f"DRC {k}: {v['description']} [{'; '.join(i['description'] for i in v['items'])}]")
    board = parse(PCB.read_text())
    print(f"DRC: {counts['violations']} violations, {counts['unconnected_items']} unconnected, "
          f"{counts['schematic_parity']} schematic parity issues; {len(children(board, 'footprint'))} footprints, "
          f"{len(children(board, 'segment'))} track segments, {len(children(board, 'via'))} vias")

    for p in problems:
        print("  FAIL " + p)
    ok = not problems
    print("lower board check (" + cli("version").stdout.strip() + "): " + ("passed" if ok else f"{len(problems)} problem(s)"))

    if ok and "--fab" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--fab") + 1]).resolve()
        (out / "gerbers").mkdir(parents=True, exist_ok=True)
        layers = "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"
        stem = str(out / "lower")
        steps = [
            ("pcb", "export", "gerbers", "--layers", layers, "-o", str(out / "gerbers") + "/", str(PCB)),
            ("pcb", "export", "drill", "--format", "excellon", "--excellon-units", "mm", "-o", str(out / "gerbers") + "/", str(PCB)),
            ("pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both", "-o", stem + "-placement.csv", str(PCB)),
            ("sch", "export", "bom", "--fields", "Reference,Value,Footprint,MPN,Manufacturer,${QUANTITY}",
             "--labels", "Refs,Value,Footprint,MPN,Manufacturer,Qty", "--group-by", "Value,Footprint",
             "-o", stem + "-bom.csv", str(SCH)),
            ("sch", "export", "pdf", "-o", stem + "-schematic.pdf", str(SCH)),
            ("pcb", "export", "svg", "--layers", "F.Cu,F.SilkS,Edge.Cuts", "--mode-single", "--page-size-mode", "2",
             "--exclude-drawing-sheet", "-o", stem + "-front.svg", str(PCB)),
            ("pcb", "export", "svg", "--layers", "B.Cu,B.SilkS,Edge.Cuts", "--mirror", "--mode-single",
             "--page-size-mode", "2", "--exclude-drawing-sheet", "-o", stem + "-back.svg", str(PCB)),
        ]
        for step in steps:
            r = cli(*step)
            if r.returncode:
                print(f"export failed: kicad-cli {' '.join(step[:3])}: {r.stderr.strip()}")
                ok = False
        print(f"fabrication files: {out}")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
