"""Main-board sheets that have been captured for real (library symbols, real pins, footprints).

tools/gen_kicad.py uses a builder from here instead of drawing block symbols
for every sheet named in CAPTURED.  Each builder also declares how its
pin-level nets refine the block netlist, so tools/check_kicad.py can prove the
real sheet still implements the block design.

Captured so far: test-port Ethernet (LAN7801, KSZ9131RNX, uplink MagJack),
processor module, coprocessor, power.
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
OPEN_VALUES: dict[str, str] = {}             # R68 / C76 were open until tools/boost_loop.py
REFINES.update({
    "VSYS": ("VSYS",), "VBAT": ("VBAT",), "+5V": ("+5V",), "+3V3": ("+3V3",), "BAT_NTC": ("BAT_NTC",),
    "BAT_NEG": ("GND",),                       # pack negative: joins ground through the 5 mOhm sense resistor
    "BUCK_SW": ("+3V3",),                      # U54 reaches its output rail only through the inductor
    **{n: () for n in ("CHG_SW", "CHG_BTST", "CHG_REGN", "CHG_PMID", "CHG_ILIM", "CHG_STAT", "CHG_QON",
                       "BOOST_SW", "BOOST_BOOT", "BOOST_VCC", "BOOST_FSW", "BOOST_FB", "BOOST_COMP", "BOOST_COMP_RC",
                       "BOOST_ILIM", "BOOST_SS", "AON_SW", "AON_VSET", "BUCK_FB", "FG_REG", "FG_THRM", "FG_AIN")},
})


def _row(s: Sheet, x: float, y: float, parts, pitch: float = 15.24, dnp: bool = False) -> None:
    """A row of two-pin parts: (reference, symbol, value, footprint, net on pin 1, net on pin 2[, fields])."""
    for i, (ref, sym, value, fp, a, b, *more) in enumerate(parts):
        px = round(x + i * pitch, 2)
        s.part(sym, ref, value, (px, y), {"1": a, "2": b}, fp, more[0] if more else None,
               ref_at=(px + 3.81, y - 1.27), value_at=(px + 3.81, y + 1.27), dnp=dnp)


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
        ("R68", R, "6k19 1%", R0402, "BOOST_COMP", "BOOST_COMP_RC"), ("C76", C, "10n", C0402, "BOOST_COMP_RC", "GND"),
        ("R69", R, "100k 1%", R0402, "BOOST_ILIM", "GND"), ("C77", C, "22u 10V", C1206, "+5V", "GND"),
        ("C78", C, "22u 10V", C1206, "+5V", "GND"), ("C79", C, "22u 10V", C1206, "+5V", "GND")])
    s.part(C, "C75", "10p", (256.54, 342.9), {"1": "BOOST_COMP", "2": "GND"}, C0402,
           ref_at=(260.35, 341.63), value_at=(260.35, 344.17), dnp=True)
    for i, line in enumerate((
            "Output 1.204 V x (1 + 182k/56k) = 5.12 V. R65 targets about 600 kHz, from my reading of the data sheet equation.",
            "R69 = 100k sets the switch current limit near 11.9 A (MODE open: power-save mode at light load).",
            "R68 / C76 (loop compensation) from tools/boost_loop.py: current-mode model with the data sheet's GEA and Rsense,",
            "phase margin >= 57 deg over 3.0-4.2 V, 0.3-4 A, 40-110 uF effective output. Calculated, not measured: load-step test.",
            "C75 (DNP): optional high-frequency pole on COMP; the calculation gives about 13 pF, fit only if COMP picks up noise.")):
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


# ---- processor sheet ----------------------------------------------------------------------------
# Compute Module 5 pin names, pins 1-200, from Raspberry Pi's CM5 data sheet (pinout table, read as
# text; about 80 of the pins were cross-checked against two other published pin lists).
CM5_PINS = """GND GND Ethernet_Pair3_P Ethernet_Pair1_P Ethernet_Pair3_N Ethernet_Pair1_N GND GND Ethernet_Pair2_N
Ethernet_Pair0_N Ethernet_Pair2_P Ethernet_Pair0_P GND GND Ethernet_nLED3 Fan_Tacho Ethernet_nLED2 Ethernet_SYNC_OUT
Fan_PWM EEPROM_nWP LED_nACT GND GND GPIO26 GPIO21 GPIO19 GPIO20 GPIO13 GPIO16 GPIO6 GPIO12 GND GND GPIO5 ID_SC ID_SD
GPIO7 GPIO11 GPIO8 GPIO9 GPIO25 GND GND GPIO10 GPIO24 GPIO22 GPIO23 GPIO27 GPIO18 GPIO17 GPIO15 GND GND GPIO4 GPIO14
GPIO3 SD_CLK GPIO2 GND GND SD_DAT3 SD_CMD SD_DAT0 SD_DAT5 GND GND SD_DAT1 SD_DAT4 SD_DAT2 SD_DAT7 GND SD_DAT6
SD_VDD_OVERRIDE GND SD_PWR_ON VBAT 5V GPIO_VREF 5V SCL0 5V SDA0 5V CM5_3V3 5V CM5_3V3 5V CM5_1V8 WL_nDisable CM5_1V8
BT_nDisable PWR_Button nRPIBOOT CC1 LED_nPWR CC2 CAM_GPIO0 GND PMIC_Enable CAM_GPIO1
USB_OTG_ID PCIe_CLK_nREQ USB_N PCIE_nWAKE USB_P PCIE_PWR_EN GND GND PCIe_nRST PCIe_CLK_P VBUS_EN PCIe_CLK_N GND GND
MIPI0_D0_N PCIe_RX_P MIPI0_D0_P PCIe_RX_N GND GND MIPI0_D1_N PCIe_TX_P MIPI0_D1_P PCIe_TX_N GND GND MIPI0_C_N
USB3-0-RX_N MIPI0_C_P USB3-0-RX_P GND GND MIPI0_D2_N USB3-0-DP MIPI0_D2_P USB3-0-DM GND GND MIPI0_D3_N USB3-0-TX_N
MIPI0_D3_P USB3-0-TX_P HDMI1_HOTPLUG GND HDMI1_SDA HDMI1_TX2_P HDMI1_SCL HDMI1_TX2_N HDMI1_CEC GND HDMI0_CEC
HDMI1_TX1_P HDMI0_HOTPLUG HDMI1_TX1_N GND GND USB3-1-RX_N HDMI1_TX0_P USB3-1-RX_P HDMI1_TX0_N GND GND USB3-1-DP
HDMI1_CLK_P USB3-1-DM HDMI1_CLK_N GND GND USB3-1-TX_N HDMI0_TX2_P USB3-1-TX_P HDMI0_TX2_N GND GND MIPI1_D0_N
HDMI0_TX1_P MIPI1_D0_P HDMI0_TX1_N GND GND MIPI1_D1_N HDMI0_TX0_P MIPI1_D1_P HDMI0_TX0_N GND GND MIPI1_C_N
HDMI0_CLK_P MIPI1_C_P HDMI0_CLK_N GND GND MIPI1_D2_N MIPI1_D3_N MIPI1_D2_P MIPI1_D3_P GND GND HDMI0_SDA HDMI0_SCL""".split()
assert len(CM5_PINS) == 200
# What each used module signal is connected to; every signal not listed here is left unconnected on purpose.
M1_NETS = {
    "5V": "+5V", "GND": "GND", "CM5_3V3": "SOM_3V3", "GPIO_VREF": "SOM_3V3", "VBAT": "+3V3_AON",
    **{f"Ethernet_Pair{i}_{p}": f"B_MDI{i}_{p}" for i in range(4) for p in "PN"},
    "Ethernet_nLED2": "B_LED2", "Ethernet_nLED3": "B_LED3",
    "GPIO14": "SOM_UART_DBG_TX", "GPIO15": "SOM_UART_DBG_RX",        # UART0: console
    "GPIO4": "COPROC_UART_RX", "GPIO5": "COPROC_UART_TX",            # UART2: SoM transmits on GPIO4 into the MCU's RX
    "GPIO22": "COPROC_BOOT0", "GPIO23": "COPROC_NRST", "GPIO6": "LAN_NRST",
    "GPIO2": "SFP_SDA", "GPIO3": "SFP_SCL",
    "GPIO16": "SFP_LOS", "GPIO17": "SFP_MOD_ABS", "GPIO26": "SFP_TX_FAULT", "GPIO27": "SFP_TX_DISABLE",
    "nRPIBOOT": "SOM_NRPIBOOT", "SCL0": "TOUCH_SCL", "SDA0": "TOUCH_SDA",
    "USB_P": "USBC_DP", "USB_N": "USBC_DN",
    "PCIe_CLK_nREQ": "PCIE_CLK_NREQ", "PCIE_nWAKE": "PCIE_NWAKE", "PCIE_PWR_EN": "PCIE_PWR_EN", "PCIe_nRST": "PCIE_NRST",
    "PCIe_CLK_P": "PCIE_CLK_P", "PCIe_CLK_N": "PCIE_CLK_N", "PCIe_RX_P": "PCIE_RX_P", "PCIe_RX_N": "PCIE_RX_N",
    "PCIe_TX_P": "PCIE_TX_P", "PCIe_TX_N": "PCIE_TX_N",
    "USB3-0-RX_P": "USB3A_RX_P", "USB3-0-RX_N": "USB3A_RX_N", "USB3-0-TX_P": "USB3A_TX_P", "USB3-0-TX_N": "USB3A_TX_N",
    "USB3-0-DP": "USB3A_DP", "USB3-0-DM": "USB3A_DM", "USB3-1-DP": "USB3B_DP", "USB3-1-DM": "USB3B_DM",
    "MIPI1_D0_P": "DSI_D0_P", "MIPI1_D0_N": "DSI_D0_N", "MIPI1_D1_P": "DSI_D1_P", "MIPI1_D1_N": "DSI_D1_N",
    "MIPI1_C_P": "DSI_CLK_P", "MIPI1_C_N": "DSI_CLK_N",
}
# Display cable, 22-way: the usual Raspberry Pi 22-pin MIPI assignment, two data lanes used.
J1_PINS = ["GND", "DSI_D0_N", "DSI_D0_P", "GND", "DSI_D1_N", "DSI_D1_P", "GND", "DSI_CLK_N", "DSI_CLK_P", "GND",
           None, None, "GND", None, None, "GND", None, None, "GND", "TOUCH_SCL", "TOUCH_SDA", "SOM_3V3"]
NO_FOOTPRINT.update({
    "M1": "two Hirose DF40C-100DS-0.4V receptacles and four M2.5 holes at the spacing in Raspberry Pi's CM5 drawing: to be "
          "taken from their published design files, not re-measured here",
    "J2": "depends on the power lead supplied with the display"})
REFINES.update({
    **{f"B_MDI{i}_{p}": ("B_MDI",) for i in range(4) for p in "PN"}, "B_LED2": ("B_LEDS",), "B_LED3": ("B_LEDS",),
    **{f"USB3A_{n}": ("USB3_1",) for n in ("RX_P", "RX_N", "TX_P", "TX_N", "DP", "DM")},
    "USB3B_DP": ("USB3_2_HS",), "USB3B_DM": ("USB3_2_HS",),
    **{f"PCIE_{n}": ("PCIE",) for n in ("CLK_NREQ", "NWAKE", "PWR_EN", "NRST", "CLK_P", "CLK_N", "RX_P", "RX_N", "TX_P", "TX_N")},
    **{f"DSI_{n}": ("DSI",) for n in ("D0_P", "D0_N", "D1_P", "D1_N", "CLK_P", "CLK_N")},
    "TOUCH_SCL": ("TOUCH_I2C",), "TOUCH_SDA": ("TOUCH_I2C",), "SFP_SCL": ("SFP_I2C",), "SFP_SDA": ("SFP_I2C",),
    "SFP_LOS": ("SFP_STATUS",), "SFP_MOD_ABS": ("SFP_STATUS",), "SFP_TX_FAULT": ("SFP_STATUS",),
    "SFP_TX_DISABLE": ("SFP_TX_DISABLE",),
    "SOM_UART_DBG_TX": ("SOM_UART_DBG",), "SOM_UART_DBG_RX": ("SOM_UART_DBG",), "SOM_NRPIBOOT": ("SOM_NRPIBOOT",),
    "SOM_3V3": ("SOM_RUN",),                   # the module's 3.3 V output: the coprocessor reads it as "SoM is up"
})
EXTRA_OK.update({
    "M1": {"COPROC_NRST_DBG": "one reset line serves the SoM and the debug pads"},
    "J41": {"GND": "ground reference pad for a probe or adapter"},
    "J1": {"SOM_RUN": "the cable's 3.3 V pin is fed from the module's 3.3 V output, the same net the run signal is taken from"},
})


def build_processor(s: Sheet) -> None:
    s.paper = "A1"
    C, R = "Device:C", "Device:R"
    names = [n for n in CM5_PINS]
    table = [(str(i + 1), n, "power_in" if n in ("5V", "GND") else "passive", "L" if i < 100 else "R")
             for i, n in enumerate(names)]
    first_3v3 = names.index("CM5_3V3")
    table[first_3v3] = (table[first_3v3][0], "CM5_3V3", "power_out", "L")
    box_symbol("netscope-x1:RaspberryPi_CM5", table, "Raspberry Pi Compute Module 5, both 100-pin connectors (pins from the CM5 data sheet)")
    unknown = set(M1_NETS) - set(names)
    if unknown:
        raise SystemExit(f"M1_NETS names signals the module does not have: {sorted(unknown)}")
    s.text("Processor: Raspberry Pi Compute Module 5, display cable, debug pads. Sheet captured for real.", (25.4, 25.4), 2.5)
    s.text("UNTESTED. Module pin names are from the CM5 data sheet. Signals with no label are deliberately unused.", (25.4, 33.02), 1.8)
    s.part("netscope-x1:RaspberryPi_CM5", "M1", "CM5 (wireless, eMMC)", (419.1, 302.26),
           {str(i + 1): M1_NETS.get(n) for i, n in enumerate(names)}, "",
           {"Manufacturer": "Raspberry Pi", "MPN": "CM5 (variant per BOM)"}, ref_at=(398.78, 165.1), value_at=(398.78, 168.91))

    s.text("Module supply: bulk and bypass on +5V at the connector; 3.3 V output used as I/O reference and run signal", (25.4, 60.96))
    _row(s, 35.56, 83.82, [
        ("C90", C, "22u 10V", C1206, "+5V", "GND"), ("C91", C, "22u 10V", C1206, "+5V", "GND"),
        ("C92", C, "100n", C0402, "+5V", "GND"), ("C93", C, "100n", C0402, "SOM_3V3", "GND"),
        ("R80", R, "10k", R0402, "SOM_3V3", "SOM_RUN")])
    for i, line in enumerate((
            "R80 lets the always-on coprocessor see the module's 3.3 V without back-feeding it. The SFP I2C bus (GPIO2/3) needs no",
            "pull-ups here: the data sheet gives the module 1.8k pull-ups on both. RTC input (VBAT, 2.5-3.5 V per the data sheet) is",
            "tied to +3V3_AON. GPIO6 resets the USB Ethernet bridge (LAN_NRST). USB_OTG_ID, PWR_Button, PMIC_Enable left open.",
            "UART numbering (UART0 on GPIO14/15, UART2 on GPIO4/5) is from memory of the Pi 5 device tree: verify before layout.")):
        s.text(line, (25.4, 106.68 + i * 4.445), 1.5)

    s.text("J1: display cable, 22-way 0.5 mm, DSI on the module's MIPI1 port with two data lanes", (25.4, 147.32))
    s.part("Connector_Generic_MountingPin:Conn_01x22_MountingPin", "J1", "F32Q 22-way", (63.5, 190.5),
           {**{str(i + 1): n for i, n in enumerate(J1_PINS)}, "MP": "GND"},
           "Connector_FFC-FPC:Amphenol_F32Q-1A7x1-11022_1x22-1MP_P0.5mm_Horizontal",
           {"Manufacturer": "Amphenol", "MPN": "F32Q-1A7H1-11022 (candidate)"}, ref_at=(66.04, 160.02), value_at=(66.04, 162.56))
    for i, line in enumerate((
            "Pin order is the usual Raspberry Pi 22-way MIPI assignment, written from memory: verify against the display's",
            "documentation. Which end is pin 1 and which face the contacts are on depend on the cable. Touch I2C uses SCL0/SDA0,",
            "assumed to match Raspberry Pi's IO board for this port: verify against its schematic.")):
        s.text(line, (25.4, 231.14 + i * 4.445), 1.5)
    s.text("J2: 5 V lead to the display", (139.7, 147.32))
    s.part("Connector_Generic:Conn_01x02", "J2", "display 5 V", (160.02, 165.1), {"1": "+5V", "2": "GND"}, "",
           ref_at=(160.02, 158.75), value_at=(160.02, 172.72))

    s.text("J41: unpopulated 1.27 mm pads: SoM console, boot select, coprocessor link taps", (25.4, 264.16))
    s.part("Connector_Generic:Conn_01x06", "J41", "debug pads", (63.5, 289.56),
           {"1": "GND", "2": "SOM_UART_DBG_TX", "3": "SOM_UART_DBG_RX", "4": "SOM_NRPIBOOT", "5": "COPROC_UART_TX",
            "6": "COPROC_UART_RX"}, "Connector_PinHeader_1.27mm:PinHeader_1x06_P1.27mm_Vertical",
           ref_at=(63.5, 279.4), value_at=(63.5, 302.26))


# ---- test-port Ethernet sheet ---------------------------------------------------------------------
# LAN7801 (USB 3 to RGMII MAC) and KSZ9131RNX (gigabit PHY) have no KiCad symbols: pins from Microchip's
# data sheets (LAN7801 DS00002123, KSZ9131RNX DS00002841), read as text.  Support parts follow Microchip's
# LAN7801 schematic checklist; values the documents do not give are marked as starting values on the sheet.
LAN7801 = [(n, name, t, "L") for n, name, t in (
    ("1", "REF_REXT", "passive"), ("2", "REF_FILT", "passive"), ("49", "USBRBIAS", "passive"), ("52", "XI", "input"),
    ("53", "XO", "output"), ("38", "USB2_DP", "bidirectional"), ("39", "USB2_DM", "bidirectional"),
    ("40", "USB3_TXDP", "output"), ("41", "USB3_TXDM", "output"), ("43", "USB3_RXDP", "input"), ("44", "USB3_RXDM", "input"),
    ("29", "VBUS_DET", "input"), ("47", "RESET_N", "input"), ("46", "TEST", "input"), ("57", "TDI/GPIO7", "input"),
    ("58", "TCK/GPIO8", "input"), ("59", "TMS/GPIO9", "input"), ("60", "TDO/GPIO10", "output"), ("23", "EECS/GPIO0", "output"),
    ("24", "EEDI/GPIO1", "input"), ("25", "EEDO/GPIO2", "output"), ("26", "EECLK/GPIO3", "output"),
    ("35", "GPIO4", "bidirectional"), ("36", "PME_MODE/GPIO5", "bidirectional"), ("45", "PME_N/GPIO6", "bidirectional"),
    ("30", "SUSPEND_N", "output"), ("61", "REFCLK_25/GPIO11", "output"), ("34", "NC", "no_connect"),
    ("37", "VDD12A", "power_in"), ("42", "VDD12A", "power_in"), ("62", "VDD12A", "power_in"), ("65", "VSS", "power_in"))]
LAN7801 += [(n, name, t, "R") for n, name, t in (
    ("4", "TXD3", "output"), ("5", "TXD2", "output"), ("6", "TXD1", "output"), ("8", "TXD0", "output"),
    ("9", "TX_CTL", "output"), ("10", "TXC", "output"), ("12", "RXC", "input"), ("13", "RX_CTL", "input"),
    ("14", "RXD0", "input"), ("15", "RXD1", "input"), ("16", "RXD2", "input"), ("17", "RXD3", "input"),
    ("19", "CLK125", "passive"), ("31", "PHY_INT_N", "input"), ("32", "PHY_RESET_N", "output"), ("33", "DUPLEX", "input"),
    ("55", "MDIO", "bidirectional"), ("56", "MDC", "output"),
    *[(n, "VDDVARIO", "power_in") for n in ("3", "7", "11", "18", "27", "48", "51")],
    ("50", "VDD33A", "power_in"), ("64", "VDD33_REG_IN", "power_in"), ("21", "VDD_SW_IN", "power_in"),
    ("63", "VDD25_REG_OUT", "power_out"), ("20", "VDD12_SW_OUT", "power_out"), ("22", "VDD12_SW_FB", "input"),
    ("28", "VDD12CORE", "power_in"), ("54", "VDD12CORE", "power_in"))]
KSZ9131 = [(n, name, t, "L") for n, name, t in (
    ("2", "TXRXP_A", "bidirectional"), ("3", "TXRXM_A", "bidirectional"), ("5", "TXRXP_B", "bidirectional"),
    ("6", "TXRXM_B", "bidirectional"), ("7", "TXRXP_C", "bidirectional"), ("8", "TXRXM_C", "bidirectional"),
    ("10", "TXRXP_D", "bidirectional"), ("11", "TXRXM_D", "bidirectional"), ("46", "XI", "input"), ("45", "XO", "output"),
    ("48", "ISET", "passive"), ("42", "RESET_N", "input"), ("43", "LDO_O", "output"), ("15", "LED2/PHYAD1", "bidirectional"),
    ("17", "LED1/PHYAD0", "bidirectional"), ("41", "CLK125_NDO/LED_MODE", "bidirectional"),
    ("38", "INT_N/ALLPHYAD", "bidirectional"), ("13", "NC", "no_connect"), ("14", "NC", "no_connect"), ("47", "NC", "no_connect"),
    ("1", "AVDDH", "power_in"), ("12", "AVDDH", "power_in"), ("4", "AVDDL", "power_in"), ("9", "AVDDL", "power_in"),
    ("44", "AVDDL_PLL", "power_in"))]
KSZ9131 += [(n, name, t, "R") for n, name, t in (
    ("19", "TXD0", "input"), ("20", "TXD1", "input"), ("21", "TXD2", "input"), ("22", "TXD3", "input"), ("24", "TXC", "input"),
    ("25", "TX_CTL", "input"), ("32", "RXD0/MODE0", "bidirectional"), ("31", "RXD1/MODE1", "bidirectional"),
    ("28", "RXD2/MODE2", "bidirectional"), ("27", "RXD3/MODE3", "bidirectional"), ("33", "RX_CTL/CLK125_EN", "bidirectional"),
    ("35", "RXC/PHYAD2", "bidirectional"), ("36", "MDC", "input"), ("37", "MDIO", "bidirectional"),
    *[(n, "DVDDH", "power_in") for n in ("16", "34", "40")], *[(n, "DVDDL", "power_in") for n in ("18", "23", "26", "30", "39")],
    ("29", "VSS", "power_in"), ("49", "EP", "power_in"))]
RGMII_TX = ("TXD0", "TXD1", "TXD2", "TXD3", "TX_CTL", "TXC")        # MAC drives, PHY receives
RGMII_RX = ("RXD0", "RXD1", "RXD2", "RXD3", "RX_CTL", "RXC")        # PHY drives, MAC receives
# KSZ9131 strap resistors (10k, to DVDDH = +3V3 or to ground), sampled when RESET_N rises.
#   MODE[3:0] = 1110: RGMII, advertise 1000BASE-T full duplex and 10/100 half/full duplex
#   PHYAD[2:0] = 001; CLK125_EN = 0 (no 125 MHz output); LED_MODE = 1; ALLPHYAD = 1 (no broadcast address 0, assumed polarity)
PHY_STRAPS = {"A_RXD3_PHY": "+3V3", "A_RXD2_PHY": "+3V3", "A_RXD1_PHY": "+3V3", "A_RXD0_PHY": "GND",
              "A_RX_CTL_PHY": "GND", "A_RXC_PHY": "GND", "PHY_LED2": "GND", "PHY_LED1": "+3V3",
              "PHY_LED_MODE": "+3V3", "A_PHY_INT_N": "+3V3"}
# Parts whose footprint or pin assignment must be checked against the maker's drawing before layout.
TO_CONFIRM = {
    "U11": "LAN7801 64-SQFN 9 x 9 mm: the exposed-pad size was not in the data sheet text; KiCad's 7.15 mm pad is a placeholder",
    "U10": "KSZ9131RNX 48-QFN 7 x 7 mm: exposed-pad size to be taken from Microchip's package drawing; 5.6 mm pad is a placeholder",
    "J11": "UDE RB1-125B8G1A: LED anode/cathode pins taken from the KiCad symbol's drawing (green L3/L4, yellow L1/L2); "
           "the maker's spec text gives no polarity. Confirm from UDE's drawing"}
REFINES.update({
    **{f"A_{sig}{end}": ("A_RGMII",) for sig in RGMII_TX for end in ("_MAC", "")},
    **{f"A_{sig}{end}": ("A_RGMII",) for sig in RGMII_RX for end in ("_PHY", "")},
    "A_MDC": ("A_MDIO",), "A_PHY_INT_N": ("A_MDIO",),     # the PHY interrupt travels with the management bus
    **{f"A_MDI_{x}_{p}": (f"A_MDI_{x}",) for x in "ABCD" for p in "PN"},
    "LAN_SSTX_P": ("USB3_1",), "LAN_SSTX_N": ("USB3_1",),
    **{n: () for n in ("LAN_SW", "LAN_1V2", "LAN_1V2A", "LAN_2V5", "LAN_REXT", "LAN_FILT", "LAN_RBIAS", "LAN_XI", "LAN_XO",
                       "LAN_VBUS_DET", "LAN_CLK125", "LAN_EEDI", "LAN_TDI", "LAN_TCK", "LAN_TMS", "PHY_XI", "PHY_XO",
                       "PHY_ISET", "PHY_LED1", "PHY_LED2", "PHY_LED_MODE", "PHY_1V2", "PHY_1V2A", "PHY_1V2PLL", "PHY_1V2_SW",
                       "PHY_1V2_FB", "PHY_1V2_EN", "B_CT", "B_LED2_A", "B_LED3_A")},
})


def build_test_port(s: Sheet) -> None:
    s.paper = "A1"
    C, R, FB, L = "Device:C", "Device:R", "Device:FerriteBead", "Device:L"
    F0603 = "Inductor_SMD:L_0603_1608Metric"
    box_symbol("netscope-x1:LAN7801", LAN7801, "USB 3.1 Gen 1 to RGMII Ethernet MAC, 64-SQFN 9x9 (pins from Microchip DS00002123)")
    box_symbol("netscope-x1:KSZ9131RNX", KSZ9131, "Gigabit Ethernet PHY, RGMII, 48-QFN 7x7 (pins from Microchip DS00002841)")
    s.text("Test port Ethernet (LAN7801 + KSZ9131RNX on the CM5's USB 3 port 0) and the uplink jack. Sheet captured for real.",
           (25.4, 25.4), 2.5)
    s.text("UNTESTED. Pins are from the data sheets read as text. Values marked 'starting value' are not from a Microchip document.",
           (25.4, 33.02), 1.8)

    # ---- U11: USB 3 to RGMII bridge ----
    s.text("U11 LAN7801: USB 3 device on the module's USB 3 port 0; RGMII to the PHY", (101.6, 88.9))
    rgmii_mac = {**{f"{sig}": f"A_{sig}_MAC" for sig in RGMII_TX}, **{f"{sig}": f"A_{sig}" for sig in RGMII_RX}}
    lan = {"REF_REXT": "LAN_REXT", "REF_FILT": "LAN_FILT", "USBRBIAS": "LAN_RBIAS", "XI": "LAN_XI", "XO": "LAN_XO",
           "USB2_DP": "USB3A_DP", "USB2_DM": "USB3A_DM", "USB3_TXDP": "LAN_SSTX_P", "USB3_TXDM": "LAN_SSTX_N",
           "USB3_RXDP": "USB3A_TX_P", "USB3_RXDM": "USB3A_TX_N",        # the module transmits into our receiver
           "VBUS_DET": "LAN_VBUS_DET", "RESET_N": "LAN_NRST", "TEST": "GND", "TDI/GPIO7": "LAN_TDI", "TCK/GPIO8": "LAN_TCK",
           "TMS/GPIO9": "LAN_TMS", "TDO/GPIO10": None, "EECS/GPIO0": None, "EEDI/GPIO1": "LAN_EEDI", "EEDO/GPIO2": None,
           "EECLK/GPIO3": None, "GPIO4": None, "PME_MODE/GPIO5": None, "PME_N/GPIO6": None, "SUSPEND_N": None,
           "REFCLK_25/GPIO11": None, "NC": None, "VDD12A": "LAN_1V2A", "VSS": "GND", **rgmii_mac,
           "CLK125": "LAN_CLK125", "PHY_INT_N": "A_PHY_INT_N", "PHY_RESET_N": "A_PHY_RST_N", "DUPLEX": "+3V3",
           "MDIO": "A_MDIO", "MDC": "A_MDC", "VDDVARIO": "+3V3", "VDD33A": "+3V3", "VDD33_REG_IN": "+3V3", "VDD_SW_IN": "+3V3",
           "VDD25_REG_OUT": "LAN_2V5", "VDD12_SW_OUT": "LAN_SW", "VDD12_SW_FB": "LAN_1V2", "VDD12CORE": "LAN_1V2"}
    s.part("netscope-x1:LAN7801", "U11", "LAN7801-I/9JX", (165.1, 157.48), {n: lan[name] for n, name, _, _ in LAN7801},
           "Package_DFN_QFN:QFN-64-1EP_9x9mm_P0.5mm_EP7.15x7.15mm",
           {"Manufacturer": "Microchip", "MPN": "LAN7801-I/9JX"}, ref_at=(144.78, 106.68), value_at=(144.78, 109.22))
    s.part("Device:Crystal_GND24", "Y1", "25 MHz", (165.1, 233.68), {"1": "LAN_XI", "3": "LAN_XO", "2": "GND", "4": "GND"},
           "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", ref_at=(165.1, 226.06), value_at=(172.72, 226.06))

    # ---- U10: gigabit PHY ----
    s.text("U10 KSZ9131RNX: 1000BASE-T PHY for the test port, MDI to the Port A magnetics (T1)", (378.46, 88.9))
    phy = {"TXRXP_A": "A_MDI_A_P", "TXRXM_A": "A_MDI_A_N", "TXRXP_B": "A_MDI_B_P", "TXRXM_B": "A_MDI_B_N",
           "TXRXP_C": "A_MDI_C_P", "TXRXM_C": "A_MDI_C_N", "TXRXP_D": "A_MDI_D_P", "TXRXM_D": "A_MDI_D_N",
           "XI": "PHY_XI", "XO": "PHY_XO", "ISET": "PHY_ISET", "RESET_N": "A_PHY_RST_N", "LDO_O": None,
           "LED2/PHYAD1": "PHY_LED2", "LED1/PHYAD0": "PHY_LED1", "CLK125_NDO/LED_MODE": "PHY_LED_MODE",
           "INT_N/ALLPHYAD": "A_PHY_INT_N", "NC": None, "AVDDH": "+3V3", "AVDDL": "PHY_1V2A", "AVDDL_PLL": "PHY_1V2PLL",
           **{sig: f"A_{sig}" for sig in RGMII_TX},
           "RXD0/MODE0": "A_RXD0_PHY", "RXD1/MODE1": "A_RXD1_PHY", "RXD2/MODE2": "A_RXD2_PHY", "RXD3/MODE3": "A_RXD3_PHY",
           "RX_CTL/CLK125_EN": "A_RX_CTL_PHY", "RXC/PHYAD2": "A_RXC_PHY", "MDC": "A_MDC", "MDIO": "A_MDIO",
           "DVDDH": "+3V3", "DVDDL": "PHY_1V2", "VSS": "GND", "EP": "GND"}
    s.part("netscope-x1:KSZ9131RNX", "U10", "KSZ9131RNXI", (444.5, 152.4), {n: phy[name] for n, name, _, _ in KSZ9131},
           "Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm",
           {"Manufacturer": "Microchip", "MPN": "KSZ9131RNXI"}, ref_at=(419.1, 114.3), value_at=(419.1, 116.84))
    s.part("Device:Crystal_GND24", "Y2", "25 MHz", (444.5, 233.68), {"1": "PHY_XI", "3": "PHY_XO", "2": "GND", "4": "GND"},
           "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", ref_at=(444.5, 226.06), value_at=(452.12, 226.06))

    # ---- PHY-side protection ----
    s.text("D10, D11: TVS arrays on the PHY side of T1, one per two pairs", (548.64, 215.9))
    for ref, x, (a, b) in (("D10", 571.5, "AB"), ("D11", 627.38, "CD")):
        s.part("Power_Protection:TPD4E05U06DQA", ref, "TPD4E05U06DQA", (x, 241.3),
               {"1": f"A_MDI_{a}_P", "2": f"A_MDI_{a}_N", "4": f"A_MDI_{b}_P", "5": f"A_MDI_{b}_N", "3": "GND", "8": "GND",
                **{n: None for n in ("6", "7", "9", "10")}}, "Package_SON:USON-10_2.5x1.0mm_P0.5mm",
               {"Manufacturer": "Texas Instruments", "MPN": "TPD4E05U06DQAR (candidate)"}, ref_at=(x, 228.6), value_at=(x, 231.14))

    # ---- uplink jack ----
    s.text("J11: uplink port, the module's own Ethernet through a gigabit MagJack (green = activity, yellow = speed)", (622.3, 106.68))
    s.part("Connector:RJ45_RB1-125B8G1A", "J11", "RB1-125B8G1A", (695.96, 152.4),
           {"R2": "B_MDI0_P", "R3": "B_MDI0_N", "R4": "B_MDI1_P", "R5": "B_MDI1_N", "R6": "B_MDI2_P", "R7": "B_MDI2_N",
            "R8": "B_MDI3_P", "R9": "B_MDI3_N", "R1": "B_CT", "R10": "GND", "SH": "GND",
            "L3": "B_LED3_A", "L4": "B_LED3", "L1": "B_LED2_A", "L2": "B_LED2"},
           "Connector_RJ:RJ45_UDE_RB1-125B8G1A", {"Manufacturer": "UDE", "MPN": "RB1-125B8G1A (candidate)"},
           ref_at=(711.2, 121.92), value_at=(711.2, 124.46))

    # ---- PHY core supply ----
    s.text("U12: 1.2 V core supply for the PHY (220 mA at 1000BASE-T per the data sheet)", (601.98, 274.32))
    s.part("Regulator_Switching:TLV62569DBV", "U12", "TLV62569DBV", (736.6, 241.3),
           {"4": "+3V3", "1": "PHY_1V2_EN", "2": "GND", "3": "PHY_1V2_SW", "5": "PHY_1V2_FB"}, "Package_TO_SOT_SMD:SOT-23-5",
           {"Manufacturer": "Texas Instruments", "MPN": "TLV62569DBVR"}, ref_at=(731.52, 228.6), value_at=(731.52, 231.14))

    # ---- support parts ----
    s.text("U11 supply and reference parts (LAN7801 schematic checklist): 10n on every supply pin, internal 1.2 V switcher, 2.5 V LDO",
           (25.4, 266.7))
    _row(s, 30.48, 297.18, [
        *[(f"C{100 + i}", C, "10n", C0402, "+3V3", "GND") for i in range(7)],             # VDDVARIO x7
        ("C107", C, "10n", C0402, "+3V3", "GND"), ("C108", C, "10n", C0402, "+3V3", "GND"),   # VDD33A, VDD33_REG_IN
        ("C109", C, "10n", C0402, "+3V3", "GND"), ("C110", C, "10u 10V", C0805, "+3V3", "GND"),   # VDD_SW_IN + bulk
        ("C111", C, "10n", C0402, "LAN_2V5", "GND"), ("C112", C, "1u", C0402, "LAN_2V5", "GND"),
        ("L11", L, "3u3", "Inductor_SMD:L_1008_2520Metric", "LAN_SW", "LAN_1V2"),
        ("C113", C, "10n", C0603, "LAN_1V2", "GND"), ("C114", C, "22u 6V3", C0805, "LAN_1V2", "GND"),
        ("C115", C, "10n", C0402, "LAN_1V2", "GND"), ("C116", C, "10n", C0402, "LAN_1V2", "GND"),   # VDD12CORE x2
        ("FB11", FB, "220R@100MHz", F0603, "LAN_1V2", "LAN_1V2A"),
        ("C117", C, "1u", C0402, "LAN_1V2A", "GND"), *[(f"C{118 + i}", C, "10n", C0402, "LAN_1V2A", "GND") for i in range(3)],
        ("C121", C, "1u", C0402, "LAN_FILT", "GND"), ("C122", C, "15p", C0402, "LAN_XI", "GND"),
        ("C123", C, "15p", C0402, "LAN_XO", "GND")])
    s.text("U11 resistors: RGMII series (starting value 10R from the checklist), bias, straps, pull-ups; USB 3 TX coupling capacitors",
           (25.4, 325.12))
    _row(s, 30.48, 355.6, [
        *[(f"R{100 + i}", R, "10R", R0402, f"A_{sig}_MAC", f"A_{sig}") for i, sig in enumerate(RGMII_TX)],
        ("R106", R, "1k5", R0402, "+3V3", "A_MDIO"), ("R107", R, "12k0 1%", R0402, "LAN_RBIAS", "GND"),
        ("R108", R, "2k00 1%", R0402, "LAN_REXT", "GND"), ("R109", R, "1k", R0402, "+3V3", "LAN_VBUS_DET"),
        ("R110", R, "10k", R0402, "LAN_CLK125", "GND"), ("R111", R, "10k", R0402, "LAN_EEDI", "GND"),
        ("R112", R, "10k", R0402, "+3V3", "LAN_TDI"), ("R113", R, "10k", R0402, "+3V3", "LAN_TCK"),
        ("R114", R, "10k", R0402, "+3V3", "LAN_TMS"), ("R115", R, "10k", R0402, "+3V3", "LAN_NRST"),
        ("R116", R, "10k", R0402, "A_PHY_RST_N", "GND"),
        ("C124", C, "100n", C0402, "LAN_SSTX_P", "USB3A_RX_P"), ("C125", C, "100n", C0402, "LAN_SSTX_N", "USB3A_RX_N")])
    s.text("U10 resistors: RGMII series (starting value), ISET, straps (MODE 1110, PHYAD 001, no CLK125, ALLPHYAD 1)", (25.4, 381.0))
    straps = [(f"R{140 + i}", R, "10k", R0402, net, rail) for i, (net, rail) in enumerate(PHY_STRAPS.items())]
    _row(s, 30.48, 411.48, [
        *[(f"R{117 + i}", R, "10R", R0402, f"A_{sig}_PHY", f"A_{sig}") for i, sig in enumerate(RGMII_RX)],
        ("R123", R, "6k04 1%", R0402, "PHY_ISET", "GND"), *straps])
    s.text("U10 supply decoupling (starting values: compare with Microchip's EVB-KSZ9131RNX schematic), crystal capacitors",
           (25.4, 436.88))
    _row(s, 30.48, 467.36, [
        ("C130", C, "100n", C0402, "+3V3", "GND"), ("C131", C, "100n", C0402, "+3V3", "GND"),
        ("C132", C, "10u 10V", C0805, "+3V3", "GND"),                                           # AVDDH
        *[(f"C{133 + i}", C, "100n", C0402, "+3V3", "GND") for i in range(3)],                  # DVDDH
        *[(f"C{136 + i}", C, "100n", C0402, "PHY_1V2", "GND") for i in range(5)],               # DVDDL
        ("C141", C, "10u 6V3", C0805, "PHY_1V2", "GND"),
        ("FB12", FB, "220R@100MHz", F0603, "PHY_1V2", "PHY_1V2A"),
        ("C142", C, "100n", C0402, "PHY_1V2A", "GND"), ("C143", C, "100n", C0402, "PHY_1V2A", "GND"),
        ("C144", C, "1u", C0402, "PHY_1V2A", "GND"),
        ("FB13", FB, "220R@100MHz", F0603, "PHY_1V2", "PHY_1V2PLL"),
        ("C145", C, "100n", C0402, "PHY_1V2PLL", "GND"), ("C146", C, "1u", C0402, "PHY_1V2PLL", "GND"),
        ("C147", C, "15p", C0402, "PHY_XI", "GND"), ("C148", C, "15p", C0402, "PHY_XO", "GND")])
    s.text("U12 parts: 0.6 V x (1 + 100k/100k) = 1.2 V; EN delayed by R/C so the core comes up after 3.3 V", (452.12, 325.12))
    _row(s, 457.2, 355.6, [
        ("C150", C, "10u 10V", C0805, "+3V3", "GND"), ("L12", L, "2u2", "Inductor_SMD:L_1008_2520Metric", "PHY_1V2_SW", "PHY_1V2"),
        ("C151", C, "22u 6V3", C0805, "PHY_1V2", "GND"), ("R130", R, "100k 1%", R0402, "PHY_1V2", "PHY_1V2_FB"),
        ("R131", R, "100k 1%", R0402, "PHY_1V2_FB", "GND"), ("R132", R, "100k", R0402, "+3V3", "PHY_1V2_EN"),
        ("C152", C, "100n", C0402, "PHY_1V2_EN", "GND")])
    s.text("J11 parts: LED resistors to the module's 3.3 V (LED pins sink 8 mA max), centre-tap capacitor", (452.12, 381.0))
    _row(s, 457.2, 411.48, [
        ("R133", R, "330R", R0402, "SOM_3V3", "B_LED3_A"), ("R134", R, "330R", R0402, "SOM_3V3", "B_LED2_A"),
        ("C153", C, "100n", C0402, "B_CT", "GND")])
    for i, net in enumerate(("LAN_1V2", "LAN_1V2A", "PHY_1V2", "PHY_1V2A", "PHY_1V2PLL")):
        x = 467.36 + i * 15.24
        s.part("power:PWR_FLAG", f"#FLG{10 + i}", "PWR_FLAG", (x, 457.2), {"1": net}, ref_at=(x, 452.12), value_at=(x, 449.58))

    notes = (
        "USB 3: the module has the AC coupling capacitors on its own TX pair (CM5 data sheet), so only our TX pair gets C124/C125.",
        "RGMII delays: the Linux lan78xx driver asks the PHY driver for internal delays (RGMII-ID); no delay is built into the traces.",
        "No EEPROM: EEDI is pulled down; the MAC address must be set by software. PME/wake pins and REFCLK_25 are unused.",
        "LAN_NRST: pulled up, so U11 starts with the 3.3 V rail; GPIO6 on the module can pulse it (checklist: no RC reset).",
        "PHY reset: R116 holds the PHY in reset until U11 drives PHY_RESET_N. The PHY needs 10 ms of stable supply first: bench check.",
        "Crystals: 25 MHz, 3225, CL 10 pF, ESR <= 50 Ohm, +/-20 ppm; 15 pF loads assume about 3 pF of stray capacitance.",
        "Strap polarity of ALLPHYAD (pull-up = 1) is assumed by analogy with the other straps; the data sheet text does not say.",
        "J11: the jack joins its four PHY-side centre taps inside (pin R1); C153 takes them to ground, the usual practice for",
        "voltage-mode PHYs (compare with the CM5 data sheet's Ethernet figure). The Port A magnetics (T1, sheet 1) need 100 nF",
        "per centre tap for the KSZ9131. J11 shield and R10 (the jack's 75 Ohm / 1000 pF 2 kV termination return, placed among the",
        "PHY-side pins by the maker) go to system ground, as on a laptop's LAN port: the barrier is the jack's transformer and",
        "capacitor. Only the test port (J10, sheet 1) keeps the floating CHASSIS net.")
    for i, line in enumerate(notes):
        s.text(line, (25.4, 497.84 + i * 4.445), 1.5)


# ---- microSD reader sheet (option, not fitted on rev A) ---------------------------------------------
# USB2244 pins from Microchip's USB224x data sheet (DS00001979A, reset-state table), which agrees with the
# older SMSC pin-description table; the same data sheet's pin diagram disagrees for pins 23-26.  Support
# parts per Microchip's USB2244 hardware design checklist (DS00004319A).
USB2244 = [(n, name, t, "L") for n, name, t in (
    ("2", "USB+", "bidirectional"), ("3", "USB-", "bidirectional"), ("33", "XTAL1", "input"), ("32", "XTAL2", "output"),
    ("35", "RBIAS", "passive"), ("18", "RESET_N", "input"), ("28", "TEST", "input"), ("27", "RXD/SDA", "bidirectional"),
    ("31", "TXD/SCK", "bidirectional"), ("1", "LED", "output"), ("12", "NC", "no_connect"), ("15", "NC", "no_connect"),
    ("16", "NC", "no_connect"), ("17", "NC", "no_connect"), ("19", "(unnamed)", "no_connect"),
    ("24", "(unnamed)", "no_connect"), ("29", "(unnamed)", "no_connect"))]
USB2244 += [(n, name, t, "R") for n, name, t in (
    ("9", "SD_CLK", "output"), ("11", "SD_CMD", "bidirectional"), ("5", "SD_D0", "bidirectional"),
    ("4", "SD_D1", "bidirectional"), ("25", "SD_D2", "bidirectional"), ("23", "SD_D3", "bidirectional"),
    ("20", "SD_D4", "bidirectional"), ("10", "SD_D5", "bidirectional"), ("8", "SD_D6", "bidirectional"),
    ("7", "SD_D7", "bidirectional"), ("26", "SD_nCD", "input"), ("30", "SD_WP", "input"), ("21", "CRD_PWR", "power_out"),
    ("6", "VDD33", "power_in"), ("14", "VDD33", "power_in"), ("22", "VDD33", "power_in"), ("36", "VDDA33", "power_in"),
    ("13", "VDD18", "power_out"), ("34", "VDD18PLL", "power_out"), ("37", "VSS", "power_in"))]
TO_CONFIRM.update({
    "U60": "USB2244 36-QFN 6 x 6 mm: pins 23-26 differ between the data sheet's tables and its pin diagram (tables used); "
           "exposed-pad size not in the text (4.1 mm placeholder)"})
REFINES.update({
    **{n: ("SD_BUS",) for n in ("SD_CLK", "SD_CMD", "SD_D0", "SD_D1", "SD_D2", "SD_D3", "SD_NCD", "SD_VCC")},
    **{n: () for n in ("U60_1V8", "U60_1V8PLL", "U60_NRST", "U60_SDA", "U60_SCK", "U60_WP", "U60_XI", "U60_XO", "U60_RBIAS")},
})


def build_microsd(s: Sheet) -> None:
    s.paper = "A3"
    C, R = "Device:C", "Device:R"
    box_symbol("netscope-x1:USB2244", USB2244, "USB 2.0 SD/MMC card reader, 36-QFN 6x6 (pins from Microchip DS00001979A)")
    s.text("microSD reader (OPTION, not fitted on rev A: every part is marked DNP). Sheet captured for real.", (20.32, 20.32), 2.0)
    s.text("UNTESTED. USB2244 on the module's second USB 2.0 pair; card power from the reader's own switch.", (20.32, 25.4))
    usb = {"USB+": "USB3B_DP", "USB-": "USB3B_DM", "XTAL1": "U60_XI", "XTAL2": "U60_XO", "RBIAS": "U60_RBIAS",
           "RESET_N": "U60_NRST", "TEST": "GND", "RXD/SDA": "U60_SDA", "TXD/SCK": "U60_SCK", "LED": None, "NC": None,
           "(unnamed)": None, "SD_CLK": "SD_CLK", "SD_CMD": "SD_CMD", "SD_D0": "SD_D0", "SD_D1": "SD_D1", "SD_D2": "SD_D2",
           "SD_D3": "SD_D3", "SD_D4": None, "SD_D5": None, "SD_D6": None, "SD_D7": None, "SD_nCD": "SD_NCD", "SD_WP": "U60_WP",
           "CRD_PWR": "SD_VCC", "VDD33": "+3V3", "VDDA33": "+3V3", "VDD18": "U60_1V8", "VDD18PLL": "U60_1V8PLL", "VSS": "GND"}
    s.part("netscope-x1:USB2244", "U60", "USB2244-AEZG", (139.7, 101.6), {n: usb[name] for n, name, _, _ in USB2244},
           "Package_DFN_QFN:QFN-36-1EP_6x6mm_P0.5mm_EP4.1x4.1mm", {"Manufacturer": "Microchip", "MPN": "USB2244-AEZG-06"},
           ref_at=(127.0, 68.58), value_at=(127.0, 71.12), dnp=True)
    s.part("Device:Crystal_GND24", "Y3", "24 MHz", (139.7, 157.48), {"1": "U60_XI", "3": "U60_XO", "2": "GND", "4": "GND"},
           "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", ref_at=(139.7, 149.86), value_at=(147.32, 149.86), dnp=True)
    s.text("J30: push-push microSD socket, card slot in the top end wall", (241.3, 55.88))
    s.part("Connector:Micro_SD_Card_Det_Hirose_DM3AT", "J30", "DM3AT-SF-PEJM5", (281.94, 99.06),
           {"1": "SD_D2", "2": "SD_D3", "3": "SD_CMD", "4": "SD_VCC", "5": "SD_CLK", "6": "GND", "7": "SD_D0", "8": "SD_D1",
            "9": "SD_NCD", "10": "GND", "11": "GND"}, "Connector_Card:microSD_HC_Hirose_DM3AT-SF-PEJM5",
           {"Manufacturer": "Hirose", "MPN": "DM3AT-SF-PEJM5"}, ref_at=(271.78, 71.12), value_at=(271.78, 73.66), dnp=True)
    s.text("Support parts (USB2244 hardware design checklist)", (20.32, 190.5))
    _row(s, 25.4, 213.36, [
        *[(f"C{160 + i}", C, "100n", C0402, "+3V3", "GND") for i in range(4)],          # VDD33 x3, VDDA33
        ("C164", C, "1u", C0402, "U60_1V8", "GND"), ("C165", C, "1u", C0402, "U60_1V8PLL", "GND"),
        ("C166", C, "4u7", C0603, "SD_VCC", "GND"), ("C167", C, "1u", C0402, "U60_NRST", "GND"),
        ("C168", C, "18p", C0402, "U60_XI", "GND"), ("C169", C, "18p", C0402, "U60_XO", "GND"),
        ("R160", R, "1M", R0402, "U60_XI", "U60_XO"), ("R161", R, "12k0 1%", R0402, "U60_RBIAS", "GND"),
        ("R162", R, "10k", R0402, "+3V3", "U60_NRST"), ("R163", R, "10k", R0402, "+3V3", "SD_NCD"),
        ("R164", R, "10k", R0402, "U60_WP", "GND"), ("R165", R, "10k", R0402, "+3V3", "U60_SDA"),
        ("R166", R, "10k", R0402, "+3V3", "U60_SCK")], dnp=True)
    notes = (
        "Card detect: the socket's switch is normally open and closes with a card in, pulling SD_nCD low against R163.",
        "SD_WP pulled down (R164): the checklist says this is needed to write to microSD. D4-D7 float (4-bit card).",
        "Reset: 10k / 1u to 3.3 V as in the checklist's figure; a reset after power-up is not required.",
        "No configuration EEPROM: internal defaults. SDA/SCK pulled up so a probe for an EEPROM sees an idle bus (the",
        "checklist does not say what to do with them; this is an assumption). Crystal: 24 MHz, CL 10 pF, 18 pF loads.",
        "Powered from +3V3, not +5V as the block netlist had it: the chip runs from 3.3 V and makes its own 1.8 V.",
        "No ESD parts on the card lines; add them if the slot is reachable in normal use.")
    for i, line in enumerate(notes):
        s.text(line, (20.32, 241.3 + i * 3.81), 1.27)


# sheet title in the block netlist -> (file stem, builder)
CAPTURED = {"Test-port MAC and PHY, uplink port": ("02_test_port_mac_and_phy", build_test_port),
            "Processor module, display, debug pads": ("05_processor_module", build_processor),
            "Coprocessor, keys, indicators": ("06_coprocessor", build_coprocessor),
            "Power: USB-C, charger, battery, rails": ("07_power", build_power),
            "microSD reader (option)": ("09_microsd_reader_option", build_microsd)}
