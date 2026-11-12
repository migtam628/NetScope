"""Small helpers for generating KiCad 9 schematics from scripts.

Reads symbols out of KiCad's installed libraries so a generated schematic
uses the real library symbol (real pin numbers and pin types) and not a
drawing of one.  Atoms keep their original text, so what is read from a
library is written back unchanged.
"""
from __future__ import annotations

import math
import uuid
from pathlib import Path

SYMBOL_DIR = Path("/usr/share/kicad/symbols")
SCH_VERSION, GEN_VERSION = 20250114, "9.0"


def parse(text: str):
    """S-expression to nested lists.  Atoms stay as raw text (strings keep their quotes)."""
    stack, cur, i, n = [], [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "(":
            stack.append(cur)
            cur = []
            i += 1
        elif c == ")":
            done, cur = cur, stack.pop()
            cur.append(done)
            i += 1
        elif c == '"':
            j = i + 1
            while text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            cur.append(text[i:j + 1])
            i = j + 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "()":
                j += 1
            cur.append(text[i:j])
            i = j
    return cur[0]


def dump(node) -> str:
    return "(" + " ".join(dump(c) if isinstance(c, list) else c for c in node) + ")"


def q(s) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def unq(atom: str) -> str:
    if atom.startswith('"'):
        return atom[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return atom


def children(node, key: str):
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == key]


_libs: dict[str, dict[str, list]] = {}


def _library(lib: str) -> dict[str, list]:
    if lib not in _libs:
        tree = parse((SYMBOL_DIR / f"{lib}.kicad_sym").read_text())
        _libs[lib] = {unq(s[1]): s for s in children(tree, "symbol")}
    return _libs[lib]


def load_symbol(lib: str, name: str) -> list:
    """The library symbol, with `extends` flattened, named "lib:name" for embedding."""
    sym = _library(lib)[name]
    parent = children(sym, "extends")
    if parent:
        base_name = unq(parent[0][1])
        base = load_symbol(lib, base_name)
        own_props = {unq(p[1]) for p in children(sym, "property")}
        body = []
        for c in base[2:]:
            if isinstance(c, list) and c[0] == "property":
                if unq(c[1]) in own_props:
                    continue
            elif isinstance(c, list) and c[0] == "symbol":      # unit: rename Parent_1_1 to Child_1_1
                c = [c[0], q(name + unq(c[1])[len(base_name):])] + c[2:]
            body.append(c)
        props = children(sym, "property")
        rest = [c for c in body if not (isinstance(c, list) and c[0] == "property")]
        kept = [c for c in body if isinstance(c, list) and c[0] == "property"]
        return ["symbol", q(f"{lib}:{name}")] + props + kept + rest
    return ["symbol", q(f"{lib}:{name}")] + sym[2:]


def pins(symbol: list) -> dict[str, tuple[float, float]]:
    """Pin number to connection point, in symbol coordinates (Y up)."""
    out = {}
    for unit in children(symbol, "symbol"):
        for pin in children(unit, "pin"):
            at = children(pin, "at")[0]
            out[unq(children(pin, "number")[0][1])] = (float(at[1]), float(at[2]))
    return out


def pin_info(symbol: list) -> dict[str, tuple[float, float, int, str]]:
    """Pin number to (x, y, angle, name) in symbol coordinates.  The angle points from the
    connection point into the symbol body."""
    out = {}
    for unit in children(symbol, "symbol"):
        for pin in children(unit, "pin"):
            at = children(pin, "at")[0]
            out[unq(children(pin, "number")[0][1])] = (float(at[1]), float(at[2]), int(float(at[3])) if len(at) > 3 else 0,
                                                       unq(children(pin, "name")[0][1]))
    return out


def pin_on_sheet(at: tuple[float, float], rotation: int, pin: tuple[float, float]) -> tuple[float, float]:
    """Sheet position (Y down) of a pin for a symbol placed at `at`, rotated counter-clockwise."""
    dx, dy = pin[0], -pin[1]
    a = math.radians(rotation)
    rx = dx * math.cos(a) + dy * math.sin(a)
    ry = -dx * math.sin(a) + dy * math.cos(a)
    return round(at[0] + rx, 4), round(at[1] + ry, 4)


class Sheet:
    """One flat schematic sheet built from library symbols, wires and labels."""

    def __init__(self, project: str, namespace: str, title: str, paper: str = "A4"):
        self.project, self.title, self.paper = project, title, paper
        self.ns = uuid.uuid5(uuid.NAMESPACE_URL, namespace)
        self.uuid = self.uid("root")
        self.lib: dict[str, list] = {}
        self.items: list[str] = []
        self.comments: list[str] = []
        self.netmap: dict[str, dict[str, str]] = {}      # ref -> pin -> net, as given to part()
        self.rev = "A"

    def uid(self, *parts) -> str:
        return str(uuid.uuid5(self.ns, "/".join(str(p) for p in parts)))

    def symbol(self, lib_id: str, ref: str, value: str, at, rotation: int = 0, footprint: str = "",
               fields: dict[str, str] | None = None, dnp: bool = False, ref_at=None, value_at=None):
        lib, name = lib_id.split(":")
        if lib_id not in self.lib:
            self.lib[lib_id] = load_symbol(lib, name)
        sym = self.lib[lib_id]
        x, y = at
        font = "(effects (font (size 1.27 1.27)))"
        hidden = "(effects (font (size 1.27 1.27)) (hide yes))"
        ta = 90 if rotation in (90, 270) else 0      # keeps the text horizontal on a turned symbol
        rx, ry = ref_at or (x, y - 5.08)
        vx, vy = value_at or (x, y + 5.08)
        flag = lambda key: (children(sym, key) or [[key, "yes"]])[0][1]      # noqa: E731  as the library has it
        o = [f"(symbol (lib_id {q(lib_id)}) (at {x} {y} {rotation}) (unit 1) (exclude_from_sim no) "
             f"(in_bom {flag('in_bom')}) (on_board {flag('on_board')}) (dnp {'yes' if dnp else 'no'}) "
             f"(uuid {q(self.uid('sym', ref))})",
             f"(property \"Reference\" {q(ref)} (at {rx} {ry} {ta}) {font})",
             f"(property \"Value\" {q(value)} (at {vx} {vy} {ta}) {font})",
             f"(property \"Footprint\" {q(footprint)} (at {x} {y} 0) {hidden})",
             f"(property \"Datasheet\" \"\" (at {x} {y} 0) {hidden})",
             f"(property \"Description\" \"\" (at {x} {y} 0) {hidden})"]
        for key, val in (fields or {}).items():
            o.append(f"(property {q(key)} {q(val)} (at {x} {y} 0) {hidden})")
        for num in pins(sym):
            o.append(f"(pin {q(num)} (uuid {q(self.uid('pin', ref, num))}))")
        o.append(f"(instances (project {q(self.project)} (path {q('/' + self.uuid)} (reference {q(ref)}) (unit 1)))))")
        self.items.append("\n".join(o))
        return {num: pin_on_sheet(at, rotation, p) for num, p in pins(sym).items()}

    def wire(self, *pts):
        for a, b in zip(pts, pts[1:]):
            self.items.append(f"(wire (pts (xy {a[0]} {a[1]}) (xy {b[0]} {b[1]})) (stroke (width 0) (type default)) "
                              f"(uuid {q(self.uid('wire', a, b))}))")

    def label(self, name: str, at, side: str = "left"):
        ang, just = (180, "right bottom") if side == "left" else (0, "left bottom")
        self.items.append(f"(label {q(name)} (at {at[0]} {at[1]} {ang}) (effects (font (size 1.27 1.27)) "
                          f"(justify {just})) (uuid {q(self.uid('label', name, at))}))")

    def label_at(self, name: str, at, angle: int):
        just = "right bottom" if angle in (180, 270) else "left bottom"
        self.items.append(f"(label {q(name)} (at {at[0]} {at[1]} {angle}) (effects (font (size 1.27 1.27)) "
                          f"(justify {just})) (uuid {q(self.uid('label', name, at))}))")

    def no_connect(self, at):
        self.items.append(f"(no_connect (at {at[0]} {at[1]}) (uuid {q(self.uid('nc', at))}))")

    def part(self, lib_id: str, ref: str, value: str, at, nets: dict, footprint: str = "",
             fields: dict[str, str] | None = None, stub: float = 2.54, **kw):
        """Place an unrotated library symbol and put a net label (or a no-connect flag) on every pin.
        `nets` maps pin number to a net name, or to None for a pin that is deliberately unconnected.
        Pins drawn at the same point (stacked supply pins) share one label and must share one net."""
        self.symbol(lib_id, ref, value, at, 0, footprint, fields, **kw)
        info = pin_info(self.lib[lib_id])
        missing = set(info) - set(nets)
        if missing:
            raise SystemExit(f"{ref}: no net given for pin(s) {sorted(missing)}")
        seen: dict[tuple[float, float], object] = {}
        for num, (px, py, ang, _name) in info.items():
            x, y = round(at[0] + px, 4), round(at[1] - py, 4)
            net = nets[num]
            if (x, y) in seen:
                if seen[(x, y)] != net:
                    raise SystemExit(f"{ref}: stacked pins at one point carry different nets")
                continue
            seen[(x, y)] = net
            if net is None:
                self.no_connect((x, y))
                continue
            dx, dy, lab = {0: (-stub, 0, 180), 180: (stub, 0, 0), 90: (0, stub, 270), 270: (0, -stub, 90)}[ang]
            end = (round(x + dx, 4), round(y + dy, 4))
            self.wire((x, y), end)
            self.label_at(net, end, lab)
        self.netmap.setdefault(ref, {}).update({n: v for n, v in nets.items() if v is not None})

    def text(self, s: str, at, size: float = 1.5):
        self.items.append(f"(text {q(s)} (exclude_from_sim no) (at {at[0]} {at[1]} 0) (effects (font (size {size} "
                          f"{size})) (justify left bottom)) (uuid {q(self.uid('text', s, at))}))")

    def render(self, company: str = "") -> str:
        o = [f"(kicad_sch (version {SCH_VERSION}) (generator \"netscope_gen\") (generator_version {q(GEN_VERSION)}) "
             f"(uuid {q(self.uuid)}) (paper {q(self.paper)})",
             f"(title_block (title {q(self.title)}) (rev {q(self.rev)}) (company {q(company)})"
             + "".join(f" (comment {i + 1} {q(c)})" for i, c in enumerate(self.comments)) + ")",
             "(lib_symbols"]
        o += [dump(s) for s in self.lib.values()]
        o.append(")")
        o += self.items
        o.append("(sheet_instances (path \"/\" (page \"1\")))")
        o.append("(embedded_fonts no))")
        return "\n".join(o) + "\n"
