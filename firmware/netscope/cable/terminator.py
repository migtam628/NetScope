"""Electrical model of the RT-1 passive remote terminator.

Each pair is terminated with a series diode + resistor.  The diode's anode is
on the first pin listed, so a forward measurement (first pin positive) reads
the resistor and the reverse measurement reads open.  That gives pair
identity (resistor value) and polarity (diode direction) from DC alone.

The pair 7-8 resistor encodes the terminator ID (1-8) so that several
terminators can be left on different drops and identified from the closet.

These values are the single source of truth: the simulator, the analyser and
hardware/remote-terminator/README.md all use them.
"""
from __future__ import annotations

# (anode pin, cathode pin) -> resistor in ohms
PAIR_RESISTORS: dict[tuple[int, int], float] = {
    (1, 2): 1_000.0,
    (3, 6): 2_200.0,
    (4, 5): 4_700.0,
}
ID_PAIR = (7, 8)
ID_RESISTORS: dict[int, float] = {
    1: 10_000.0, 2: 15_000.0, 3: 22_000.0, 4: 33_000.0,
    5: 47_000.0, 6: 68_000.0, 7: 100_000.0, 8: 150_000.0,
}

PAIRS: list[tuple[int, int]] = [(1, 2), (3, 6), (4, 5), (7, 8)]
PAIR_NAMES = {(1, 2): "1-2", (3, 6): "3-6", (4, 5): "4-5", (7, 8): "7-8"}

# Matching window: 1 % resistors + diode-compensation error + up to ~25 ohm
# of cable loop resistance on a 1 k part.  Adjacent values are >= 1.47x apart
# so 12 % cannot alias.
MATCH_TOLERANCE = 0.12

# Anything at or below this in BOTH directions is a metallic connection
# (short, or a transformer winding at the far end), not a terminator.
SHORT_MAX_OHMS = 100.0

# Worst-case Cat5e conductor resistance, ohms per metre (9.38 ohm / 100 m).
CONDUCTOR_OHMS_PER_M = 0.0938


def terminator_elements(term_id: int) -> list[tuple[int, int, float]]:
    """(anode, cathode, ohms) for every element in terminator `term_id`."""
    if term_id not in ID_RESISTORS:
        raise ValueError(f"terminator id must be 1-8, got {term_id}")
    els = [(a, c, r) for (a, c), r in PAIR_RESISTORS.items()]
    els.append((ID_PAIR[0], ID_PAIR[1], ID_RESISTORS[term_id]))
    return els


def identify(ohms: float) -> tuple[tuple[int, int], int | None] | None:
    """Match a measured resistance to a terminator element.

    Returns ((anode, cathode), terminator_id or None) or None if no match.
    """
    for pair, r in PAIR_RESISTORS.items():
        if abs(ohms - r) <= r * MATCH_TOLERANCE:
            return pair, None
    for tid, r in ID_RESISTORS.items():
        if abs(ohms - r) <= r * MATCH_TOLERANCE:
            return ID_PAIR, tid
    return None
