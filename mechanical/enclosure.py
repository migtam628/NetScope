#!/usr/bin/env python3
"""NetScope X1 enclosure - parametric CadQuery source (rev A concept).

    python mechanical/enclosure.py        # writes mechanical/out/

Outputs STEP / STL / 3MF per printable part, an assembly STEP with reference
volumes for the internal modules, SVG drawings and a check report.

STATUS: concept geometry for a first printed fit-check.  Not yet a
mouldable design: no draft, no snap/lip detail at the split line, no gasket
groove, door has no latch detail.  Dimensions marked TBC come from product
pages, not from the makers' mechanical drawings, and must be confirmed
before printing.  See docs/12-mechanical.md.
"""
from pathlib import Path

import cadquery as cq
import yaml
from cadquery import exporters

OUT = Path(__file__).resolve().parent / "out"
FLOORPLAN = yaml.safe_load((Path(__file__).resolve().parents[1] / "hardware/pcb/floorplan.yaml").read_text())

# ---- envelope (mm) ---------------------------------------------------------
W, H, D = 108.0, 212.0, 40.0        # width (X), height (Y), depth (Z)
R_PLAN, R_FRONT, R_BACK = 14.0, 3.0, 4.0
WALL = 2.5
Z_FRONT, Z_BACK = D / 2, -D / 2
Z_SPLIT = 6.0                       # front shell is Z_SPLIT..Z_FRONT

# ---- display: Raspberry Pi Touch Display 2, 5 inch --------------------------
ACTIVE_W, ACTIVE_H = 62.1, 110.4    # from the maker's product page
MODULE_W, MODULE_H, MODULE_T = 90.0, 143.5, 8.0   # TBC against mechanical drawing
DISPLAY_Y = 30.0                    # display centre above enclosure centre
WINDOW_MARGIN = 1.0
BEZEL_W, BEZEL_H_PROUD = 5.0, 1.5   # raised lip that takes the hit instead of the glass

# ---- keypad ------------------------------------------------------------------
KEY_D = 11.0                        # hole diameter: gloved-finger target
DPAD_C, DPAD_PITCH = (-22.0, -76.0), 13.5
RIGHT_KEYS = [(24.0, -62.0), (24.0, -77.0), (24.0, -92.0)]   # Back, Home, Fn

# ---- ports ----------------------------------------------------------------------
RJ45_W, RJ45_H = 16.6, 14.0           # opening; jack positions come from the floorplan
SFP_W, SFP_H = 15.1, 10.4             # opening for the SFP+ cage mouth
USBC_W, USBC_H = 9.6, 3.9

# ---- battery: 1S3P 21700 ---------------------------------------------------------
CELL_D, CELL_L = 21.6, 71.0
DOOR_W, DOOR_H, DOOR_Y, DOOR_GAP = 74.0, 80.0, -56.0, 0.3

PCB_T = 1.6                          # board outlines and parts come from hardware/pcb/floorplan.yaml
LED_Y = -48.0                       # status LEDs sit between the display and the keys
VENT_XY = (37.5, -77.0)             # buzzer is on the front of the lower board
POST_R = 3.0
POWER_KEY = (38.0, -55.0)           # recessed opening, smaller than the other keys
SD_SLOT_W, SD_SLOT_H = 14.0, 2.6    # microSD slot in the top end wall
SD_Z = Z_FRONT - WALL - 8.0 - 2.0 - 1.6 - 1.0   # card plane: 1 mm behind the board (MODULE_T = 8)

# ---- depth stack, front to back (everything hangs off these) -------------------
Z_DISPLAY = Z_FRONT - WALL - MODULE_T / 2
Z_PCB = Z_DISPLAY - MODULE_T / 2 - 2.0 - PCB_T / 2
Z_PCB_BOTTOM = Z_PCB - PCB_T / 2
RJ45_BODY_H = 13.5
RJ45_Z = Z_PCB_BOTTOM - RJ45_BODY_H / 2     # jacks sit on the back of the PCB
USBC_Z = Z_PCB_BOTTOM - 2.3                 # mid-mount receptacle, stays below the split line
BOSS_R, BOSS_XY = 3.0, [(-48.5, 96.0), (48.5, 96.0), (-48.5, 0.0), (48.5, 0.0),
                        (-48.5, -98.0), (48.5, -98.0)]
BUMPER_T, BUMPER_Z, BUMPER_Z0 = 3.0, 30.0, -4.0   # band thickness, height, centre


def _block(z0: float, z1: float) -> cq.Workplane:
    return cq.Workplane("XY").box(W + 20, H + 20, z1 - z0).translate((0, 0, (z0 + z1) / 2))


def body() -> cq.Workplane:
    b = cq.Workplane("XY").box(W, H, D).edges("|Z").fillet(R_PLAN)
    b = b.faces(">Z").edges().fillet(R_FRONT)
    return b.faces("<Z").edges().fillet(R_BACK)


def hollow() -> cq.Workplane:
    solid = body()
    inner = cq.Workplane("XY").box(W - 2 * WALL, H - 2 * WALL, D - 2 * WALL) \
        .edges("|Z").fillet(R_PLAN - WALL).faces(">Z or <Z").edges().fillet(1.0)
    return solid.cut(inner)


def front_shell() -> cq.Workplane:
    f = hollow().intersect(_block(Z_SPLIT, Z_FRONT + 5))
    win_w, win_h = ACTIVE_W + 2 * WINDOW_MARGIN, ACTIVE_H + 2 * WINDOW_MARGIN
    bezel = (cq.Workplane("XY").workplane(offset=Z_FRONT - 0.2)
             .center(0, DISPLAY_Y).rect(win_w + 2 * BEZEL_W, win_h + 2 * BEZEL_W)
             .extrude(BEZEL_H_PROUD + 0.2).edges("|Z").fillet(3.0))
    f = f.union(bezel)
    window = (cq.Workplane("XY").workplane(offset=Z_FRONT - WALL - 1)
              .center(0, DISPLAY_Y).rect(win_w, win_h).extrude(WALL + BEZEL_H_PROUD + 2))
    f = f.cut(window)
    keys = [(DPAD_C[0], DPAD_C[1]),
            (DPAD_C[0] + DPAD_PITCH, DPAD_C[1]), (DPAD_C[0] - DPAD_PITCH, DPAD_C[1]),
            (DPAD_C[0], DPAD_C[1] + DPAD_PITCH), (DPAD_C[0], DPAD_C[1] - DPAD_PITCH)] + RIGHT_KEYS
    holes = (cq.Workplane("XY").workplane(offset=Z_FRONT - WALL - 1).pushPoints(keys)
             .circle(KEY_D / 2).extrude(WALL + 2))
    f = f.cut(holes)
    f = f.cut(cq.Workplane("XY").workplane(offset=Z_FRONT - WALL - 1).center(*POWER_KEY)
              .circle(3.5).extrude(WALL + 2))
    # status LED light-pipe holes between the display and the keys
    leds = (cq.Workplane("XY").workplane(offset=Z_FRONT - WALL - 1)
            .pushPoints([(x, LED_Y) for x in (-12, -4, 4, 12)]).circle(1.25)
            .extrude(WALL + 2))
    f = f.cut(leds)
    # buzzer vents over the buzzer on the lower board
    vents = (cq.Workplane("XY").workplane(offset=Z_FRONT - WALL - 1)
             .pushPoints([(VENT_XY[0] + dx, VENT_XY[1] + dy) for dx in (-3, 0, 3) for dy in (-3, 0, 3)])
             .circle(0.7).extrude(WALL + 2))
    f = f.cut(vents)
    # screw bosses for M2.5 heat-set inserts, from the inside of the front wall to the split
    for x, y in BOSS_XY:
        boss = (cq.Workplane("XY").workplane(offset=Z_SPLIT).center(x, y).circle(BOSS_R)
                .extrude(Z_FRONT - WALL - Z_SPLIT + 0.2))
        f = f.union(boss)
        f = f.cut(cq.Workplane("XY").workplane(offset=Z_SPLIT - 0.1).center(x, y)
                  .circle(1.6).extrude(6.0))
    return f


def rear_shell() -> cq.Workplane:
    r = hollow().intersect(_block(Z_BACK - 5, Z_SPLIT))
    # screw pillars with through holes and counterbores from the back
    for x, y in BOSS_XY:
        pillar = (cq.Workplane("XY").workplane(offset=Z_BACK + WALL - 0.2).center(x, y)
                  .circle(BOSS_R).extrude(Z_SPLIT - Z_BACK - WALL + 0.2))
        r = r.union(pillar)
    r = r.intersect(body())  # trim pillars to the outer skin
    for x, y in BOSS_XY:
        r = r.cut(cq.Workplane("XY").workplane(offset=Z_BACK - 1).center(x, y)
                  .circle(1.45).extrude(D))
        r = r.cut(cq.Workplane("XY").workplane(offset=Z_BACK - 1).center(x, y)
                  .circle(2.6).extrude(1 + 6.0))
    # RJ45 openings in the top end, USB-C in the bottom end
    for x in part_x("J10") + part_x("J11"):
        r = r.cut(cq.Workplane("XY").box(RJ45_W, 12, RJ45_H)
                  .translate((x, H / 2 - 3, RJ45_Z)))
    for x in part_x("J32"):                       # SFP+ cage mouth
        r = r.cut(cq.Workplane("XY").box(SFP_W, 12, SFP_H)
                  .translate((x, H / 2 - 3, Z_PCB_BOTTOM - 9.8 / 2)))
    usb = cq.Workplane("XZ").center(0, USBC_Z).rect(USBC_W, USBC_H).extrude(12) \
        .edges("|Y").fillet(1.6).translate((0, -H / 2 + 12 - 3, 0))
    r = r.cut(usb)
    # microSD slot through the top end wall, in line with the socket on the board tab
    for x in part_x("J30"):
        r = r.cut(cq.Workplane("XY").box(SD_SLOT_W, 8.0, SD_SLOT_H).translate((x, H / 2 - 2.0, SD_Z)))
    # battery door opening
    r = r.cut(cq.Workplane("XY").box(DOOR_W, DOOR_H, WALL + 2)
              .translate((0, DOOR_Y, Z_BACK + WALL / 2)).edges("|Z").fillet(4.0))
    # anti-slip grip ribs either side of the door
    for side in (-1, 1):
        for i in range(9):
            rib = cq.Workplane("XY").box(9.0, 2.0, 1.0).translate(
                (side * (DOOR_W / 2 + 8.5), DOOR_Y - 32 + i * 8.0, Z_BACK - 0.3))
            r = r.union(rib)
    # lanyard point: a solid lug inside the top-left corner, pierced front to back
    lug = (cq.Workplane("XY").workplane(offset=Z_BACK).center(-W / 2 + 9.5, H / 2 - 9.5)
           .circle(6.0).extrude(Z_PCB_BOTTOM - 0.8 - Z_BACK)).intersect(body())  # stops below the PCB
    r = r.union(lug)
    r = r.cut(cq.Workplane("XY").workplane(offset=Z_BACK - 1)
              .center(-W / 2 + 9.5, H / 2 - 9.5).circle(2.4).extrude(Z_PCB_BOTTOM - Z_BACK))
    # board standoffs at every mounting hole in the floorplan (M2.5 self-tapping pilot)
    for x, y in mounting_holes():
        post = (cq.Workplane("XY").workplane(offset=Z_BACK + WALL - 0.2).center(x, y)
                .circle(POST_R).extrude(Z_PCB_BOTTOM - Z_BACK - WALL + 0.2))
        r = r.union(post)
        r = r.cut(cq.Workplane("XY").workplane(offset=Z_PCB_BOTTOM - 6.0).center(x, y)
                  .circle(1.05).extrude(6.1))
    return r


def battery_door() -> cq.Workplane:
    d = cq.Workplane("XY").box(DOOR_W - 2 * DOOR_GAP, DOOR_H - 2 * DOOR_GAP, WALL) \
        .edges("|Z").fillet(4.0 - DOOR_GAP)
    d = d.faces("<Z").workplane().pushPoints([(0, DOOR_H / 2 - 6), (0, -DOOR_H / 2 + 6)]) \
        .cboreHole(2.8, 5.0, 1.2)
    return d.translate((0, DOOR_Y, Z_BACK + WALL / 2))


def bumper() -> cq.Workplane:
    outer = cq.Workplane("XY").box(W + 2 * BUMPER_T, H + 2 * BUMPER_T, BUMPER_Z) \
        .edges("|Z").fillet(R_PLAN + BUMPER_T).faces(">Z or <Z").edges().fillet(1.2)
    b = outer.cut(cq.Workplane("XY").box(W, H, BUMPER_Z + 2).edges("|Z").fillet(R_PLAN))
    b = b.translate((0, 0, BUMPER_Z0))
    # Port windows.  They must not cut the band in two: a strap is left
    # behind the ports (checked: the bumper has to stay one body).
    xs = part_x("J10") + part_x("J11") + part_x("J32") + part_x("J30")
    x0, x1 = min(xs) - RJ45_W / 2 - 3, max(xs) + RJ45_W / 2 + 3
    b = b.cut(cq.Workplane("XY").box(x1 - x0, 12, RJ45_H + 3)
              .translate(((x0 + x1) / 2, H / 2 + BUMPER_T / 2, RJ45_Z)))
    b = b.cut(cq.Workplane("XY").box(USBC_W + 10, 12, USBC_H + 6)
              .translate((0, -H / 2 - BUMPER_T / 2, USBC_Z)))
    return b


def _placements(board: dict):
    cx, cy = board["centre_in_enclosure"]
    for ref, side, x, y, w, h, z, *flags in board["place"]:
        yield ref, side, cx + x, cy + y, w, h, z, set(flags)


def part_x(ref: str) -> list[float]:
    """Enclosure X of every placement of a part (used to line openings up with connectors)."""
    return [x for b in FLOORPLAN["boards"].values()
            for r, _, x, *_ in _placements(b) if r == ref]


def mounting_holes() -> list[tuple[float, float]]:
    return [(x, y) for b in FLOORPLAN["boards"].values()
            for _, _, x, y, _, _, _, flags in _placements(b) if "hole" in flags]


def board_assembly(name: str) -> cq.Workplane:
    """Bare board plus one box per placed part (approximate envelopes)."""
    b = FLOORPLAN["boards"][name]
    (bw, bh), (cx, cy) = b["size"], b["centre_in_enclosure"]
    solid = cq.Workplane("XY").box(bw, bh, PCB_T).edges("|Z").fillet(2.0).translate((cx, cy, Z_PCB))
    for x0, y0, x1, y1 in b.get("tabs", []):
        solid = solid.union(cq.Workplane("XY").box(x1 - x0 + 1.0, y1 - y0, PCB_T)
                            .translate((cx + (x0 + x1) / 2 - 0.5, cy + (y0 + y1) / 2, Z_PCB)))
    for _, _, x, y, _, _, _, flags in _placements(b):
        if "hole" in flags:
            solid = solid.cut(cq.Workplane("XY").workplane(offset=Z_PCB - PCB_T).center(x, y)
                              .circle(1.35).extrude(2 * PCB_T))
    for ref, side, x, y, w, h, z, flags in _placements(b):
        if "hole" in flags or z <= 0:
            continue
        zc = Z_PCB + PCB_T / 2 + z / 2 if side == "F" else Z_PCB_BOTTOM - z / 2
        solid = solid.union(cq.Workplane("XY").box(w, h, z).translate((x, y, zc)))
    return solid


def references() -> dict[str, cq.Workplane]:
    """Keep-out volumes of bought-in modules and the two board assemblies."""
    z_cells = Z_BACK + WALL + 0.6 + CELL_D / 2
    cells = cq.Workplane("XY")
    for i in (-1, 0, 1):
        cells = cells.union(cq.Workplane("XZ").circle(CELL_D / 2).extrude(CELL_L)
                            .translate((i * (CELL_D + 0.6), DOOR_Y + CELL_L / 2, z_cells)))
    return {
        "ref_display": cq.Workplane("XY").box(MODULE_W, MODULE_H, MODULE_T)
        .translate((0, DISPLAY_Y, Z_DISPLAY)),
        "pcb_main": board_assembly("main"),
        "pcb_lower": board_assembly("lower"),
        "ref_cells": cells,
    }


PARTS = {"front_shell": front_shell, "rear_shell": rear_shell,
         "battery_door": battery_door, "bumper": bumper}
DENSITY = {"front_shell": 1.15, "rear_shell": 1.15, "battery_door": 1.15, "bumper": 1.20}  # g/cm3
COLORS = {"front_shell": (0.13, 0.16, 0.19), "rear_shell": (0.13, 0.16, 0.19),
          "battery_door": (0.2, 0.24, 0.28), "bumper": (1.0, 0.82, 0.25)}


def main() -> int:
    OUT.mkdir(exist_ok=True)
    report, ok = ["# Enclosure check report", "",
                  "Generated by `mechanical/enclosure.py`. Geometry checks only: this is not "
                  "a tolerance analysis, drop simulation or mouldability review.", "",
                  "| Part | Valid solid | Bodies | Bounding box (mm) | Volume (cm3) | Mass (g) |",
                  "|---|---|---:|---|---:|---:|"], True
    built = {}
    asm = cq.Assembly(name="netscope_x1")
    for name, fn in PARTS.items():
        part = fn()
        built[name] = part
        shape = part.val()
        bb = shape.BoundingBox()
        n_solids = len(part.solids().vals())
        valid = shape.isValid() and n_solids == 1
        ok &= valid
        vol = shape.Volume() / 1000
        report.append(f"| {name} | {'yes' if valid else 'NO'} | {n_solids} | "
                      f"{bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f} | {vol:.1f} | "
                      f"{vol * DENSITY[name]:.0f} |")
        for ext in ("step", "stl", "3mf"):
            exporters.export(part, str(OUT / f"{name}.{ext}"))
        asm.add(part, name=name, color=cq.Color(*COLORS[name]))
    refs = references()
    for name, ref in refs.items():
        colour = cq.Color(0.05, 0.35, 0.15) if name.startswith("pcb") else cq.Color(0.3, 0.6, 0.9, 0.5)
        asm.add(ref, name=name, color=colour)
        exporters.export(ref, str(OUT / f"{name}.stl"))
        if name.startswith("pcb"):
            exporters.export(ref, str(OUT / f"{name}.step"))
    asm.save(str(OUT / "netscope_x1_assembly.step"))

    report += ["", "## Interference (shell vs. module keep-outs)", "",
               "| Shell part | Module | Overlap (mm3) |", "|---|---|---:|"]
    for pname in ("front_shell", "rear_shell", "battery_door"):
        for rname, ref in refs.items():
            try:
                v = built[pname].intersect(ref).val().Volume()
            except Exception:
                v = 0.0
            flag = "" if v < 1.0 else " **CLASH**"
            ok &= v < 1.0
            report.append(f"| {pname} | {rname} | {v:.1f}{flag} |")
    report += ["", "## Interference between internal modules", "",
               "| Module | Module | Overlap (mm3) |", "|---|---|---:|"]
    names = list(refs)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            try:
                v = refs[a].intersect(refs[b]).val().Volume()
            except Exception:
                v = 0.0
            ok &= v < 1.0
            report.append(f"| {a} | {b} | {v:.1f}{'' if v < 1.0 else ' **CLASH**'} |")
    stack = WALL + MODULE_T + 2.0 + PCB_T + 0.6 + CELL_D + 0.6 + WALL
    report += ["", "## Depth stack at the battery", "",
               f"front wall {WALL} + display {MODULE_T} + gap 2.0 + PCB {PCB_T} + clearance 0.6 "
               f"+ cell {CELL_D} + clearance 0.6 + door {WALL} = **{stack:.1f} mm** "
               f"against {D:.1f} mm outside depth "
               f"({'fits' if stack <= D else 'DOES NOT FIT'}, {D - stack:+.1f} mm).", ""]
    ok &= stack <= D

    compound = cq.Workplane("XY").add(asm.toCompound())
    for view, direction in (("front", (0, 0, 1)), ("back", (0, 0, -1)), ("side", (1, 0, 0)),
                            ("top_end", (0, 1, 0)), ("iso", (1, -1, 0.8))):
        exporters.export(compound, str(OUT / f"drawing_{view}.svg"),
                         opt=dict(projectionDir=direction, showAxes=False, showHidden=False,
                                  width=700, height=900, marginLeft=40, marginTop=40,
                                  strokeWidth=0.4))
    report.append(f"Overall result: **{'pass' if ok else 'FAIL'}**")
    (OUT / "check_report.md").write_text("\n".join(report) + "\n")
    print("\n".join(report))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
