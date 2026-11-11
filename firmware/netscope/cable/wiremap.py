"""Wiremap analysis.

Input is the 8x8 DC resistance matrix from the coprocessor front end
(matrix[a-1][b-1] = ohms with pin a positive, pin b return, None = open) and
optionally a pair-to-pair coupling measurement for split-pair detection.

What DC can and cannot tell you:
  * shorts, opens, reversed pairs, crossed pairs, miswires: yes (with RT-1)
  * which conductor of an open pair is broken: no (both look open)
  * split pairs: no - a split pair is DC-correct.  It needs the AC coupling
    measurement, which is experimental until validated on hardware.
  * anything about performance at frequency (NEXT/RL/IL margins): no.
    This is continuity verification, not certification.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .terminator import PAIR_NAMES, PAIRS, SHORT_MAX_OHMS, identify

# Above this, coupling between two pairs indicates a split pair.
# PROVISIONAL threshold: must be set from measurements on real cable.
SPLIT_COUPLING_DB = -20.0


@dataclass
class WiremapAnalysis:
    far_end: str = "unknown"  # terminator | open | equipment | unknown
    terminator_id: int | None = None
    mapping: dict[int, int | None] = field(default_factory=dict)
    pin_status: dict[int, str] = field(default_factory=dict)
    faults: list[dict] = field(default_factory=list)
    cable_type: str | None = None  # straight | crossover | None
    equipment_pairs: list[str] = field(default_factory=list)
    split_checked: bool = False

    @property
    def ok(self) -> bool:
        return not self.faults

    def to_dict(self) -> dict:
        d = asdict(self)
        d["mapping"] = {str(k): v for k, v in self.mapping.items()}
        d["pin_status"] = {str(k): v for k, v in self.pin_status.items()}
        return d


def _partner(pin: int) -> int:
    for a, b in PAIRS:
        if pin == a:
            return b
        if pin == b:
            return a
    raise ValueError(pin)


def _pair_of(pin: int) -> tuple[int, int]:
    return next(p for p in PAIRS if pin in p)


def analyse(matrix: list[list[float | None]],
            crosstalk_db: dict[str, float] | None = None) -> WiremapAnalysis:
    res = WiremapAnalysis()
    res.mapping = {i: None for i in range(1, 9)}
    res.pin_status = {i: "open" for i in range(1, 9)}

    def m(a: int, b: int) -> float | None:
        return matrix[a - 1][b - 1]

    metallic: list[tuple[int, int]] = []
    diode_links: list[tuple[int, int, float]] = []  # (anode pin, cathode pin, ohms)
    for a in range(1, 9):
        for b in range(a + 1, 9):
            f, r = m(a, b), m(b, a)
            if f is not None and r is not None:
                if max(f, r) <= SHORT_MAX_OHMS:
                    metallic.append((a, b))
                else:
                    res.faults.append({
                        "kind": "resistive", "pins": [a, b],
                        "detail": f"Unexpected two-way resistance between pins {a} and {b} "
                                  f"({f:.0f}/{r:.0f} ohm): moisture, damaged insulation, or a "
                                  f"non-RT-1 termination."})
            elif f is not None:
                diode_links.append((a, b, f))
            elif r is not None:
                diode_links.append((b, a, r))

    # Far-end equipment: low resistance within nominal pairs only (transformer
    # windings), on at least two pairs, and nothing between pairs.
    within = [p for p in metallic if p in PAIRS]
    if metallic and len(within) == len(metallic) and len(within) >= 2 and not diode_links:
        res.far_end = "equipment"
        res.equipment_pairs = [PAIR_NAMES[p] for p in within]
        for a, b in within:
            res.pin_status[a] = res.pin_status[b] = "ok"
        return res

    shorted: set[int] = set()
    for a, b in metallic:
        shorted |= {a, b}
        res.faults.append({"kind": "short", "pins": [a, b],
                           "detail": f"Short between pins {a} and {b}."})
    for p in shorted:
        res.pin_status[p] = "short"

    for anode, cathode, ohms in diode_links:
        hit = identify(ohms)
        if hit is None:
            res.faults.append({
                "kind": "resistive", "pins": [anode, cathode],
                "detail": f"{ohms:.0f} ohm between pins {anode} and {cathode} does not match "
                          f"any RT-1 value."})
            continue
        (r_anode, r_cathode), tid = hit
        if tid is not None:
            res.terminator_id = tid
        res.far_end = "terminator"
        if anode in shorted or cathode in shorted:
            continue  # mapping through a short is ambiguous
        res.mapping[anode] = r_anode
        res.mapping[cathode] = r_cathode

    if res.far_end != "terminator":
        res.far_end = "open" if not metallic else "unknown"
        if not metallic:
            res.pin_status = {i: "unverified" for i in range(1, 9)}
        return res

    # Classify each near-end pair against where its pins landed.
    crossed: dict[tuple[int, int], tuple[int, int]] = {}
    for pair in PAIRS:
        a, b = pair
        if a in shorted or b in shorted:
            continue
        ma, mb = res.mapping[a], res.mapping[b]
        name = PAIR_NAMES[pair]
        if ma is None and mb is None:
            res.faults.append({
                "kind": "open", "pins": [a, b],
                "detail": f"Open on pair {name}: one or both conductors are not continuous "
                          f"(DC cannot tell which; see TDR distance)."})
            continue
        if ma is None or mb is None:
            res.pin_status[a] = res.pin_status[b] = "miswire"
            res.faults.append({
                "kind": "miswire", "pins": [a, b],
                "detail": f"Pair {name} is split across the far end: pin {a}->{ma}, pin {b}->{mb}."})
            continue
        if (ma, mb) == (a, b):
            res.pin_status[a] = res.pin_status[b] = "ok"
        elif (ma, mb) == (b, a):
            res.pin_status[a] = res.pin_status[b] = "reversed"
            res.faults.append({"kind": "reversed", "pins": [a, b],
                               "detail": f"Pair {name} is reversed (pins {a} and {b} swapped)."})
        elif _partner(ma) == mb:
            crossed[pair] = _pair_of(ma)
            res.pin_status[a] = res.pin_status[b] = "crossed"
        else:
            res.pin_status[a] = res.pin_status[b] = "miswire"
            res.faults.append({
                "kind": "miswire", "pins": [a, b],
                "detail": f"Miswire: pin {a} lands on far pin {ma}, pin {b} on far pin {mb}."})

    if crossed:
        swap_23 = crossed.get((1, 2)) == (3, 6) and crossed.get((3, 6)) == (1, 2)
        swap_14 = crossed.get((4, 5)) == (7, 8) and crossed.get((7, 8)) == (4, 5)
        polarity_ok = all(res.mapping[a] == dst[0] for (a, _), dst in crossed.items())
        if polarity_ok and swap_23 and len(crossed) in (2, 4) and (len(crossed) == 2 or swap_14):
            res.cable_type = "crossover"
            for (a, b) in crossed:
                res.pin_status[a] = res.pin_status[b] = "crossover"
        else:
            for (a, b), dst in crossed.items():
                res.faults.append({
                    "kind": "crossed", "pins": [a, b],
                    "detail": f"Pair {PAIR_NAMES[(a, b)]} is crossed to far pair "
                              f"{PAIR_NAMES[dst]}."})
    if not res.faults and not crossed:
        res.cable_type = "straight"

    # Split pairs are only meaningful once DC is clean.
    if crosstalk_db is not None and not res.faults:
        res.split_checked = True
        for key, db in crosstalk_db.items():
            if db > SPLIT_COUPLING_DB:
                a_name, b_name = key.split("/")
                res.faults.append({
                    "kind": "split", "pins": [],
                    "detail": f"Probable split pair between {a_name} and {b_name} "
                              f"(coupling {db:.0f} dB). DC continuity is correct but the "
                              f"conductors are not twisted with their partners."})
                res.cable_type = None
    return res
