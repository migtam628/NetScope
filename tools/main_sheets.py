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
from kicad_lib import CUSTOM, Sheet, box_symbol, load_symbol, pin_info  # noqa: E402

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


# ---- power sheet -------------------------------------------------------------------------------
# Parts with no symbol in KiCad's library: pins from the manufacturers' data sheets, read as text
# (TI SLVSCM8 for TPS61088, TI SLVSEC6 for TPS62840, Maxim/ADI MAX17055).  To be compared with the
# PDFs by eye before any board is ordered.
TPS61088 = [("9", "VIN", "power_in", "L"), ("2", "EN", "input", "L"), ("13", "MODE", "input", "L"),
            ("3", "FSW", "passive", "L"), ("10", "SS", "passive", "L"), ("19", "ILIM", "passive", "L"),
            ("18", "COMP", "passive", "L"), ("17", "FB", "input", "L"), ("11", "NC", "passive", "L"),
            ("12", "NC", "passive", "L"), ("20", "AGND", "power_in", "L"),
            ("4", "SW", "passive", "R"), ("5", "SW", "passive", "R"), ("6", "SW", "passive", "R"), ("7", "SW", "passive", "R"),
            ("8", "BOOT", "passive", "R"), ("1", "VCC", "passive", "R"), ("14", "VOUT", "power_out", "R"),
            ("15", "VOUT", "passive", "R"), ("16", "VOUT", "passive", "R"), ("21", "PGND", "power_in", "R")]
TPS62840 = [("2", "VIN", "power_in", "L"), ("4", "EN", "input", "L"), ("3", "MODE", "input", "L"),
            ("6", "STOP", "input", "L"), ("1", "GND", "power_in", "L"),
            ("7", "SW", "passive", "R"), ("8", "VOS", "passive", "R"), ("5", "VSET", "passive", "R")]
MAX17055 = [("10", "BATT", "power_in", "L"), ("9", "THRM", "passive", "L"), ("2", "AIN", "passive", "L"),
            ("7", "REG", "passive", "L"), ("1", "N.C.", "no_connect", "L"),
            ("3", "SCL", "input", "R"), ("4", "SDA", "bidirectional", "R"), ("8", "ALRT", "open_collector", "R"),
            ("5", "CSN", "passive", "R"), ("6", "CSP", "passive", "R"), ("11", "EP", "passive", "R")]
C0805, C1206, R2512 = "Capacitor_SMD:C_0805_2012Metric", "Capacitor_SMD:C_1206_3216Metric", "Resistor_SMD:R_2512_6332Metric"
# Parts on this sheet that have no footprint yet, and why.
NO_FOOTPRINT = {"U51": "KiCad's library has no footprint for the 2 x 2.5 mm 10-pin TDFN; to be drawn from the maker's land pattern",
                "BT1": "battery connection (connector or solder pads) is decided with the pack supplier"}
# Values deliberately left open, and why.
OPEN_VALUES = {"R68": "boost compensation resistor: to be calculated from the data sheet procedure or TI's design tool",
               "C76": "boost compensation capacitor: same"}
REFINES.update({
    "VSYS": ("VSYS",), "VBAT": ("VBAT",), "+5V": ("+5V",), "+3V3": ("+3V3",), "BAT_NTC": ("BAT_NTC",),
    "BAT_NEG": ("GND",),                       # pack negative: joins ground through the 5 mOhm sense resistor
    "BUCK_SW": ("+3V3",),                      # U54 reaches its output rail only through the inductor
    **{n: () for n in ("CHG_SW", "CHG_BTST", "CHG_REGN", "CHG_PMID", "CHG_ILIM", "CHG_STAT", "CHG_QON",
                       "BOOST_SW", "BOOST_BOOT", "BOOST_VCC", "BOOST_FSW", "BOOST_FB", "BOOST_COMP", "BOOST_COMP_RC",
                       "BOOST_ILIM", "BOOST_SS", "AON_SW", "AON_VSET", "BUCK_FB", "FG_REG", "FG_THRM", "FG_AIN")},
})


def _row(s: Sheet, x: float, y: float, parts, pitch: float = 15.24) -> None:
    """A row of two-pin parts: (reference, symbol, value, footprint, net on pin 1, net on pin 2[, fields])."""
    for i, (ref, sym, value, fp, a, b, *more) in enumerate(parts):
        px = round(x + i * pitch, 2)
        s.part(sym, ref, value, (px, y), {"1": a, "2": b}, fp, more[0] if more else None,
               ref_at=(px + 3.81, y - 1.27), value_at=(px + 3.81, y + 1.27))


def build_power(s: Sheet) -> None:
    s.paper = "A2"
    C, R, L = "Device:C", "Device:R", "Device:L"
    box_symbol("netscope-x1:TPS61088RHL", TPS61088, "10 A synchronous boost converter, VQFN-20 (pins from TI SLVSCM8)")
    box_symbol("netscope-x1:TPS62840DLC", TPS62840, "60 nA IQ buck converter, VSON-8 (pins from TI SLVSEC6)")
    box_symbol("netscope-x1:MAX17055ETB", MAX17055, "Fuel gauge, TDFN-10 (pins from the MAX17055 data sheet)")
    s.text("Power: charger and power path, fuel gauge, 5 V boost, two 3.3 V bucks. Sheet captured for real.", (20.32, 20.32), 2.2)
    s.text("UNTESTED. Component values are data-sheet starting points, not a verified design: see hardware/kicad/README.md.",
           (20.32, 26.67))

    # ---- charger and power path ----
    s.text("Charger and power path: BQ25895. USB-C input from the lower board (J51), system rail VSYS, battery VBAT.", (20.32, 43.18))
    s.part("Battery_Management:BQ25895RTW", "U50", "BQ25895RTW", (124.46, 104.14),
           {"1": "USBC_VBUS", "2": "USBC_DP", "3": "USBC_DN", "4": "CHG_STAT", "5": "PWR_I2C_SCL", "6": "PWR_I2C_SDA",
            "7": "CHG_INT", "8": "GND", "9": "GND", "10": "CHG_ILIM", "11": "BAT_NTC", "12": "CHG_QON",
            "13": "VBAT", "14": "VBAT", "15": "VSYS", "16": "VSYS", "17": "GND", "18": "GND", "25": "GND",
            "19": "CHG_SW", "20": "CHG_SW", "21": "CHG_BTST", "22": "CHG_REGN", "23": "CHG_PMID", "24": None},
           "Package_DFN_QFN:Texas_RTW_WQFN-24-1EP_4x4mm_P0.5mm_EP2.7x2.7mm_ThermalVias",
           {"Manufacturer": "Texas Instruments", "MPN": "BQ25895RTWR"}, ref_at=(109.22, 73.66), value_at=(109.22, 76.2))
    _row(s, 27.94, 170.18, [
        ("C60", C, "1u 25V", C0603, "USBC_VBUS", "GND"), ("C61", C, "10u 25V", C0805, "CHG_PMID", "GND"),
        ("C62", C, "10u 25V", C0805, "CHG_PMID", "GND"), ("C63", C, "47n", C0402, "CHG_BTST", "CHG_SW"),
        ("C64", C, "4u7 10V", C0603, "CHG_REGN", "GND"), ("C65", C, "10u 10V", C0805, "VSYS", "GND"),
        ("C66", C, "10u 10V", C0805, "VSYS", "GND"), ("C67", C, "10u 10V", C0805, "VBAT", "GND"),
        ("L50", L, "2u2 >=6A", "Inductor_SMD:L_Coilcraft_XAL5030-XXX", "CHG_SW", "VSYS",
         {"Manufacturer": "Coilcraft", "MPN": "XAL5030-222 (candidate)"}),
        ("R60", R, "130R 1%", R0402, "CHG_ILIM", "GND"), ("R61", R, "5k23 1%", R0402, "CHG_REGN", "BAT_NTC"),
        ("R62", R, "30k1 1%", R0402, "BAT_NTC", "GND")])
    s.part("Connector:TestPoint", "TP50", "STAT", (218.44, 172.72), {"1": "CHG_STAT"}, "TestPoint:TestPoint_Pad_D1.0mm",
           ref_at=(220.98, 168.91), value_at=(220.98, 171.45))
    s.part("Connector:TestPoint", "TP51", "QON", (233.68, 172.72), {"1": "CHG_QON"}, "TestPoint:TestPoint_Pad_D1.0mm",
           ref_at=(236.22, 168.91), value_at=(236.22, 171.45))
    for i, line in enumerate((
            "R60 caps the input current at 3.0 A or less (130R with the part's worst-case gain). Charging is enabled",
            "(CE low) and OTG boost is disabled (OTG low); current and voltage are set over I2C by the coprocessor.",
            "R61/R62 are the data sheet's values for a 103AT thermistor: recalculate for the pack's actual NTC.",
            "D+/D- sit on the USB data pair in parallel with the SoM, without the DSEL switch TI describes: to be bench-tested.")):
        s.text(line, (20.32, 190.5 + i * 3.81), 1.27)

    # ---- fuel gauge and battery ----
    s.text("Battery connection and fuel gauge: MAX17055. Pack negative reaches ground through the 5 mOhm sense resistor.", (300.99, 43.18))
    s.part("Connector_Generic:Conn_01x03", "BT1", "battery: +, NTC, -", (327.66, 86.36),
           {"1": "VBAT", "2": "BAT_NTC", "3": "BAT_NEG"}, "", ref_at=(327.66, 78.74), value_at=(327.66, 93.98))
    s.part("netscope-x1:MAX17055ETB", "U51", "MAX17055ETB+", (424.18, 91.44),
           {"10": "VBAT", "9": "FG_THRM", "2": "FG_AIN", "7": "FG_REG", "1": None, "3": "PWR_I2C_SCL", "4": "PWR_I2C_SDA",
            "8": "CHG_INT", "5": "GND", "6": "BAT_NEG", "11": "BAT_NEG"}, "",
           {"Manufacturer": "Analog Devices", "MPN": "MAX17055ETB+T"}, ref_at=(414.02, 78.74), value_at=(414.02, 81.28))
    _row(s, 309.88, 170.18, [
        ("R63", R, "5m 1% 1W", R2512, "BAT_NEG", "GND"), ("C68", C, "100n", C0402, "VBAT", "BAT_NEG"),
        ("C69", C, "470n", C0402, "FG_REG", "BAT_NEG"), ("R64", R, "10k 1%", R0402, "FG_THRM", "FG_AIN"),
        ("RT51", "Device:Thermistor_NTC", "10k NTC", R0402, "FG_AIN", "BAT_NEG")])
    for i, line in enumerate((
            "5 mOhm, not the data sheet's 10: the boost can draw over 7 A from the pack and 10 mOhm measures only to 5.1 A.",
            "RT51 is a board thermistor for the gauge; the pack's own NTC goes to the charger only (two bias networks",
            "cannot share one thermistor). U51 and BT1 have no footprint yet: see the README.")):
        s.text(line, (300.99, 190.5 + i * 3.81), 1.27)

    # ---- 5 V boost ----
    s.text("5.1 V boost: TPS61088, enabled by the coprocessor (SOM_PWR_EN). Feeds the SoM and everything on +5V.", (20.32, 223.52))
    s.part("netscope-x1:TPS61088RHL", "U52", "TPS61088RHL", (124.46, 276.86),
           {"9": "VSYS", "2": "SOM_PWR_EN", "13": None, "3": "BOOST_FSW", "10": "BOOST_SS", "19": "BOOST_ILIM",
            "18": "BOOST_COMP", "17": "BOOST_FB", "11": "GND", "12": "GND", "20": "GND",
            "4": "BOOST_SW", "5": "BOOST_SW", "6": "BOOST_SW", "7": "BOOST_SW", "8": "BOOST_BOOT", "1": "BOOST_VCC",
            "14": "+5V", "15": "+5V", "16": "+5V", "21": "GND"},
           "Package_DFN_QFN:Texas_VQFN-RHL-20_ThermalVias",
           {"Manufacturer": "Texas Instruments", "MPN": "TPS61088RHLR"}, ref_at=(111.76, 254.0), value_at=(111.76, 256.54))
    _row(s, 27.94, 342.9, [
        ("L1", L, "1u5 >=12A", "Inductor_SMD:L_Coilcraft_XAL7030-152", "VSYS", "BOOST_SW",
         {"Manufacturer": "Coilcraft", "MPN": "XAL7030-152 (candidate)"}),
        ("C70", C, "22u 10V", C1206, "VSYS", "GND"), ("C71", C, "100n", C0402, "VSYS", "GND"),
        ("C72", C, "100n", C0402, "BOOST_BOOT", "BOOST_SW"), ("C73", C, "2u2", C0603, "BOOST_VCC", "GND"),
        ("C74", C, "47n", C0402, "BOOST_SS", "GND"), ("R65", R, "267k 1%", R0402, "BOOST_FSW", "BOOST_SW"),
        ("R66", R, "182k 1%", R0402, "+5V", "BOOST_FB"), ("R67", R, "56k 1%", R0402, "BOOST_FB", "GND"),
        ("R68", R, "TBD", R0402, "BOOST_COMP", "BOOST_COMP_RC"), ("C76", C, "TBD", C0402, "BOOST_COMP_RC", "GND"),
        ("R69", R, "100k 1%", R0402, "BOOST_ILIM", "GND"), ("C77", C, "22u 10V", C1206, "+5V", "GND"),
        ("C78", C, "22u 10V", C1206, "+5V", "GND"), ("C79", C, "22u 10V", C1206, "+5V", "GND")])
    for i, line in enumerate((
            "Output 1.204 V x (1 + 182k/56k) = 5.12 V. R65 targets about 600 kHz, from my reading of the data sheet equation.",
            "R69 = 100k sets the switch current limit near 11.9 A (MODE open: power-save mode at light load).",
            "R68 / C76 (loop compensation) are NOT chosen: the data sheet has no 5 V example. The board must not be built with them open.")):
        s.text(line, (20.32, 363.22 + i * 3.81), 1.27)

    # ---- always-on 3.3 V ----
    s.text("Always-on 3.3 V: TPS62840 from VSYS (coprocessor, key pull-ups)", (300.99, 223.52))
    s.part("netscope-x1:TPS62840DLC", "U53", "TPS62840DLC", (350.52, 266.7),
           {"2": "VSYS", "4": "VSYS", "3": "GND", "6": "GND", "1": "GND", "7": "AON_SW", "8": "+3V3_AON", "5": "AON_VSET"},
           "Package_SON:Texas_VSON-HR-8_1.5x2mm_P0.5mm", {"Manufacturer": "Texas Instruments", "MPN": "TPS62840DLCR"},
           ref_at=(342.9, 254.0), value_at=(342.9, 256.54))
    _row(s, 309.88, 342.9, [
        ("L53", L, "2u2", "Inductor_SMD:L_1008_2520Metric", "AON_SW", "+3V3_AON"), ("C80", C, "4u7 10V", C0603, "VSYS", "GND"),
        ("C81", C, "10u 6V3", C0603, "+3V3_AON", "GND"), ("R70", R, "267k 1%", R0402, "AON_VSET", "GND")])
    s.text("R70 = 267k selects 3.3 V. Always enabled (EN to VSYS).", (300.99, 363.22), 1.27)

    # ---- switched 3.3 V ----
    s.text("3.3 V for the Ethernet and analogue parts: TLV62569 from +5V", (431.8, 223.52))
    s.part("Regulator_Switching:TLV62569DBV", "U54", "TLV62569DBV", (480.06, 266.7),
           {"1": "+5V", "2": "GND", "3": "BUCK_SW", "4": "+5V", "5": "BUCK_FB"}, "Package_TO_SOT_SMD:SOT-23-5",
           {"Manufacturer": "Texas Instruments", "MPN": "TLV62569DBVR"}, ref_at=(472.44, 254.0), value_at=(472.44, 256.54))
    _row(s, 439.42, 342.9, [
        ("L54", L, "2u2 >=3A", "Inductor_SMD:L_1210_3225Metric", "BUCK_SW", "+3V3"), ("C82", C, "10u 10V", C0805, "+5V", "GND"),
        ("C83", C, "22u 6V3", C0805, "+3V3", "GND"), ("R71", R, "453k 1%", R0402, "+3V3", "BUCK_FB"),
        ("R72", R, "100k 1%", R0402, "BUCK_FB", "GND")])
    s.text("0.6 V x (1 + 453k/100k) = 3.32 V. Follows +5V (EN tied to the input).", (431.8, 363.22), 1.27)
    for i, net in enumerate(("VSYS", "VBAT", "+3V3_AON", "+3V3", "USBC_VBUS")):
        x = 462.28 + i * 12.7
        s.part("power:PWR_FLAG", f"#FLG{50 + i}", "PWR_FLAG", (x, 99.06), {"1": net}, ref_at=(x, 93.98), value_at=(x, 91.44))


# sheet title in the block netlist -> (file stem, builder)
CAPTURED = {"Coprocessor, keys, indicators": ("06_coprocessor", build_coprocessor),
            "Power: USB-C, charger, battery, rails": ("07_power", build_power)}
