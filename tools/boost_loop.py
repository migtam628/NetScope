#!/usr/bin/env python3
"""Loop compensation of the 5.1 V boost (U52, TPS61088) on the power sheet: R68 / C76.

    python tools/boost_loop.py

TI's data sheet gives the procedure, but its equations are images that could not be read
here, so this script uses the standard small-signal model of a peak-current-mode boost:

    power stage  Gps(s) = Ro(1-D)/(2 Rsense) * (1 + s/wesr)(1 - s/wrhp) / (1 + s/wp)
                 wp = 2/(Ro Co),  wrhp = Ro (1-D)^2 / L,  wesr = 1/(ESR Co)
    compensation Gc(s)  = GEA * (REA || (R68 + 1/(s C76))) * VREF/VOUT

with the data sheet's GEA = 190 uA/V, internal Rsense = 0.08 Ohm and VREF = 1.204 V, and
REA of about 5 MOhm as stated by TI on its E2E forum.  It prints the starting values from
the usual rules (crossover set at the worst corner, compensation zero on the power-stage
pole) and then sweeps battery voltage, load and effective output capacitance for the
chosen parts.  Light-load rows are optimistic: below roughly 1 A the part runs in PFM
(MODE open), where this model does not apply.

This is a calculation, not a measurement.  Confirm with TI's WEBENCH model and with a
load-step test on the first board.
"""
import numpy as np

GEA, RSENSE, VREF, REA = 190e-6, 0.08, 1.204, 5e6
VOUT, L, ESR = 5.12, 1.5e-6, 0.002          # 5.12 V out, L1 = 1.5 uH, ceramic output bank
FSW = 600e3
R68, C76 = 6190, 10e-9                      # chosen


def loop(vin, iout, co, r5, c5):
    """Crossover frequency (Hz), phase margin (deg), right-half-plane zero (Hz)."""
    d, ro = 1 - vin / VOUT, VOUT / iout
    f = np.logspace(2, 6, 4000)
    s = 2j * np.pi * f
    wp, wrhp, wesr = 2 / (ro * co), ro * (1 - d) ** 2 / L, 1 / (ESR * co)
    gps = ro * (1 - d) / (2 * RSENSE) * (1 + s / wesr) * (1 - s / wrhp) / (1 + s / wp)
    zc = 1 / (1 / REA + 1 / (r5 + 1 / (s * c5)))
    t = gps * GEA * zc * VREF / VOUT
    mag = 20 * np.log10(abs(t))
    i = np.where(np.diff(np.sign(mag)))[0][0]
    return f[i], 180 + np.degrees(np.angle(t[i])), wrhp / (2 * np.pi)


def main() -> None:
    vin, iout, co, fc = 3.0, 4.0, 40e-6, 8e3   # worst corner: flat battery, 4 A, least effective capacitance
    d = 1 - vin / VOUT
    r5 = 2 * np.pi * VOUT * RSENSE * co * fc / ((1 - d) * VREF * GEA)
    print(f"starting values: R68 = {r5:.0f} Ohm, C76 = {(VOUT / iout) * co / (2 * r5) * 1e9:.1f} nF, "
          f"high-frequency capacitor {ESR * co / r5 * 1e12:.0f} pF (left as an unfitted option)")
    print(f"chosen: R68 = {R68} Ohm, C76 = {C76 * 1e9:.0f} nF (zero at {1 / (2 * np.pi * R68 * C76) / 1e3:.2f} kHz; "
          f"more phase margin at large output capacitance)")
    print(" Vin   Iout  Co uF   fc kHz   PM deg   fRHPZ kHz   fc/fRHPZ")
    rows = []
    for v in (3.0, 3.7, 4.2):
        for i in (0.3, 2.0, 4.0):
            for c in (40e-6, 70e-6, 110e-6):
                f_c, pm, frhp = loop(v, i, c, R68, C76)
                rows.append((f_c, pm, f_c / frhp))
                print(f" {v:.1f}  {i:4.1f}  {c * 1e6:5.0f}  {f_c / 1e3:7.2f}  {pm:7.1f}  {frhp / 1e3:10.1f}  {f_c / frhp:8.2f}")
    print(f"worst phase margin {min(r[1] for r in rows):.0f} deg (target > 45); highest crossover "
          f"{max(r[0] for r in rows) / 1e3:.1f} kHz (limit fsw/10 = {FSW / 10e3:.0f} kHz); "
          f"worst fc/fRHPZ {max(r[2] for r in rows):.2f} (limit 0.2)")


if __name__ == "__main__":
    main()
