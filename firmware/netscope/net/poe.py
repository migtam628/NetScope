"""IEEE 802.3 PoE reference tables (af/at/bt) and interpretation helpers."""
from __future__ import annotations

# class: (PSE output W, PD input W, type, standard)
CLASSES: dict[int, tuple[float, float, int, str]] = {
    0: (15.4, 12.95, 1, "802.3af"),
    1: (4.0, 3.84, 1, "802.3af"),
    2: (7.0, 6.49, 1, "802.3af"),
    3: (15.4, 12.95, 1, "802.3af"),
    4: (30.0, 25.5, 2, "802.3at"),
    5: (45.0, 40.0, 3, "802.3bt"),
    6: (60.0, 51.0, 3, "802.3bt"),
    7: (75.0, 62.0, 4, "802.3bt"),
    8: (90.0, 71.3, 4, "802.3bt"),
}

# Minimum voltage at the PD while powered, by type.
PD_MIN_V = {1: 37.0, 2: 42.5, 3: 42.5, 4: 41.1}
PD_MAX_V = 57.0

# Steady voltage above this with no PD signature presented means a
# passive / non-negotiating injector (a compliant PSE stays <= ~10 V until
# detection succeeds).  20.5 V is the top of the 802.3 classification range.
PASSIVE_THRESHOLD_V = 20.5


def describe_class(cls: int) -> dict:
    pse_w, pd_w, typ, std = CLASSES[cls]
    return dict(poe_class=cls, pse_w=pse_w, pd_w=pd_w, type=typ, standard=std)


def classify_port_voltage(alt_a_v: float, alt_b_v: float, pulsing: bool) -> str:
    """none | pse_probing | passive  (from the pre-connection voltage scan)."""
    peak = max(abs(alt_a_v), abs(alt_b_v))
    if peak >= PASSIVE_THRESHOLD_V and not pulsing:
        return "passive"
    if peak >= 1.5:
        return "pse_probing"
    return "none"
