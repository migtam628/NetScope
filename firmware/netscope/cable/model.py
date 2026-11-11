"""Cable-under-test model used by the simulator and by the analyser tests.

It predicts the DC resistance matrix the wiremap front end would measure for
a given cable, so the analyser can be exercised against known faults without
hardware.  It is a model, not a measurement.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .terminator import CONDUCTOR_OHMS_PER_M, PAIRS, terminator_elements

Matrix = list[list[float | None]]

STRAIGHT = {i: i for i in range(1, 9)}
CROSSOVER_10_100 = {1: 3, 2: 6, 3: 1, 6: 2, 4: 4, 5: 5, 7: 7, 8: 8}
CROSSOVER_GIGABIT = {1: 3, 2: 6, 3: 1, 6: 2, 4: 7, 5: 8, 7: 4, 8: 5}

WINDING_OHMS = 1.0  # DC resistance of a far-end transformer winding


@dataclass
class CableModel:
    length_m: float = 30.0
    wiring: dict[int, int | None] = field(default_factory=lambda: dict(STRAIGHT))
    shorts: list[tuple[int, int]] = field(default_factory=list)
    far_end: str = "terminator"  # terminator | open | equipment
    terminator_id: int = 1
    equipment_pairs: int = 4  # 2 for a 10/100-only device
    split_pairs: tuple[str, str] | None = None  # e.g. ("3-6", "4-5")
    fault_distance_m: float | None = None  # where an open/short is, for TDR


def _groups(shorts: list[tuple[int, int]]) -> dict[int, int]:
    parent = {i: i for i in range(1, 9)}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in shorts:
        parent[find(a)] = find(b)
    return {i: find(i) for i in range(1, 9)}


def simulate_matrix(cable: CableModel) -> Matrix:
    """matrix[a-1][b-1] = ohms with pin a driven positive and pin b as return."""
    grp = _groups(cable.shorts)
    loop = 2 * cable.length_m * CONDUCTOR_OHMS_PER_M
    short_loop = 2 * (cable.fault_distance_m or cable.length_m) * CONDUCTOR_OHMS_PER_M

    def remotes(pin: int) -> set[int]:
        return {cable.wiring[p] for p in range(1, 9)
                if grp[p] == grp[pin] and cable.wiring.get(p) is not None}

    if cable.far_end == "terminator":
        elements = terminator_elements(cable.terminator_id)
    elif cable.far_end == "equipment":
        elements = []
        for a, c in PAIRS[: cable.equipment_pairs]:
            elements += [(a, c, WINDING_OHMS), (c, a, WINDING_OHMS)]
    else:
        elements = []

    m: Matrix = [[None] * 8 for _ in range(8)]
    for a in range(1, 9):
        for b in range(1, 9):
            if a == b:
                continue
            if grp[a] == grp[b]:
                m[a - 1][b - 1] = round(short_loop, 2)
                continue
            ra, rb = remotes(a), remotes(b)
            hits = [r + loop for an, ca, r in elements if an in ra and ca in rb]
            if hits:
                m[a - 1][b - 1] = round(min(hits), 2)
    return m


def simulate_crosstalk(cable: CableModel) -> dict[str, float]:
    """Coupling between pairs in dB (more negative = better isolation)."""
    names = ["1-2", "3-6", "4-5", "7-8"]
    out = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            split = cable.split_pairs and set(cable.split_pairs) == {a, b}
            out[f"{a}/{b}"] = -11.0 if split else -44.0
    return out
