#!/usr/bin/env python3
"""Generate the KiCad 9 schematic project from the block netlist.

    python tools/gen_kicad.py            # writes hardware/kicad/netscope-x1/
    python tools/check_kicad.py          # ERC + netlist comparison with kicad-cli

One hierarchical sheet per entry in the netlist's `sheets:` map.  Every part
is a project-local block symbol (a box with one pin per function); nets are
joined by global labels, so a net keeps the same name on every sheet.

What this is: the block netlist in KiCad form, checked by KiCad itself.
What it is not: schematic capture.  Pins carry FUNCTION names and placeholder
pin numbers, bundles such as RGMII are one pin, footprints are not assigned
and datasheet application parts (decoupling, straps, compensation) are absent.
Replace each block symbol with the real part's symbol sheet by sheet.

The files are regenerated from hardware/netlist/netscope-x1.yaml: edit the
YAML, not the generated schematic, until real capture starts.
"""
from __future__ import annotations

import csv
import json
import math
import sys
import uuid
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from kicad_lib import Sheet, load_symbol, pin_info  # noqa: E402
from main_sheets import CAPTURED, MCU, REFINES, U40_PINS  # noqa: E402

NETLIST = ROOT / "hardware/netlist/netscope-x1.yaml"
BOM = ROOT / "hardware/bom/bom.csv"
OUT = ROOT / "hardware/kicad/netscope-x1"
FLOORPLAN = ROOT / "hardware/pcb/floorplan.yaml"
DOMAINS = ("LINE", "POE", "SYS")
PROJECT = "netscope-x1"
LIB = "netscope-x1"
SCH_VERSION, GEN_VERSION = 20250114, "9.0"
NS = uuid.UUID("6f1d5b0e-2c1a-4c55-9d53-0c7a5e1f9a10")
RAILS = ("GND", "CHASSIS", "POE_VSS")
G = 2.54
STUB = 5.08
PAPER = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0)}
FONT = "(effects (font (size 1.27 1.27)))"


def uid(*parts: str) -> str:
    return str(uuid.uuid5(NS, "/".join(parts)))


def q(s) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def snap(v: float, step: float = G) -> float:
    return round(round(v / step) * step, 4)


def slug(title: str) -> str:
    """Short file-name stem: the sheet title up to its first colon or comma."""
    head = title.split(":")[0].split(",")[0]
    keep = "".join(c.lower() if c.isalnum() else "_" for c in head)
    while "__" in keep:
        keep = keep.replace("__", "_")
    return keep.strip("_")


class Design:
    def __init__(self):
        d = yaml.safe_load(NETLIST.read_text())
        self.title = d.get("title", "NetScope X1")
        self.comps, self.nets, self.sheets = d["components"], d["nets"], d["sheets"]
        self.barriers = d.get("barriers", {})
        with BOM.open(newline="") as f:
            self.bom = {r["key"]: r for r in csv.DictReader(f)}
        order = [r for refs in self.sheets.values() for r in refs]
        self.rank = {r: i for i, r in enumerate(order)}
        self.pin_net: dict[str, dict] = {}
        self.pins: dict[str, list[str]] = defaultdict(list)
        for net in self.nets:
            for node in net["nodes"]:
                ref, pin = node.split(".", 1)
                self.pin_net[node] = net
                self.pins[ref].append(pin)

    def side(self, ref: str, pin: str) -> str:
        net = self.pin_net[f"{ref}.{pin}"]
        if net.get("source") == f"{ref}.{pin}":
            return "R"
        if net["name"] in RAILS or net.get("source"):
            return "L"
        others = [self.rank[n.split(".", 1)[0]] for n in net["nodes"] if n.split(".", 1)[0] != ref]
        return "L" if others and min(others) < self.rank[ref] else "R"

    def etype(self, ref: str, pin: str) -> str:
        net = self.pin_net[f"{ref}.{pin}"]
        if net.get("source") == f"{ref}.{pin}":
            return "power_out"
        return "power_in" if net.get("source") else "passive"

    def geometry(self, ref: str):
        """(width, height, [(pin, number, side, local_x, local_y)]) in symbol coordinates (Y up)."""
        left = [p for p in self.pins[ref] if self.side(ref, p) == "L"]
        right = [p for p in self.pins[ref] if self.side(ref, p) == "R"]
        chars = max([len(p) for p in left] + [0]) + max([len(p) for p in right] + [0])
        w = max(25.4, math.ceil((chars * 1.05 + 8) / 5.08) * 5.08)
        h = (max(len(left), len(right), 1) + 1) * G
        number = {p: str(i + 1) for i, p in enumerate(self.pins[ref])}
        out = []
        for names, sx, s in ((left, -w / 2 - G, "L"), (right, w / 2 + G, "R")):
            for i, p in enumerate(names):
                out.append((p, number[p], s, round(sx, 4), round(h / 2 - G * (i + 1), 4)))
        return w, h, out

    def fields(self, ref: str) -> dict[str, str]:
        c = self.comps[ref]
        b = self.bom.get(c.get("bom", ""), {})
        dom = c["domain"]
        return {
            "Manufacturer": b.get("manufacturer", ""), "MPN": b.get("mpn", ""),
            "MPN_Status": b.get("mpn_status", ""), "BOM_Key": c.get("bom", ""),
            "Domain": "+".join(dom) if isinstance(dom, list) else dom,
            "Barrier": self.barriers.get(ref, {}).get("rating", ""),
        }


def prefix(ref: str) -> str:
    return ref.rstrip("0123456789")


def lib_symbol(d: Design, ref: str, qualified: bool) -> str:
    w, h, pins = d.geometry(ref)
    name = f"BLK_{ref}"
    full = f"{LIB}:{name}" if qualified else name
    c = d.comps[ref]
    barrier = ref in d.barriers
    props = [("Reference", prefix(ref), 0, h / 2 + 3.81, False),
             ("Value", c["part"], 0, h / 2 + 1.27, False),
             ("Footprint", "", 0, 0, True), ("Datasheet", "", 0, 0, True),
             ("Description", f"Block symbol for {c['part']} (function pins, placeholder numbers)", 0, 0, True)]
    s = [f"(symbol {q(full)} (pin_names (offset 1.016)) (exclude_from_sim no) (in_bom yes) (on_board yes)"]
    for key, val, x, y, hide in props:
        s.append(f"(property {q(key)} {q(val)} (at {x} {round(y, 4)} 0) "
                 f"(effects (font (size 1.27 1.27)){' (hide yes)' if hide else ''}))")
    stroke = "(stroke (width 0.3048) (type dash))" if barrier else "(stroke (width 0.254) (type default))"
    s.append(f"(symbol {q(name + '_0_1')} (rectangle (start {-w / 2} {h / 2}) (end {w / 2} {-h / 2}) "
             f"{stroke} (fill (type background))))")
    s.append(f"(symbol {q(name + '_1_1')}")
    for pin, num, side, x, y in pins:
        ang = 0 if side == "L" else 180
        s.append(f"(pin {d.etype(ref, pin)} line (at {x} {y} {ang}) (length {G}) "
                 f"(name {q(pin)} {FONT}) (number {q(num)} {FONT}))")
    s.append(")")
    s.append("(embedded_fonts no))")
    return "\n".join(s)


def title_block(d: Design, sheet_title: str) -> str:
    return (f"(title_block (title {q(sheet_title)}) (rev \"A-draft\") "
            f"(company \"MT Tech Services LLC\") "
            f"(comment 1 \"BLOCK LEVEL: function-named pins with placeholder numbers. Not for fabrication.\") "
            f"(comment 2 \"Generated from hardware/netlist/netscope-x1.yaml by tools/gen_kicad.py\") "
            f"(comment 3 {q(d.title)}))")


def text(s: str, x: float, y: float, size: float = 1.8) -> str:
    return (f"(text {q(s)} (exclude_from_sim no) (at {x} {y} 0) "
            f"(effects (font (size {size} {size})) (justify left bottom)) (uuid {q(uid('text', s, str(x), str(y)))}))")


def glabel(net: str, x: float, y: float, side: str, key: str) -> str:
    ang, just = (180, "right") if side == "L" else (0, "left")
    return (f"(global_label {q(net)} (shape passive) (at {x} {y} {ang}) (fields_autoplaced yes) "
            f"(effects (font (size 1.27 1.27)) (justify {just})) (uuid {q(uid('lbl', key))}) "
            f"(property \"Intersheetrefs\" \"${{INTERSHEET_REFS}}\" (at 0 0 0) "
            f"(effects (font (size 1.27 1.27)) (hide yes))))")


def wire(x1, y1, x2, y2, key: str) -> str:
    return (f"(wire (pts (xy {x1} {y1}) (xy {x2} {y2})) (stroke (width 0) (type default)) "
            f"(uuid {q(uid('wire', key))}))")


def place(d: Design, refs: list[str]):
    """Balanced column layout on the smallest paper that fits.  Returns (paper, {ref: (x, y)})."""
    top, gap, pitch = 27.94, 7.62, 132.08
    need = {r: d.geometry(r)[1] + 2 * gap for r in refs}
    for paper in ("A4", "A3", "A2"):
        pw, ph = PAPER[paper]
        ncols, usable = int((pw - 30) // pitch), ph - top - 38
        if max(need.values()) > usable:
            continue
        target = min(usable, max(sum(need.values()) / ncols, max(need.values())))
        while True:                      # shortest column height that needs no more than ncols
            cols, used = [[]], 0.0
            for r in refs:
                if cols[-1] and used + need[r] > target + 0.01:
                    cols.append([])
                    used = 0.0
                cols[-1].append(r)
                used += need[r]
            if len(cols) <= ncols or target >= usable:
                break
            target = min(usable, target + G)
        if len(cols) > ncols:
            continue
        x0 = snap(15 + (pw - 30 - len(cols) * pitch) / 2 + pitch / 2)
        pos = {}
        for ci, col in enumerate(cols):
            y = top
            for r in col:
                h = need[r] - 2 * gap
                cy = snap(y + gap + h / 2)
                pos[r] = (snap(x0 + ci * pitch), cy)
                y = cy + h / 2 + gap
        return paper, pos
    raise SystemExit(f"sheet with {len(refs)} parts does not fit on A2")


def sheet_file(d: Design, title: str, refs: list[str], root_uuid: str, sheet_uuid: str) -> str:
    paper, pos = place(d, refs)
    o = [f"(kicad_sch (version {SCH_VERSION}) (generator \"netscope_gen_kicad\") "
         f"(generator_version {q(GEN_VERSION)}) (uuid {q(uid('sheetfile', title))}) (paper {q(paper)})",
         title_block(d, title), "(lib_symbols"]
    o += [lib_symbol(d, r, True) for r in refs]
    o.append(")")
    o.append(text("Block-level sheet. Dashed outline = isolation barrier part. Net names are global.",
                  15.24, 20.32))
    for ref in refs:
        x, y = pos[ref]
        w, h, pins = d.geometry(ref)
        c = d.comps[ref]
        o.append(f"(symbol (lib_id {q(f'{LIB}:BLK_{ref}')}) (at {x} {y} 0) (unit 1) (exclude_from_sim no) "
                 f"(in_bom yes) (on_board yes) (dnp no) (uuid {q(uid('sym', ref))})")
        o.append(f"(property \"Reference\" {q(ref)} (at {x} {round(y - h / 2 - 3.81, 4)} 0) {FONT})")
        o.append(f"(property \"Value\" {q(c['part'])} (at {x} {round(y - h / 2 - 1.27, 4)} 0) {FONT})")
        for key in ("Footprint", "Datasheet"):
            o.append(f"(property {q(key)} \"\" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))")
        o.append(f"(property \"Description\" {q('Block symbol for ' + c['part'])} (at {x} {y} 0) "
                 f"(effects (font (size 1.27 1.27)) (hide yes)))")
        for key, val in d.fields(ref).items():
            if val:
                o.append(f"(property {q(key)} {q(val)} (at {x} {y} 0) "
                         f"(effects (font (size 1.27 1.27)) (hide yes)))")
        for _, num, *_ in pins:
            o.append(f"(pin {q(num)} (uuid {q(uid('pin', ref, num))}))")
        o.append(f"(instances (project {q(PROJECT)} (path {q('/' + root_uuid + '/' + sheet_uuid)} "
                 f"(reference {q(ref)}) (unit 1)))))")
        for pin, num, side, lx, ly in pins:
            px, py = round(x + lx, 4), round(y - ly, 4)
            ex = round(px - STUB if side == "L" else px + STUB, 4)
            net = d.pin_net[f"{ref}.{pin}"]["name"]
            o.append(wire(px, py, ex, py, f"{ref}.{pin}"))
            o.append(glabel(net, ex, py, side, f"{ref}.{pin}"))
    o.append("(embedded_fonts no))")
    return "\n".join(o) + "\n"


def root_file(d: Design, root_uuid: str, sheets: list[tuple[str, str, str]]) -> str:
    o = [f"(kicad_sch (version {SCH_VERSION}) (generator \"netscope_gen_kicad\") "
         f"(generator_version {q(GEN_VERSION)}) (uuid {q(root_uuid)}) (paper \"A3\")",
         title_block(d, "NetScope X1 main board - sheet index"), "(lib_symbols)"]
    notes = ["NetScope X1 main board, rev A draft: BLOCK-LEVEL schematic.",
             "Generated from hardware/netlist/netscope-x1.yaml. Do not edit by hand; edit the YAML and run tools/gen_kicad.py.",
             "Sheets marked REAL CAPTURE in their title block use library symbols and real pins (tools/main_sheets.py); the rest are block level:",
             "Each part is a box with one pin per FUNCTION. Pin numbers are placeholders, bundles (RGMII, MDI, USB...) are one pin.",
             "No footprints, no decoupling or other datasheet application parts. Not a fabrication schematic.",
             "Domains: SYS = system side, LINE = cable conductors, POE = network-powered. Barrier parts have dashed outlines.",
             "Checks: tools/check_kicad.py runs KiCad ERC and compares KiCad's exported netlist with the YAML netlist."]
    for i, n in enumerate(notes):
        o.append(text(n, 20.32, 30.48 + i * 5.08, 2.0 if i == 0 else 1.6))
    for i, (title, fname, suid) in enumerate(sheets):
        x, y = 25.4 + (i % 4) * 96.52, 81.28 + (i // 4) * 50.8
        o.append(f"(sheet (at {x} {y}) (size 81.28 30.48) (exclude_from_sim no) (in_bom yes) (on_board yes) "
                 f"(dnp no) (fields_autoplaced yes) (stroke (width 0.1524) (type solid)) "
                 f"(fill (color 0 0 0 0.0)) (uuid {q(suid)})")
        o.append(f"(property \"Sheetname\" {q(title)} (at {x} {round(y - 0.7, 4)} 0) "
                 f"(effects (font (size 1.27 1.27)) (justify left bottom)))")
        o.append(f"(property \"Sheetfile\" {q(fname)} (at {x} {round(y + 31.2, 4)} 0) "
                 f"(effects (font (size 1.27 1.27)) (justify left top)))")
        o.append(f"(instances (project {q(PROJECT)} (path {q('/' + root_uuid)} (page {q(str(i + 2))})))))")
    o.append("(sheet_instances (path \"/\" (page \"1\")))")
    o.append("(embedded_fonts no))")
    return "\n".join(o) + "\n"


def project_file(d: Design) -> str:
    """Net classes carry the electrical domain; the spacing between domains is a
    custom rule in the .kicad_dru file, so nets inside one domain keep normal clearance."""
    base = {"name": "Default", "clearance": 0.15, "track_width": 0.15, "via_diameter": 0.6,
            "via_drill": 0.3, "wire_width": 6, "bus_width": 12, "line_style": 0,
            "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)",
            "diff_pair_gap": 0.15, "diff_pair_width": 0.15, "diff_pair_via_gap": 0.25,
            "microvia_diameter": 0.3, "microvia_drill": 0.1, "priority": 2147483647}
    colour = {"SYS": "rgb(29, 78, 216)", "LINE": "rgb(180, 83, 9)", "POE": "rgb(185, 28, 28)"}
    patterns = [{"netclass": n["domain"], "pattern": n["name"]} for n in d.nets]
    domain = {n["name"]: n["domain"] for n in d.nets}
    for real, block in sorted(REFINES.items()):            # pin-level nets on captured sheets take their block net's domain
        if real not in domain:
            patterns.append({"netclass": domain[block[0]] if block else "SYS", "pattern": real})
    path = OUT / f"{PROJECT}.kicad_pro"
    prj = json.loads(path.read_text()) if path.exists() else {
        "board": {"design_settings": {"defaults": {}, "rules": {"min_clearance": 0.1}}},
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "sheets": [], "text_variables": {}}
    # Only the net classes and their assignments are generated; every other setting
    # in an existing project file (KiCad rewrites it on save) is kept as it is.
    prj["meta"] = {"filename": f"{PROJECT}.kicad_pro", "version": prj.get("meta", {}).get("version", 3)}
    net = prj.setdefault("net_settings", {})
    kept = [c for c in net.get("classes", []) if c.get("name") not in ("Default", *DOMAINS)]
    default = next((c for c in net.get("classes", []) if c.get("name") == "Default"), None)
    default = default or base
    domains = [{**default, "name": dom, "priority": i, "schematic_color": colour[dom],
                "pcb_color": colour[dom]} for i, dom in enumerate(DOMAINS)]
    net["classes"] = [default] + domains + kept
    net["meta"] = {"version": 4}
    net.setdefault("net_colors", None)
    net.setdefault("netclass_assignments", None)
    net["netclass_patterns"] = patterns
    return json.dumps(prj, indent=2, sort_keys=True) + "\n"


def rules_file() -> str:
    iso = yaml.safe_load(FLOORPLAN.read_text())["rules"]["isolation"]
    o = ["(version 1)",
         "# Generated by tools/gen_kicad.py.  Spacing between electrical domains, from",
         "# rules.isolation in hardware/pcb/floorplan.yaml.  A design value, not a safety",
         "# rating: creepage and clearance for the PoE barrier still need a standards review."]
    for a, b in (("LINE", "SYS"), ("POE", "SYS"), ("LINE", "POE")):
        o.append(f"(rule \"isolation_{a}_{b}\"\n"
                 f"  (condition \"A.hasNetclass('{a}') && B.hasNetclass('{b}')\")\n"
                 f"  (constraint clearance (min {iso}mm)))")
    return "\n".join(o) + "\n"


def pin_table() -> str:
    """The coprocessor pin plan as a table, for the firmware and for review."""
    info = pin_info(load_symbol(*MCU.split(":")))
    number = {}
    for num, (_, _, _, name) in info.items():
        number.setdefault(name, []).append(num)
    o = ["# Coprocessor pin plan (U40, STM32G0B1CBU6, UFQFPN-48)", "",
         "Generated by `tools/gen_kicad.py` from `tools/main_sheets.py`; the schematic sheet is drawn from the same table.",
         "Functions in the last column are checked against the alternate-function list in KiCad's library symbol.",
         "Not yet checked against the reference manual: boot entry through PA14-BOOT0 and the UCPD dead-battery pins.", "",
         "| Pin | Name | Net | Peripheral function |", "|---|---|---|---|"]
    for name, (net, function) in sorted(U40_PINS.items(), key=lambda kv: min(int(n) for n in number[kv[0]])):
        o.append(f"| {', '.join(sorted(number[name], key=int))} | {name} | {net} | {function or 'GPIO' if name[0] == 'P' else 'supply'} |")
    return "\n".join(o) + "\n"


def main() -> None:
    d = Design()
    OUT.mkdir(parents=True, exist_ok=True)
    root_uuid = uid("root")
    sheets = []
    for n, (title, refs) in enumerate(d.sheets.items(), 1):
        fname, suid = f"{n:02d}_{slug(title)}.kicad_sch", uid("sheet", title)
        if title in CAPTURED:                              # a real, pin-level sheet replaces the block one
            stem, build = CAPTURED[title]
            fname = f"{stem}.kicad_sch"
            real = Sheet(PROJECT, f"netscope-x1/main/{stem}", title, "A3")
            real.instance_path, real.is_root, real.global_labels = f"/{root_uuid}/{suid}", False, True
            real.rev = "A-draft"
            real.comments = ["REAL CAPTURE: library symbols and real pin numbers. UNTESTED.",
                             "Generated by tools/gen_kicad.py from tools/main_sheets.py"]
            build(real)
            (OUT / fname).write_text(real.render("MT Tech Services LLC"))
        else:
            (OUT / fname).write_text(sheet_file(d, title, refs, root_uuid, suid))
        sheets.append((title, fname, suid))
    (OUT / f"{PROJECT}.kicad_sch").write_text(root_file(d, root_uuid, sheets))
    lib = [f"(kicad_symbol_lib (version 20241209) (generator \"netscope_gen_kicad\") "
           f"(generator_version {q(GEN_VERSION)})"]
    lib += [lib_symbol(d, r, False) for title, refs in d.sheets.items() if title not in CAPTURED for r in refs]
    (OUT / f"{LIB}.kicad_sym").write_text("\n".join(lib) + "\n)\n")
    (OUT / "sym-lib-table").write_text(
        f"(sym_lib_table\n  (version 7)\n  (lib (name {q(LIB)})(type \"KiCad\")"
        f"(uri \"${{KIPRJMOD}}/{LIB}.kicad_sym\")(options \"\")(descr \"NetScope X1 block symbols (generated)\"))\n)\n")
    (OUT / f"{PROJECT}.kicad_pro").write_text(project_file(d))
    (OUT / f"{PROJECT}.kicad_dru").write_text(rules_file())
    (OUT.parent / "coprocessor-pins.md").write_text(pin_table())
    current = {f for _, f, _ in sheets} | {f"{PROJECT}.kicad_sch"}
    stale = sorted(p.name for p in OUT.glob("*.kicad_sch") if p.name not in current)
    if stale:
        print("stale sheet files no longer in the netlist (delete by hand): " + ", ".join(stale))
    print(f"wrote {OUT.relative_to(ROOT)}: root + {len(sheets)} sheets ({len(CAPTURED)} captured for real, "
          f"{len(sheets) - len(CAPTURED)} block level), {len(d.nets)} block nets")


if __name__ == "__main__":
    main()
