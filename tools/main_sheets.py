"""Main-board sheets that have been captured for real (library symbols, real pins, footprints).

tools/gen_kicad.py uses a builder from here instead of drawing block symbols
for every sheet named in CAPTURED.  Each builder also declares how its
pin-level nets refine the block netlist, so tools/check_kicad.py can prove the
real sheet still implements the block design.

Captured so far: the coprocessor sheet (U40, its support parts, the SWD pads
and the two cables to the lower board).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_lower import J50 as LOWER_J50, J51 as LOWER_J51  # noqa: E402
from kicad_lib import Sheet, load_symbol, pin_info  # noqa: E402

R0402, C0402, C0603 = "Resistor_SMD:R_0402_1005Metric", "Capacitor_SMD:C_0402_1005Metric", "Capacitor_SMD:C_0603_1608Metric"
MCU = "MCU_ST_STM32G0:STM32G0B1CBUx"

# ---- coprocessor pin plan: pin name -> (net, peripheral function it relies on, or None for plain GPIO) ----
U40_PINS = {
    "PA0": ("WM_ADC_V", "ADC1_IN0"), "PA1": ("WM_ADC_I", "ADC1_IN1"), "PA4": ("XT_ADC", "ADC1_IN4"),
    "PA5": ("CC1_SENSE", "ADC1_IN5"), "PA6": ("CC2_SENSE", "ADC1_IN6"),
    "PA2": ("COPROC_UART_TX_R", "USART2_TX"), "PA3": ("COPROC_UART_RX", "USART2_RX"),
    "PA7": ("BUZZ", "TIM17_CH1"), "PA8": ("SOM_RUN", None),
    "PA9/UCPD1_DBCC1": ("WM_DRV_A0", None), "PA10/UCPD1_DBCC2": ("WM_DRV_A1", None),
    "PA9/PA11": ("WM_DRV_A2", None), "PA10/PA12": ("WM_RET_A0", None),
    "PA13": ("SWDIO", "SYS_SWDIO"), "PA14": ("SWCLK", "SYS_SWCLK"), "PA15": ("KEY_FN", None),
    "PB0": ("LED3", "TIM3_CH3"), "PB1": ("LED4", "TIM3_CH4"), "PB2": ("WM_RET_A1", None), "PB3": ("WM_RET_A2", None),
    "PB4": ("SPARE_PB4", None), "PB5": ("KEY_OK", "SYS_WKUP6"), "PB6": ("KEY_BACK", None), "PB7": ("KEY_HOME", None),
    "PB8": ("PWR_I2C_SCL", "I2C1_SCL"), "PB9": ("PWR_I2C_SDA", "I2C1_SDA"),
    "PB10": ("POE_I2C_SCL", "I2C2_SCL"), "PB11": ("POE_I2C_SDA", "I2C2_SDA"),
    "PB12": ("CHG_INT", None), "PB13": ("POE_ISO_EN", None), "PB14": ("RELAY_TEST_EN", None), "PB15": ("SOM_PWR_EN", None),
    "PC6": ("LED1", "TIM3_CH1"), "PC7": ("LED2", "TIM3_CH2"), "PC13": ("KEY_PWR", "SYS_WKUP2"),
    "PC14": ("WM_MUX_EN", None), "PC15": ("WM_RANGE0", None),
    "PD0": ("KEY_UP", None), "PD1": ("KEY_DOWN", None), "PD2": ("KEY_LEFT", None), "PD3": ("KEY_RIGHT", None),
    "PF0": ("WM_RANGE1", None), "PF1": ("SFP_PWR_EN", None), "PF2": ("COPROC_NRST", None),
    "VBAT": ("+3V3_AON", None), "VDD": ("+3V3_AON", None), "VREF+": ("+3V3_AON", None), "VSS": ("GND", None),
}
# Outputs that switch power or relays: each must be held off by a resistor while the MCU is in reset.
HELD_OFF = ["RELAY_TEST_EN", "POE_ISO_EN", "SOM_PWR_EN", "SFP_PWR_EN", "WM_MUX_EN"]

# ---- how the pin-level nets refine the block netlist: real net -> block net(s); () = local to this sheet ----
REFINES = {
    "+3V3_AON": ("+3V3_AON",), "GND": ("GND",), "USBC_VBUS": ("USBC_VBUS",),
    "WM_ADC_V": ("WM_ADC_V",), "WM_ADC_I": ("WM_ADC_I",), "XT_ADC": ("XT_ADC",), "BUZZ": ("BUZZ",),
    "SOM_RUN": ("SOM_RUN",), "SOM_PWR_EN": ("SOM_PWR_EN",), "CHG_INT": ("CHG_INT",), "POE_ISO_EN": ("POE_ISO_EN",),
    "RELAY_TEST_EN": ("RELAY_TEST_EN",), "SFP_PWR_EN": ("SFP_PWR_EN",),
    "COPROC_UART_TX": ("COPROC_UART",), "COPROC_UART_TX_R": ("COPROC_UART",), "COPROC_UART_RX": ("COPROC_UART",),
    "COPROC_NRST": ("COPROC_BOOT", "COPROC_NRST_DBG"), "COPROC_BOOT0": ("COPROC_BOOT",),
    "SWDIO": ("SWD",), "SWCLK": ("SWD",),
    "PWR_I2C_SCL": ("PWR_I2C",), "PWR_I2C_SDA": ("PWR_I2C",), "POE_I2C_SCL": ("SYS_I2C_POE",), "POE_I2C_SDA": ("SYS_I2C_POE",),
    "USBC_CC1": ("USBC_CC",), "USBC_CC2": ("USBC_CC",), "CC1_SENSE": ("USBC_CC",), "CC2_SENSE": ("USBC_CC",),
    "USBC_DP": ("USBC_D",), "USBC_DN": ("USBC_D",),
    "WM_MUX_EN": ("WM_MUX_SEL",), "WM_RANGE0": ("WM_ISRC_SEL",), "WM_RANGE1": ("WM_ISRC_SEL",),
    **{f"WM_{g}_A{i}": ("WM_MUX_SEL",) for g in ("DRV", "RET") for i in range(3)},
    **{f"KEY_{k}": ("KEYS",) for k in ("UP", "DOWN", "LEFT", "RIGHT", "OK", "BACK", "HOME", "FN", "PWR")},
    **{f"LED{i}": ("STATUS_LEDS",) for i in range(1, 5)},
    "SPARE_PB4": (),
}
# Block nets a real part may touch beyond what the block netlist lists for it, with the reason.
EXTRA_OK = {
    "U40": {"COPROC_NRST_DBG": "one reset pin serves both the SoM and the debug pads"},
    "J40": {"+3V3_AON": "target voltage reference", "GND": "ground", "COPROC_BOOT": "the reset line is shared with the SoM"},
}
# Lower-board cable net names -> main-board net names (same copper, the main board uses the block names).
CABLE_NAME = {"VBUS": "USBC_VBUS", "USB_DP": "USBC_DP", "USB_DN": "USBC_DN", "CC1": "USBC_CC1", "CC2": "USBC_CC2"}


def cable_table(lower: list) -> list:
    """Main-board pin table for a cable.  The main-board connector is on the back, the lower-board one on
    the front, both with the cable leaving towards the gap between the boards: pin n meets pin n, through
    a cable with its contacts on opposite faces at the two ends.  Derived from geometry, not yet from parts."""
    return [CABLE_NAME.get(n, n) if n else None for n in lower]


def by_name(lib_id: str, plan: dict) -> dict:
    """{pin name: net} -> {pin number: net}, insisting that every pin of the symbol is covered."""
    info = pin_info(load_symbol(*lib_id.split(":")))
    missing = {name for _, _, _, name in info.values()} - set(plan)
    if missing:
        raise SystemExit(f"{lib_id}: no decision for pin(s) {sorted(missing)}")
    return {num: plan[name] for num, (_, _, _, name) in info.items()}


def build_coprocessor(s: Sheet) -> None:
    s.paper = "A3"
    s.text("Coprocessor: STM32G0B1CBU6, always powered. Sheet captured for real: library symbols, real pin numbers.",
           (20.32, 20.32), 2.0)
    s.text("UNTESTED. Pin functions are checked against the library's alternate-function list by tools/check_kicad.py.",
           (20.32, 25.4))

    # ---- the MCU ----
    s.part(MCU, "U40", "STM32G0B1CBU6", (139.7, 149.86), by_name(MCU, {k: v[0] for k, v in U40_PINS.items()}),
           "Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm",
           {"Manufacturer": "STMicroelectronics", "MPN": "STM32G0B1CBU6"}, ref_at=(121.92, 96.52), value_at=(121.92, 99.06))
    s.text("No crystal: internal 16 MHz oscillator. PA9/PA10 pins are UCPD dead-battery pins; used here as plain",
           (190.5, 215.9), 1.27)
    s.text("outputs. Boot entry for updates from the SoM (BOOT0 shares PA14) depends on option bits: to be verified.",
           (190.5, 218.44), 1.27)

    # ---- supply decoupling ----
    s.text("Supply and reference decoupling, reset capacitor", (20.32, 38.1))
    x = 27.94
    for ref, value, fp, net in (("C40", "4u7", C0603, "+3V3_AON"), ("C41", "100n", C0402, "+3V3_AON"),
                                ("C42", "100n", C0402, "+3V3_AON"), ("C43", "1u", C0402, "+3V3_AON"),
                                ("C44", "100n", C0402, "COPROC_NRST")):
        s.part("Device:C", ref, value, (x, 55.88), {"1": net, "2": "GND"}, fp, ref_at=(x + 5.08, 54.61), value_at=(x + 5.08, 57.15))
        x += 17.78
    s.part("power:PWR_FLAG", "#FLG01", "PWR_FLAG", (x + 5.08, 60.96), {"1": "GND"}, ref_at=(x + 5.08, 55.88), value_at=(x + 5.08, 53.34))

    # ---- resistors: pull-ups, hold-off pull-downs, series parts ----
    s.text("Bus pull-ups, hold-off pull-downs (power and relay controls stay off while the MCU is in reset), series parts",
           (20.32, 226.06))
    parts = [("R40", "4k7", "+3V3_AON", "PWR_I2C_SCL"), ("R41", "4k7", "+3V3_AON", "PWR_I2C_SDA"),
             ("R42", "4k7", "+3V3_AON", "POE_I2C_SCL"), ("R43", "4k7", "+3V3_AON", "POE_I2C_SDA"),
             ("R44", "10k", "+3V3_AON", "CHG_INT")]
    parts += [(f"R{45 + i}", "100k", net, "GND") for i, net in enumerate(HELD_OFF)]
    parts += [("R50", "10k", "USBC_CC1", "CC1_SENSE"), ("R51", "10k", "USBC_CC2", "CC2_SENSE"),
              ("R52", "1k", "COPROC_UART_TX_R", "COPROC_UART_TX"), ("R53", "1k", "COPROC_BOOT0", "SWCLK")]
    for i, (ref, value, a, b) in enumerate(parts):
        x = 27.94 + i * 13.97
        s.part("Device:R", ref, value, (x, 254.0), {"1": a, "2": b}, R0402, ref_at=(x + 3.81, 252.73), value_at=(x + 3.81, 255.27))
    s.text("R52 limits current into the SoM's pin while the SoM is unpowered; firmware must also float the line then.",
           (20.32, 283.21), 1.27)

    # ---- debug pads and spare ----
    s.text("SWD: Tag-Connect TC2030 pads, no part fitted", (233.68, 232.41))
    s.part("Connector:Conn_ARM_SWD_TagConnect_TC2030", "J40", "TC2030 SWD", (243.84, 256.54),
           {"1": "+3V3_AON", "2": "SWDIO", "3": "COPROC_NRST", "4": "SWCLK", "5": "GND", "6": None},
           "Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical", ref_at=(236.22, 241.3), value_at=(236.22, 243.84))
    s.part("Connector:TestPoint", "TP40", "spare PB4", (289.56, 259.08), {"1": "SPARE_PB4"}, "TestPoint:TestPoint_Pad_D1.0mm",
           ref_at=(292.1, 255.27), value_at=(292.1, 257.81))

    # ---- cables to the lower board ----
    s.text("J50: 30-way signal cable to the lower board", (299.72, 40.64))
    s.part("Connector_Generic_MountingPin:Conn_01x30_MountingPin", "J50", "FH12-30S-0.5SH", (327.66, 91.44),
           {**{str(i + 1): n for i, n in enumerate(cable_table(LOWER_J50))}, "MP": "GND"},
           "Connector_FFC-FPC:Hirose_FH12-30S-0.5SH_1x30-1MP_P0.50mm_Horizontal",
           {"Manufacturer": "Hirose", "MPN": "FH12-30S-0.5SH(55)"}, ref_at=(330.2, 50.8), value_at=(330.2, 53.34))
    s.text("J51: 20-way power cable", (360.68, 40.64))
    s.part("Connector_Generic_MountingPin:Conn_01x20_MountingPin", "J51", "FH12-20S-0.5SH", (388.62, 78.74),
           {**{str(i + 1): n for i, n in enumerate(cable_table(LOWER_J51))}, "MP": "GND"},
           "Connector_FFC-FPC:Hirose_FH12-20S-0.5SH_1x20-1MP_P0.50mm_Horizontal",
           {"Manufacturer": "Hirose", "MPN": "FH12-20S-0.5SH(55)"}, ref_at=(391.16, 50.8), value_at=(391.16, 53.34))
    s.text("Pin n here meets pin n on the lower board (cable with contacts on opposite faces).", (299.72, 147.32), 1.27)
    s.text("That mapping is derived from the placement, not yet confirmed with parts in hand.", (299.72, 149.86), 1.27)


# sheet title in the block netlist -> (file stem, builder)
CAPTURED = {"Coprocessor, keys, indicators": ("06_coprocessor", build_coprocessor)}
