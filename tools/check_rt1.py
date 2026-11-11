#!/usr/bin/env python3
"""Check the RT-1 remote terminator KiCad project (needs kicad-cli 9 and KiCad's libraries).

    python tools/check_rt1.py [--fab DIR]

1. ERC on the schematic: any violation fails.
2. The schematic's netlist against firmware/netscope/cable/terminator.py:
   for every pair, jack anode pin -> diode anode, diode cathode -> resistor,
   resistor -> jack cathode pin, nothing else on any net, values as defined.
3. DRC on the board with schematic parity: any violation, unconnected item
   or parity issue fails.
4. Board facts: two copper layers, outline size, every part has a footprint.

With --fab, and only if everything passed, writes Gerbers, drill file,
placement file, BOM, schematic PDF and board images into DIR.

A pass means the files are self-consistent and say what the firmware expects.
It does not mean the board works: nothing has been fabricated or measured.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "firmware"))
sys.path.insert(0, str(ROOT / "tools"))

from gen_rt1 import DIODE_FP, JACK_FP, RES_FP, elements  # noqa: E402
from kicad_lib import children, parse, unq  # noqa: E402

PRJ = ROOT / "hardware/remote-terminator/kicad/rt-1"
SCH, PCB = PRJ / "rt-1.kicad_sch", PRJ / "rt-1.kicad_pcb"


def cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["kicad-cli", *args], capture_output=True, text=True)


def main() -> int:
    if not shutil.which("kicad-cli"):
        print("kicad-cli not found: install KiCad 9 to run this check")
        return 2
    problems: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="rt1-"))

    # 1. ERC
    cli("sch", "erc", "--format", "json", "--severity-all", "-o", str(tmp / "erc.json"), str(SCH))
    erc = json.loads((tmp / "erc.json").read_text())
    found = [v for s in erc["sheets"] for v in s["violations"]]
    for v in found:
        problems.append(f"ERC {v['severity']}: {v['description']} [{'; '.join(i['description'] for i in v['items'])}]")
    if any(v["type"] == "lib_symbol_issues" for v in found):
        print("hint: KiCad's global symbol library table is missing; copy /usr/share/kicad/template/sym-lib-table "
              "to ~/.config/kicad/9.0/")
    print(f"ERC: {len(found)} violations")

    # 2. netlist against the firmware definition
    cli("sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(tmp / "rt-1.net"), str(SCH))
    tree = parse((tmp / "rt-1.net").read_text())
    comps = {}
    for c in children(children(tree, "components")[0], "comp"):
        get = lambda k: unq(children(c, k)[0][1]) if children(c, k) else ""   # noqa: E731
        comps[get("ref")] = (get("value"), get("footprint"))
    got = {frozenset((unq(children(x, "ref")[0][1]), unq(children(x, "pin")[0][1])) for x in children(n, "node"))
           for n in children(children(tree, "nets")[0], "net")}
    want, want_comps = set(), {"J1": JACK_FP}
    for i, a, c, value in elements():
        want |= {frozenset({("J1", str(a)), (f"D{i}", "2")}),      # pin 2 of the diode symbol is the anode
                 frozenset({(f"D{i}", "1"), (f"R{i}", "1")}),
                 frozenset({(f"R{i}", "2"), ("J1", str(c))})}
        want_comps[f"D{i}"], want_comps[f"R{i}"] = DIODE_FP, RES_FP
        if comps.get(f"R{i}", ("",))[0] != value:
            problems.append(f"R{i}: value {comps.get(f'R{i}')} in the schematic, {value!r} from the firmware")
    for net in sorted(want - got, key=sorted):
        problems.append(f"net missing from the schematic: {sorted(net)}")
    for net in sorted(got - want, key=sorted):
        problems.append(f"net in the schematic that the firmware definition does not have: {sorted(net)}")
    for ref, fp in want_comps.items():
        if comps.get(ref, ("", ""))[1] != fp:
            problems.append(f"{ref}: footprint {comps.get(ref)} in the schematic, expected {fp}")
    for ref in sorted(set(comps) - set(want_comps)):
        problems.append(f"unexpected part {ref}")
    print(f"netlist: {len(comps)} parts, {len(got)} nets; firmware definition expects {len(want_comps)} parts, {len(want)} nets")

    # 3. DRC with parity
    cli("pcb", "drc", "--schematic-parity", "--severity-all", "--format", "json", "-o", str(tmp / "drc.json"), str(PCB))
    drc = json.loads((tmp / "drc.json").read_text())
    counts = {k: len(drc.get(k, [])) for k in ("violations", "unconnected_items", "schematic_parity")}
    for k in counts:
        for v in drc.get(k, []):
            problems.append(f"DRC {k}: {v['description']} [{'; '.join(i['description'] for i in v['items'])}]")
    print(f"DRC: {counts['violations']} violations, {counts['unconnected_items']} unconnected, "
          f"{counts['schematic_parity']} schematic parity issues")

    # 4. board facts, read from the board file itself
    board = parse(PCB.read_text())
    copper = [unq(layer[1]) for layer in children(board, "layers")[0][1:] if unq(layer[1]).endswith(".Cu")]
    xs, ys = [], []
    for kind in ("gr_line", "gr_rect"):
        for g in children(board, kind):
            if unq(children(g, "layer")[0][1]) == "Edge.Cuts":
                for key in ("start", "end"):
                    xs.append(float(children(g, key)[0][1]))
                    ys.append(float(children(g, key)[0][2]))
    size = (round(max(xs) - min(xs), 2), round(max(ys) - min(ys), 2))
    if copper != ["F.Cu", "B.Cu"]:
        problems.append(f"expected a two-layer board, found {copper}")
    print(f"board: {len(copper)} copper layers, outline {size[0]} x {size[1]} mm, "
          f"{len(children(board, 'footprint'))} footprints, {len(children(board, 'segment'))} track segments, "
          f"{len(children(board, 'via'))} vias")

    for p in problems:
        print("  FAIL " + p)
    ok = not problems
    print("RT-1 check (" + cli("version").stdout.strip() + "): " + ("passed" if ok else f"{len(problems)} problem(s)"))

    if ok and "--fab" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--fab") + 1]).resolve()
        (out / "gerbers").mkdir(parents=True, exist_ok=True)
        layers = "F.Cu,B.Cu,F.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"
        steps = [
            ("pcb", "export", "gerbers", "--layers", layers, "-o", str(out / "gerbers") + "/", str(PCB)),
            ("pcb", "export", "drill", "--format", "excellon", "--excellon-units", "mm", "-o", str(out / "gerbers") + "/", str(PCB)),
            ("pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "front", "-o", str(out / "rt-1-placement.csv"), str(PCB)),
            ("sch", "export", "bom", "--fields", "Reference,Value,Footprint,MPN,Manufacturer,Tolerance,Rating,${QUANTITY}",
             "--labels", "Refs,Value,Footprint,MPN,Manufacturer,Tolerance,Rating,Qty", "--group-by", "Value,Footprint",
             "-o", str(out / "rt-1-bom.csv"), str(SCH)),
            ("sch", "export", "pdf", "-o", str(out / "rt-1-schematic.pdf"), str(SCH)),
            ("pcb", "export", "svg", "--layers", "F.Cu,B.Cu,F.SilkS,F.Mask,Edge.Cuts", "--mode-single",
             "--page-size-mode", "2", "-o", str(out / "rt-1-front.svg"), str(PCB)),
            ("pcb", "export", "svg", "--layers", "B.Cu,B.SilkS,Edge.Cuts", "--mirror", "--mode-single",
             "--page-size-mode", "2", "-o", str(out / "rt-1-back.svg"), str(PCB)),
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
