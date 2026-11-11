#!/usr/bin/env python3
"""Check the generated KiCad project with KiCad itself (needs kicad-cli 9).

    python tools/check_kicad.py [--pdf OUT.pdf]

1. Electrical rule check on the whole hierarchy; any violation fails.
2. KiCad's exported netlist is compared with hardware/netlist/netscope-x1.yaml:
   same parts with the same values, same nets, same pins on every net.
3. Net classes: each sheet is loaded on its own and every net must carry the
   class of its domain (kicad-cli reports "Default" for nets on sub-sheets
   when it exports a hierarchy, so the hierarchy export cannot show this).
4. If the board file exists: design rule check of the outline and holes.
   Footprint/schematic parity is NOT checked: the block symbols have no
   footprints yet.
5. Isolation rule probe (needs KiCad's `pcbnew` module under /usr/bin/python3):
   a scratch board with one track pair per domain pair 1 mm apart, plus two
   same-domain tracks 0.4 mm apart.  Each cross-domain pair must be flagged
   by its rule and the same-domain pair must not.  This is needed because
   kicad-cli silently ignores a rules file it cannot parse.

Passing means the KiCad files say what the YAML netlist says.  It does not
mean the design is electrically correct: pins are function names, and ERC
only sees the pin types the generator assigned (one driver per power net).
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
NETLIST = ROOT / "hardware/netlist/netscope-x1.yaml"
PRJ = ROOT / "hardware/kicad/netscope-x1"
NAME = "netscope-x1"


def cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["kicad-cli", *args], capture_output=True, text=True)


def parse_sexpr(text: str):
    """Minimal S-expression reader: nested lists of strings."""
    stack, cur, i, n = [], [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "(":
            stack.append(cur)
            cur = []
        elif c == ")":
            done, cur = cur, stack.pop()
            cur.append(done)
        elif c == '"':
            j, buf = i + 1, []
            while text[j] != '"':
                if text[j] == "\\":
                    j += 1
                buf.append(text[j])
                j += 1
            cur.append("".join(buf))
            i = j
        elif not c.isspace():
            j = i
            while j < n and not text[j].isspace() and text[j] not in "()":
                j += 1
            cur.append(text[i:j])
            i = j - 1
        i += 1
    return cur[0]


def find(node, key):
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == key]


def attr(node, key):
    hit = find(node, key)
    return hit[0][1] if hit and len(hit[0]) > 1 else ""


def export_netlist(sch: Path, out: Path):
    r = cli("sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(out), str(sch))
    if r.returncode or not out.exists():
        raise SystemExit(f"netlist export failed for {sch.name}:\n{r.stdout}{r.stderr}")
    tree = parse_sexpr(out.read_text())
    comps = {attr(c, "ref"): attr(c, "value") for c in find(find(tree, "components")[0], "comp")}
    nets = {}
    for net in find(find(tree, "nets")[0], "net"):
        nets[attr(net, "name")] = (attr(net, "class"),
                                   {f"{attr(n, 'ref')}.{attr(n, 'pinfunction')}" for n in find(net, "node")})
    return comps, nets


def main() -> int:
    if not shutil.which("kicad-cli"):
        print("kicad-cli not found: install KiCad 9 to run this check")
        return 2
    version = cli("version").stdout.strip()
    design = yaml.safe_load(NETLIST.read_text())
    root = PRJ / f"{NAME}.kicad_sch"
    problems: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="nsx-kicad-"))

    # 1. ERC
    erc_out = tmp / "erc.json"
    r = cli("sch", "erc", "--format", "json", "--severity-all", "-o", str(erc_out), str(root))
    if not erc_out.exists():
        raise SystemExit(f"ERC did not run:\n{r.stdout}{r.stderr}")
    erc = json.loads(erc_out.read_text())
    violations = [(s["path"], v) for s in erc["sheets"] for v in s["violations"]]
    for path, v in violations:
        items = "; ".join(i["description"] for i in v["items"])
        problems.append(f"ERC {v['severity']} on {path}: {v['description']} [{items}]")
    print(f"ERC: {len(erc['sheets'])} sheets, {len(violations)} violations")

    # 2. netlist comparison
    comps, nets = export_netlist(root, tmp / "root.net")
    want_comps = {ref: c["part"] for ref, c in design["components"].items()}
    want_nets = {n["name"]: set(n["nodes"]) for n in design["nets"]}
    for ref in sorted(set(want_comps) - set(comps)):
        problems.append(f"part {ref} is in the YAML netlist but not in KiCad")
    for ref in sorted(set(comps) - set(want_comps)):
        problems.append(f"part {ref} is in KiCad but not in the YAML netlist")
    for ref in sorted(set(comps) & set(want_comps)):
        if comps[ref] != want_comps[ref]:
            problems.append(f"{ref}: value {comps[ref]!r} in KiCad, {want_comps[ref]!r} in YAML")
    for name in sorted(set(want_nets) - set(nets)):
        problems.append(f"net {name} is in the YAML netlist but not in KiCad")
    for name in sorted(set(nets) - set(want_nets)):
        problems.append(f"net {name} is in KiCad but not in the YAML netlist")
    for name in sorted(set(nets) & set(want_nets)):
        got, want = nets[name][1], want_nets[name]
        if got != want:
            problems.append(f"net {name}: only in KiCad {sorted(got - want)}, only in YAML {sorted(want - got)}")
    nodes = sum(len(v[1]) for v in nets.values())
    print(f"netlist: {len(comps)} parts, {len(nets)} nets, {nodes} pins in KiCad; "
          f"{len(want_comps)} parts, {len(want_nets)} nets, {sum(map(len, want_nets.values()))} pins in YAML")

    # 3. net classes, one sheet at a time
    domain = {n["name"]: n["domain"] for n in design["nets"]}
    checked = 0
    for sheet in sorted(PRJ.glob("*.kicad_sch")):
        if sheet == root:
            continue
        flat = tmp / sheet.stem
        flat.mkdir()
        shutil.copy(sheet, flat / "flat.kicad_sch")
        shutil.copy(PRJ / f"{NAME}.kicad_pro", flat / "flat.kicad_pro")
        shutil.copy(PRJ / f"{NAME}.kicad_sym", flat)
        shutil.copy(PRJ / "sym-lib-table", flat)
        _, flat_nets = export_netlist(flat / "flat.kicad_sch", flat / "flat.net")
        for name, (cls, _) in flat_nets.items():
            checked += 1
            if cls != domain.get(name):
                problems.append(f"net {name} on {sheet.name}: class {cls!r}, domain {domain.get(name)!r}")
    print(f"net classes: {checked} net-on-sheet assignments checked against domains")

    # 4. board
    pcb = PRJ / f"{NAME}.kicad_pcb"
    if pcb.exists():
        drc_out = tmp / "drc.json"
        r = cli("pcb", "drc", "--format", "json", "--severity-all", "-o", str(drc_out), str(pcb))
        if not drc_out.exists():
            raise SystemExit(f"DRC did not run:\n{r.stdout}{r.stderr}")
        if "rror" in r.stderr:
            problems.append(f"DRC reported: {r.stderr.strip()}")
        drc = json.loads(drc_out.read_text())
        found = drc.get("violations", []) + drc.get("unconnected_items", [])
        for v in found:
            problems.append(f"DRC {v['severity']}: {v['description']}")
        print(f"DRC: {len(found)} violations (outline and mounting holes only; no footprints or nets yet)")
    else:
        print("DRC: no board file, skipped")

    # 5. isolation rules really fire
    by_domain: dict[str, list[str]] = {}
    for n in design["nets"]:
        by_domain.setdefault(n["domain"], []).append(n["name"])
    pairs = [("LINE", "SYS"), ("POE", "SYS"), ("LINE", "POE")]
    tracks, y = [], 100.0
    for a, b in pairs:                                   # 0.2 mm tracks, 1.0 mm apart
        tracks += [(by_domain[a][0], y), (by_domain[b][1], y + 1.2)]
        y += 20
    tracks += [(by_domain["LINE"][2], y), (by_domain["LINE"][3], y + 0.6)]   # same domain, 0.4 mm
    probe = tmp / "probe"
    probe.mkdir()
    shutil.copy(PRJ / f"{NAME}.kicad_pro", probe / "probe.kicad_pro")
    shutil.copy(PRJ / f"{NAME}.kicad_dru", probe / "probe.kicad_dru")
    script = (
        "import pcbnew, json, sys\n"
        "b = pcbnew.BOARD()\n"
        "for net, y in json.loads(sys.argv[1]):\n"
        "    n = pcbnew.NETINFO_ITEM(b, net); b.Add(n)\n"
        "    t = pcbnew.PCB_TRACK(b)\n"
        "    t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(100), pcbnew.FromMM(y)))\n"
        "    t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(120), pcbnew.FromMM(y)))\n"
        "    t.SetWidth(pcbnew.FromMM(0.2)); t.SetLayer(pcbnew.F_Cu); t.SetNet(n); b.Add(t)\n"
        "pcbnew.SaveBoard(sys.argv[2], b)\n")
    made = subprocess.run(["/usr/bin/python3", "-c", script, json.dumps(tracks), str(probe / "scratch.kicad_pcb")],
                          capture_output=True, text=True)
    if made.returncode or not (probe / "scratch.kicad_pcb").exists():
        print("isolation rules: SKIPPED, KiCad's pcbnew Python module is not available")
    else:
        shutil.copy(probe / "scratch.kicad_pcb", probe / "probe.kicad_pcb")
        cli("pcb", "drc", "--format", "json", "--severity-all", "-o", str(probe / "drc.json"),
            str(probe / "probe.kicad_pcb"))
        hits = [v["description"] for v in json.loads((probe / "drc.json").read_text())["violations"]
                if v["type"] == "clearance"]
        for a, b in pairs:
            if sum(f"isolation_{a}_{b}" in h for h in hits) != 1:
                problems.append(f"isolation rule {a}-{b} did not flag a 1.0 mm gap (rules file not applied?)")
        if len(hits) != len(pairs):
            problems.append(f"isolation probe: expected {len(pairs)} clearance violations, got {len(hits)}: {hits}")
        print(f"isolation rules: {len(hits)} of {len(pairs)} cross-domain pairs flagged at 1.0 mm, "
              "same-domain pair at 0.4 mm not flagged")

    if "--pdf" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--pdf") + 1]).resolve()
        r = cli("sch", "export", "pdf", "-o", str(out), str(root))
        print(f"pdf: {out}" if out.exists() else f"pdf export failed: {r.stderr}")

    shutil.rmtree(tmp, ignore_errors=True)
    for p in problems:
        print("  FAIL " + p)
    print(f"KiCad check ({version}): " + ("passed" if not problems else f"{len(problems)} problem(s)"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
