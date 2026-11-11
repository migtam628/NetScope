#!/usr/bin/env python3
"""Draw a block-level schematic (SVG pages + one PDF) from a netlist YAML.

Style: one box per part, one row per pin, each pin tied to a named net flag.
Nets are followed by name, as on a hierarchical schematic with global labels;
the small numbers after a flag are the other sheets the net appears on, and
the last pages index every net with all of its nodes.

This is a drawing of the block netlist, not a KiCad schematic: pins carry
function names, not package pin numbers, and datasheet application passives
are not shown.  It exists so the design can be read and reviewed.

Usage:
  tools/render_schematic.py hardware/netlist/netscope-x1.yaml hardware/schematic/netscope-x1-main-board
  tools/render_schematic.py hardware/spike/bench-kit.yaml hardware/schematic/bench-kit
The PDF step needs Chrome/Chromium; without it only the SVG pages are written.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from html import escape
from pathlib import Path

import yaml

W, H = 1587, 1122                    # A3 landscape at 96 dpi
MARGIN, TITLE_H = 40, 64
BOX_W, PITCH, STUB, HEAD = 230, 21, 26, 46
COL_W = 495
COLOR = {"SYS": "#1d4ed8", "LINE": "#b45309", "POE": "#b91c1c"}
RAILS = ("GND", "CHASSIS", "POE_VSS")
FONT = "font-family='DejaVu Sans Mono, Menlo, Consolas, monospace'"


def load(path: Path) -> dict:
    d = yaml.safe_load(path.read_text())
    errs = []
    comps = d["components"]
    use = Counter(n for net in d["nets"] for n in net["nodes"])
    errs += [f"pin {n} is on {c} nets" for n, c in use.items() if c > 1]
    for net in d["nets"]:
        for n in net["nodes"]:
            if n.split(".", 1)[0] not in comps:
                errs.append(f"net {net['name']}: unknown part in {n}")
            else:
                dom = comps[n.split(".", 1)[0]]["domain"]
                doms = set(dom) if isinstance(dom, list) else {dom}
                if net["domain"] not in doms:
                    errs.append(f"net {net['name']} ({net['domain']}) touches {n} which is in {sorted(doms)}")
    for ref, c in comps.items():
        if isinstance(c["domain"], list) and ref not in d.get("barriers", {}):
            errs.append(f"{ref} spans domains but is not a declared barrier")
    placed = [r for refs in d["sheets"].values() for r in refs]
    errs += [f"{r} is not on any sheet" for r in comps if r not in placed]
    errs += [f"{r} is on a sheet but not a component" for r in placed if r not in comps]
    if errs:
        sys.exit("netlist errors:\n  " + "\n  ".join(errs))
    return d


def text(x, y, s, size=11, fill="#111", anchor="start", weight="normal", extra=""):
    return (f"<text x='{x:.0f}' y='{y:.0f}' font-size='{size}' fill='{fill}' text-anchor='{anchor}' "
            f"font-weight='{weight}' {FONT} {extra}>{escape(str(s))}</text>")


def wrap(s: str, n: int) -> list[str]:
    out, line = [], ""
    for word in s.split():
        if len(line) + len(word) + 1 > n and line:
            out.append(line)
            line = word
        else:
            line = (line + " " + word).strip()
    return out + [line] if line else out


def frame(title: str, doc: str, page: int, pages: int, note: str) -> str:
    y = H - MARGIN - TITLE_H
    legend = "".join(
        f"<rect x='{MARGIN + 600 + i * 190}' y='{y + 38}' width='12' height='12' fill='{c}'/>"
        + text(MARGIN + 618 + i * 190, y + 49, lab, 10)
        for i, (lab, c) in enumerate((("SYS  system side", COLOR["SYS"]),
                                      ("LINE  cable conductors", COLOR["LINE"]),
                                      ("POE  network-powered", COLOR["POE"]))))
    return (f"<rect x='{MARGIN}' y='{MARGIN}' width='{W - 2 * MARGIN}' height='{H - 2 * MARGIN}' "
            f"fill='none' stroke='#111' stroke-width='1.5'/>"
            f"<line x1='{MARGIN}' y1='{y}' x2='{W - MARGIN}' y2='{y}' stroke='#111' stroke-width='1.5'/>"
            + text(MARGIN + 14, y + 26, doc, 15, weight="bold")
            + text(MARGIN + 14, y + 49, title, 13)
            + text(MARGIN + 600, y + 26, note, 10, fill="#b91c1c")
            + legend
            + text(W - MARGIN - 14, y + 26, f"Sheet {page} of {pages}", 13, anchor="end", weight="bold")
            + text(W - MARGIN - 14, y + 49, "Block level: function-named pins, not package pins", 10,
                   fill="#555", anchor="end"))


def svg(body: str) -> str:
    return (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {W} {H}' width='{W}' height='{H}'>"
            f"<rect width='{W}' height='{H}' fill='#fff'/>{body}</svg>")


def render(d: dict, doc: str, note: str) -> list[str]:
    comps, nets, barriers = d["components"], d["nets"], d.get("barriers", {})
    order = [r for refs in d["sheets"].values() for r in refs]
    rank = {r: i for i, r in enumerate(order)}
    sheet_of = {r: i + 1 for i, refs in enumerate(d["sheets"].values()) for r in refs}
    pin_net, net_by_name = {}, {}
    pins: dict[str, list[str]] = defaultdict(list)
    for net in nets:
        net_by_name[net["name"]] = net
        for node in net["nodes"]:
            ref, pin = node.split(".", 1)
            pin_net[node] = net
            pins[ref].append(pin)

    def side(ref: str, pin: str) -> str:
        net = pin_net[f"{ref}.{pin}"]
        if net.get("source") == f"{ref}.{pin}":
            return "R"
        if net["name"] in RAILS or net.get("source"):
            return "L"
        others = [rank[n.split(".", 1)[0]] for n in net["nodes"] if n.split(".", 1)[0] != ref]
        return "L" if others and min(others) < rank[ref] else "R"

    def box_height(ref: str) -> int:
        l = sum(side(ref, p) == "L" for p in pins[ref])
        return HEAD + max(l, len(pins[ref]) - l, 1) * PITCH + 14

    def draw_box(ref: str, x: float, y: float) -> str:
        c = comps[ref]
        h = box_height(ref)
        multi = isinstance(c["domain"], list)
        stroke = "#111" if not multi else "#7c3aed"
        out = [f"<rect x='{x}' y='{y}' width='{BOX_W}' height='{h}' fill='#fafafa' stroke='{stroke}' "
               f"stroke-width='{2 if multi else 1.3}' {'stroke-dasharray=\"7 4\"' if multi else ''}/>",
               text(x + 8, y + 17, ref, 13, weight="bold")]
        for i, line in enumerate(wrap(c["part"], 30)[:2]):
            out.append(text(x + 8, y + 30 + i * 11, line, 9, fill="#444"))
        if ref in barriers:
            out.append(text(x + BOX_W - 8, y + 17, "BARRIER", 9, fill="#7c3aed", anchor="end", weight="bold"))
        rows = {"L": 0, "R": 0}
        for pin in pins[ref]:
            s = side(ref, pin)
            py = y + HEAD + rows[s] * PITCH + 12
            rows[s] += 1
            net = pin_net[f"{ref}.{pin}"]
            col = COLOR[net["domain"]]
            others = sorted({sheet_of[n.split(".", 1)[0]] for n in net["nodes"]} - {sheet_of[ref]})
            tag = (" >" + ",".join(map(str, others))) if others else ""
            label = net["name"] + tag
            if s == "L":
                out.append(f"<line x1='{x - STUB}' y1='{py}' x2='{x}' y2='{py}' stroke='{col}' stroke-width='1.6'/>")
                out.append(f"<circle cx='{x - STUB}' cy='{py}' r='2.6' fill='{col}'/>")
                out.append(text(x - STUB - 6, py + 4, label, 10, fill=col, anchor="end"))
                out.append(text(x + 6, py + 4, pin[:20], 9.5))
            else:
                out.append(f"<line x1='{x + BOX_W}' y1='{py}' x2='{x + BOX_W + STUB}' y2='{py}' stroke='{col}' stroke-width='1.6'/>")
                out.append(f"<circle cx='{x + BOX_W + STUB}' cy='{py}' r='2.6' fill='{col}'/>")
                out.append(text(x + BOX_W + STUB + 6, py + 4, label, 10, fill=col))
                out.append(text(x + BOX_W - 6, py + 4, pin[:20], 9.5, anchor="end"))
        return "".join(out)

    # ---- paginate ----------------------------------------------------------
    usable = H - 2 * MARGIN - TITLE_H - 24
    ncols = (W - 2 * MARGIN) // COL_W
    x0 = MARGIN + (W - 2 * MARGIN - ncols * COL_W) / 2 + (COL_W - BOX_W) / 2
    layouts = []                                  # (title, [(ref, x, y)])
    for title, refs in d["sheets"].items():
        page, col, y = [], 0, MARGIN + 18
        part = 1
        for ref in refs:
            h = box_height(ref)
            if y + h > MARGIN + 18 + usable and y > MARGIN + 18:
                col, y = col + 1, MARGIN + 18
                if col == ncols:
                    layouts.append((f"{title} ({part})", page))
                    page, col, part = [], 0, part + 1
            page.append((ref, x0 + col * COL_W, y))
            y += h + 22
        layouts.append((title if part == 1 else f"{title} ({part})", page))

    rows = [(n["name"], n["domain"], ", ".join(n["nodes"])) for n in nets]
    per = 44
    index_pages = [rows[i:i + per] for i in range(0, len(rows), per)]
    total = len(layouts) + len(index_pages)
    out = []
    for i, (title, page) in enumerate(layouts, 1):
        body = "".join(draw_box(ref, x, y) for ref, x, y in page)
        out.append(svg(body + frame(title, doc, i, total, note)))
    for j, chunk in enumerate(index_pages, 1):
        body = [text(MARGIN + 20, MARGIN + 30, "Net", 11, weight="bold"),
                text(MARGIN + 230, MARGIN + 30, "Domain", 11, weight="bold"),
                text(MARGIN + 310, MARGIN + 30, "Nodes", 11, weight="bold")]
        for k, (name, dom, nodes) in enumerate(chunk):
            y = MARGIN + 52 + k * 21
            body.append(text(MARGIN + 20, y, name, 10.5, fill=COLOR[dom], weight="bold"))
            body.append(text(MARGIN + 230, y, dom, 10.5, fill=COLOR[dom]))
            body.append(text(MARGIN + 310, y, nodes if len(nodes) < 168 else nodes[:165] + "...", 10))
        out.append(svg("".join(body) + frame(f"Net index ({j})", doc, len(layouts) + j, total, note)))
    return out


def main() -> None:
    src, stem = Path(sys.argv[1]), Path(sys.argv[2])
    d = load(src)
    doc = d.get("title") or stem.name
    note = d.get("status") or "Pre-hardware. Not built, not ERC-checked, not verified."
    pages = render(d, doc, note)
    stem.parent.mkdir(parents=True, exist_ok=True)
    for old in stem.parent.glob(stem.name + "-p*.svg"):
        old.unlink()
    for i, p in enumerate(pages, 1):
        Path(f"{stem}-p{i:02d}.svg").write_text(p)
    html = stem.with_suffix(".html")
    html.write_text("<!doctype html><meta charset='utf-8'><style>@page{size:420mm 297mm;margin:0}"
                    "body{margin:0}svg{display:block;width:420mm;height:297mm;page-break-after:always}"
                    "</style>" + "".join(pages))
    chrome = next((c for c in ("google-chrome", "chromium", "chromium-browser") if shutil.which(c)), None)
    if chrome:
        subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={stem.with_suffix('.pdf')}", html.resolve().as_uri()],
                       check=True, capture_output=True)
    html.unlink()
    print(f"{src.name}: {len(d['components'])} parts, {len(d['nets'])} nets, {len(pages)} pages -> {stem}"
          + (".pdf" if chrome else "-pNN.svg (no Chrome: PDF skipped)"))


if __name__ == "__main__":
    main()
