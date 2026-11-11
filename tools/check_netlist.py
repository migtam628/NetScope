#!/usr/bin/env python3
"""Design-rule checks on the block-level netlist and BOM.

This is not KiCad ERC (there is no schematic yet). It checks the things that
can be checked now and that matter most later:

  * every net is well formed and every pin is used once
  * BOM and netlist agree
  * power nets have exactly one declared source
  * ISOLATION: no net joins the SYS, LINE and POE domains except through a
    declared barrier part; the processor and coprocessor never sit on a
    LINE or POE net
  * FAIL-SAFE: with the relays unpowered, every cable conductor reaches the
    isolation transformer and nothing else

Exit status is non-zero on any violation.  Usage: tools/check_netlist.py
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
NETLIST = ROOT / "hardware/netlist/netscope-x1.yaml"
BOM = ROOT / "hardware/bom/bom.csv"
PROTECTED = ("M1", "U40")  # processor, coprocessor


def check(netlist: dict, bom_rows: list[dict]) -> list[str]:
    errs: list[str] = []
    comps, nets, barriers = netlist["components"], netlist["nets"], netlist["barriers"]

    def domains(ref: str) -> set[str]:
        d = comps[ref]["domain"]
        return set(d) if isinstance(d, list) else {d}

    for ref in comps:
        if len(domains(ref)) > 1 and ref not in barriers:
            errs.append(f"{ref} spans {sorted(domains(ref))} but is not a declared barrier")
    for ref in barriers:
        if ref not in comps:
            errs.append(f"barrier {ref} is not a component")

    names = Counter(n["name"] for n in nets)
    errs += [f"duplicate net name {n}" for n, c in names.items() if c > 1]

    pin_use: Counter[str] = Counter()
    used_refs: set[str] = set()
    for net in nets:
        name, dom, nodes = net["name"], net["domain"], net["nodes"]
        if len(nodes) < 2:
            errs.append(f"net {name} has fewer than two nodes")
        for node in nodes:
            ref = node.split(".", 1)[0]
            pin_use[node] += 1
            if ref not in comps:
                errs.append(f"net {name}: unknown component {ref}")
                continue
            used_refs.add(ref)
            if dom not in domains(ref):
                errs.append(f"ISOLATION: net {name} ({dom}) touches {ref} "
                            f"({'/'.join(sorted(domains(ref)))})")
            if ref in PROTECTED and dom != "SYS":
                errs.append(f"ISOLATION: {ref} is on non-SYS net {name}")
        is_rail = name[0] in "+-" or name in ("VBAT", "VSYS")
        if is_rail and "source" not in net:
            errs.append(f"power net {name} has no declared source")
        if "source" in net and net["source"] not in nodes:
            errs.append(f"net {name}: source {net['source']} is not on the net")
    errs += [f"pin {p} is on {c} nets" for p, c in pin_use.items() if c > 1]
    errs += [f"component {r} is not connected to anything" for r in comps if r not in used_refs]

    # Fail-safe: jack pin -> relay COM only; relay NC -> transformer line side only.
    by_node = {node: net for net in nets for node in net["nodes"]}
    for pin in range(1, 9):
        net = by_node.get(f"J10.P{pin}")
        if net is None:
            errs.append(f"FAIL-SAFE: J10.P{pin} is unconnected")
            continue
        others = [n for n in net["nodes"] if not n.startswith("J10.")]
        if len(others) != 1 or not (others[0][0] == "K" and ".COM_" in others[0]):
            errs.append(f"FAIL-SAFE: J10.P{pin} must go to exactly one relay common, got {others}")
            continue
        nc = others[0].replace(".COM_", ".NC_")
        nc_net = by_node.get(nc)
        peers = [n for n in (nc_net["nodes"] if nc_net else []) if n != nc]
        if len(peers) != 1 or not peers[0].startswith("T1.LINE_"):
            errs.append(f"FAIL-SAFE: {nc} (unpowered path of pin {pin}) must go only to T1 "
                        f"line side, got {peers}")

    # BOM agreement.
    bom = {r["key"]: r for r in bom_rows}
    used_keys = set()
    for ref, c in comps.items():
        key = c.get("bom")
        used_keys.add(key)
        if key not in bom:
            errs.append(f"{ref}: BOM key '{key}' missing from bom.csv")
        elif ref not in bom[key]["refs"].split():
            errs.append(f"{ref} is not listed in the refs of BOM row '{key}'")
    for key, r in bom.items():
        if r["in_netlist"] == "yes" and key not in used_keys:
            errs.append(f"BOM row '{key}' says in_netlist=yes but no component uses it")
        for col in ("cost_1", "cost_10", "cost_100", "cost_1000"):
            try:
                float(r[col])
            except ValueError:
                errs.append(f"BOM row '{key}': {col} is not a number")
        if r["mpn_status"] not in ("known", "candidate", "tbd"):
            errs.append(f"BOM row '{key}': bad mpn_status '{r['mpn_status']}'")
    return errs


def main() -> int:
    netlist = yaml.safe_load(NETLIST.read_text())
    with BOM.open(newline="") as f:
        rows = list(csv.DictReader(f))
    errs = check(netlist, rows)
    n_nodes = sum(len(n["nodes"]) for n in netlist["nets"])
    print(f"{len(netlist['components'])} components, {len(netlist['nets'])} nets, "
          f"{n_nodes} nodes, {len(rows)} BOM rows")
    for e in errs:
        print("ERROR", e)
    print("netlist check:", "FAILED" if errs else "passed")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
