#!/usr/bin/env python3
"""Check and draw the board floorplan (hardware/pcb/floorplan.yaml).

Checks: parts inside the outline, no overlaps on a side (through-hole parts
block both sides), height limits per side and band, isolation spacing between
electrical domains, mounting-hole keep-outs, and that every netlist part is
placed.  Also lists the nets that cross between the two boards, which sets
the size of the board-to-board cables.

Writes hardware/pcb/floorplan.pdf (+ SVG pages) and hardware/pcb/floorplan_report.md.
Exit status is non-zero on any violation.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from html import escape
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hardware/pcb"
COLOR = {"SYS": "#1d4ed8", "LINE": "#b45309", "POE": "#b91c1c", "MIX": "#7c3aed", "NONE": "#555"}
S = 9.0  # px per mm


def load():
    fp = yaml.safe_load((OUT / "floorplan.yaml").read_text())
    nl = yaml.safe_load((ROOT / "hardware/netlist/netscope-x1.yaml").read_text())
    return fp, nl


def parts_of(board: dict) -> list[dict]:
    out = []
    for row in board["place"]:
        ref, side, x, y, w, h, z, *flags = row
        out.append(dict(ref=ref, side=side, x=x, y=y, w=w, h=h, z=z, flags=set(flags)))
    return out


def rect(p):
    return p["x"] - p["w"] / 2, p["y"] - p["h"] / 2, p["x"] + p["w"] / 2, p["y"] + p["h"] / 2


def gap(a, b) -> float:
    ax0, ay0, ax1, ay1 = rect(a)
    bx0, by0, bx1, by1 = rect(b)
    dx = max(bx0 - ax1, ax0 - bx1, 0.0)
    dy = max(by0 - ay1, ay0 - by1, 0.0)
    if dx == 0 and dy == 0:
        return -min(ax1 - bx0, bx1 - ax0, ay1 - by0, by1 - ay0)   # overlap depth (negative)
    return (dx * dx + dy * dy) ** 0.5


def check(fp, nl):
    errs, notes = [], []
    comps, barriers = nl["components"], nl.get("barriers", {})
    R = fp["rules"]

    def dom(ref):
        if ref not in comps:
            return None
        d = comps[ref]["domain"]
        return "MIX" if isinstance(d, list) else d

    board_of, seen = {}, set()
    for bname, b in fp["boards"].items():
        bw, bh = b["size"]
        ps = parts_of(b)
        holes = [p for p in ps if "hole" in p["flags"]]
        real = [p for p in ps if "hole" not in p["flags"]]
        for p in real:
            if "extra" not in p["flags"]:
                if p["ref"] not in comps:
                    errs.append(f"{bname}: {p['ref']} is not in the netlist (mark it extra)")
                seen.add(p["ref"])
                board_of.setdefault(p["ref"], bname)
            x0, y0, x1, y1 = rect(p)
            m = R["edge_margin"]
            lo_x, hi_x = -bw / 2, bw / 2
            for tx0, ty0, tx1, ty1 in b.get("tabs", []):   # a part wholly within a tab's Y span may use it
                if y0 >= ty0 and y1 <= ty1:
                    lo_x, hi_x = min(lo_x, tx0), max(hi_x, tx1)
            if "over" not in p["flags"] and (x0 < lo_x + m or x1 > hi_x - m
                                             or y0 < -bh / 2 + m or y1 > bh / 2 - m):
                errs.append(f"{bname}: {p['ref']} is outside the board outline / edge margin")
            sides = "FB" if "tht" in p["flags"] else p["side"]
            for s in sides:
                if s != p["side"] and "tht" in p["flags"]:
                    continue  # the far side only carries pins
                lim = [l for lo, hi, l in b["limits"][s] if lo <= p["y"] <= hi]
                bands = [l for lo, hi, l in b["limits"][s] if y0 < hi and y1 > lo]
                limit = min(bands) if bands else None
                if limit is not None and p["z"] > limit + 1e-9 and p["z"] > 0:
                    errs.append(f"{bname}: {p['ref']} is {p['z']} mm tall on side {s}; "
                                f"limit there is {limit} mm")
            for h in holes:
                hx0, hy0 = h["x"] - R["hole_keepout"], h["y"] - R["hole_keepout"]
                hx1, hy1 = h["x"] + R["hole_keepout"], h["y"] + R["hole_keepout"]
                if x0 < hx1 and x1 > hx0 and y0 < hy1 and y1 > hy0:
                    errs.append(f"{bname}: {p['ref']} is inside the keep-out of hole {h['ref']}")
        for i, a in enumerate(real):
            for c in real[i + 1:]:
                if a["ref"] == c["ref"]:
                    continue
                same_side = a["side"] == c["side"] or "tht" in a["flags"] or "tht" in c["flags"]
                g = gap(a, c)
                if same_side and g < R["clearance"]:
                    errs.append(f"{bname}: {a['ref']} and {c['ref']} overlap or are closer than "
                                f"{R['clearance']} mm ({g:.2f})")
                da, dc = dom(a["ref"]), dom(c["ref"])
                if da and dc and da != dc and "MIX" not in (da, dc) and g < R["isolation"]:
                    where = "same side" if a["side"] == c["side"] else "opposite sides"
                    errs.append(f"{bname}: {a['ref']} ({da}) and {c['ref']} ({dc}) are {g:.2f} mm "
                                f"apart ({where}); isolation rule is {R['isolation']} mm")
        used = sum(p["w"] * p["h"] for p in real if "tht" not in p["flags"] or p["z"] > 0)
        area = bw * bh + sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in b.get("tabs", []))
        notes.append(f"{bname}: {bw} x {bh} mm = {area / 100:.1f} cm2 with tabs; placed part area "
                     f"{used / 100:.1f} cm2 = {100 * used / (2 * bw * bh):.0f}% of both sides "
                     f"(before passives and routing)")
    for ref in comps:
        if ref not in seen:
            errs.append(f"{ref} ({comps[ref]['part']}) is in the netlist but not placed")
    for ref in barriers:
        pass
    cross = []
    for net in nl["nets"]:
        boards = {board_of.get(n.split('.', 1)[0]) for n in net["nodes"]} - {None}
        if len(boards) > 1:
            cross.append(net["name"])
    return errs, notes, cross, board_of


def draw(fp, nl) -> list[str]:
    comps = nl["components"]
    pages = []
    for bname, b in fp["boards"].items():
        bw, bh = b["size"]
        ps = parts_of(b)
        for side, label in (("F", "FRONT (display side)"), ("B", "BACK (seen through the board)")):
            W, H = bw * S + 520, bh * S + 260
            ox, oy = 60 + bw * S / 2, 150 + bh * S / 2
            o = [f"<rect width='{W}' height='{H}' fill='#fff'/>",
                 f"<text x='60' y='34' font-size='20' font-weight='bold' font-family='sans-serif'>"
                 f"{escape(b['title'])} - {label}</text>",
                 f"<text x='60' y='56' font-size='12' fill='#b91c1c' font-family='sans-serif'>"
                 f"Floorplan only: not routed, approximate envelopes, small passives not placed.</text>"]
            for lo, hi, lim in b["limits"][side]:
                if lim <= 1.0:
                    o.append(f"<rect x='{ox - bw * S / 2}' y='{oy - hi * S}' width='{bw * S}' "
                             f"height='{(hi - lo) * S}' fill='#fee2e2'/>"
                             f"<text x='{ox}' y='{oy - (lo + hi) / 2 * S + 4}' font-size='11' "
                             f"text-anchor='middle' fill='#991b1b' font-family='sans-serif'>"
                             f"battery cells directly behind: parts under 1 mm only</text>")
            o.append(f"<rect x='{ox - bw * S / 2}' y='{oy - bh * S / 2}' width='{bw * S}' height='{bh * S}' "
                     f"rx='{2 * S}' fill='none' stroke='#14532d' stroke-width='3'/>")
            for tx0, ty0, tx1, ty1 in b.get("tabs", []):
                o.append(f"<rect x='{ox + tx0 * S}' y='{oy - ty1 * S}' width='{(tx1 - tx0) * S}' "
                         f"height='{(ty1 - ty0) * S}' fill='#fff' stroke='#14532d' stroke-width='3'/>")
            legend = []
            for p in ps:
                if "hole" in p["flags"]:
                    o.append(f"<circle cx='{ox + p['x'] * S}' cy='{oy - p['y'] * S}' r='{1.35 * S}' "
                             f"fill='#fff' stroke='#111' stroke-width='2'/>"
                             f"<circle cx='{ox + p['x'] * S}' cy='{oy - p['y'] * S}' r='{2.9 * S}' "
                             f"fill='none' stroke='#999' stroke-dasharray='4 3'/>")
                    continue
                other = p["side"] != side
                if other and "tht" not in p["flags"]:
                    continue
                d = comps.get(p["ref"], {}).get("domain", "NONE")
                col = COLOR["MIX" if isinstance(d, list) else d]
                x, y = ox + (p["x"] - p["w"] / 2) * S, oy - (p["y"] + p["h"] / 2) * S
                pins = other or p["z"] == 0 and "tht" in p["flags"]
                o.append(f"<rect x='{x:.1f}' y='{y:.1f}' width='{p['w'] * S:.1f}' height='{p['h'] * S:.1f}' "
                         f"fill='{col}' fill-opacity='{0.08 if pins else 0.22}' stroke='{col}' "
                         f"stroke-width='1.6' {'stroke-dasharray=\"5 3\"' if pins else ''}/>")
                fs = 12 if min(p["w"], p["h"]) * S > 30 else 9
                txt = p["ref"] + (" pins" if pins else "")
                if p["w"] * S > len(txt) * fs * 0.62 and p["h"] * S > fs:
                    o.append(f"<text x='{ox + p['x'] * S:.1f}' y='{oy - p['y'] * S + fs / 3:.1f}' font-size='{fs}' "
                             f"text-anchor='middle' font-family='monospace' fill='#111'>{txt}</text>")
                if not pins and p["ref"] not in [l[0] for l in legend]:
                    legend.append((p["ref"], comps.get(p["ref"], {}).get("part", "(not a netlist part)"),
                                   p["z"], col))
            lx = 60 + bw * S + 30
            o.append(f"<text x='{lx}' y='88' font-size='12' font-weight='bold' font-family='sans-serif'>"
                     f"Parts on this side (height mm)</text>")
            for i, (ref, part, z, col) in enumerate(sorted(legend)):
                yy = 108 + i * 15
                if yy > H - 60:
                    break
                o.append(f"<rect x='{lx}' y='{yy - 9}' width='9' height='9' fill='{col}'/>"
                         f"<text x='{lx + 15}' y='{yy}' font-size='10.5' font-family='monospace'>"
                         f"{ref:<6}{z:>5}  {escape(part[:40])}</text>")
            o.append(f"<text x='60' y='{H - 60}' font-size='11' font-family='sans-serif'>"
                     f"Blue system side, amber cable conductors, red network-powered, purple isolation barrier. "
                     f"Dashed = through-hole pins. Scale {S:.0f} px/mm.</text>")
            o.append(f"<line x1='60' y1='{H - 40}' x2='{60 + 10 * S}' y2='{H - 40}' stroke='#111' stroke-width='3'/>"
                     f"<text x='{60 + 10 * S + 8}' y='{H - 36}' font-size='11' font-family='sans-serif'>10 mm</text>")
            pages.append(f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {W} {H}' "
                         f"width='{W}' height='{H}'>{''.join(o)}</svg>")
    return pages


def main() -> int:
    fp, nl = load()
    errs, notes, cross, board_of = check(fp, nl)
    rep = ["# Floorplan report", "", "Generated by `tools/render_floorplan.py`. Geometry checks on "
           "approximate part envelopes; not a layout review.", ""]
    rep += [f"- {n}" for n in notes]
    rep += ["", f"## Nets crossing between the boards ({len(cross)})", "",
            ", ".join(f"`{c}`" for c in cross), "",
            "These set the board-to-board cables (J50 signal, J51 power).", "",
            "## Violations", ""]
    rep += [f"- {e}" for e in errs] or ["None."]
    (OUT / "floorplan_report.md").write_text("\n".join(rep) + "\n")
    pages = draw(fp, nl)
    for old in OUT.glob("floorplan-p*.svg"):
        old.unlink()
    for i, p in enumerate(pages, 1):
        (OUT / f"floorplan-p{i}.svg").write_text(p)
    chrome = next((c for c in ("google-chrome", "chromium", "chromium-browser") if shutil.which(c)), None)
    if chrome:
        html = OUT / "floorplan.html"
        html.write_text("<!doctype html><meta charset='utf-8'><style>@page{size:420mm 297mm;margin:8mm}"
                        "body{margin:0}svg{display:block;max-width:100%;max-height:280mm;height:auto;"
                        "page-break-after:always}</style>" + "".join(pages))
        subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={OUT / 'floorplan.pdf'}", html.as_uri()],
                       check=True, capture_output=True)
        html.unlink()
    print("\n".join(notes))
    print(f"cross-board nets: {len(cross)}")
    print("\n".join("VIOLATION " + e for e in errs) or "floorplan check: passed")
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
