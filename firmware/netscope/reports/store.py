"""Report storage and export (JSON, CSV, PDF).

A report is a plain dict saved as <id>.json; CSV and PDF are rendered from it
on demand so there is one source of truth per report.
"""
from __future__ import annotations

import csv
import io
import json
import re
import time
from pathlib import Path

from .. import __version__

STATUS_RGB = {"PASS": (22, 128, 61), "FAIL": (200, 30, 30), "WARNING": (190, 110, 0),
              "NOT_TESTED": (110, 110, 110)}


def build_report(device: dict, test_type: str, results: list[dict], *, job: str = "",
                 technician: str = "", notes: str = "", diagnosis: dict | None = None,
                 overall: str | None = None) -> dict:
    now = time.time()
    provenance = sorted({r.get("provenance", "unknown") for r in results})
    rid = time.strftime("%Y%m%d-%H%M%S", time.localtime(now)) + "-" + \
        (re.sub(r"[^A-Za-z0-9]+", "", job)[:16] or "nojob")
    if overall is None:
        rank = {"NOT_TESTED": 0, "PASS": 1, "WARNING": 2, "FAIL": 3}
        overall = max((r["status"] for r in results), key=lambda s: rank[s], default="NOT_TESTED")
    actions: list[str] = list((diagnosis or {}).get("next_steps", []))
    for r in results:
        for rec in r.get("recommendations", []):
            if rec not in actions:
                actions.append(rec)
    return dict(
        schema="netscope.report/1", id=rid,
        device=dict(model=device.get("model"), serial=device.get("serial"),
                    hw_rev=device.get("hw_rev"), firmware=__version__),
        job=job, technician=technician,
        created=now, created_iso=time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now)),
        test_type=test_type, overall=overall, provenance=provenance,
        results=results, diagnosis=diagnosis, notes=notes, corrective_actions=actions)


class ReportStore:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, rid: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9-]+", rid):
            raise KeyError(rid)
        return self.root / f"{rid}.json"

    def save(self, report: dict) -> dict:
        p = self._path(report["id"])
        n = 1
        while p.exists():  # same job twice in one second
            n += 1
            report["id"] = re.sub(r"(-r\d+)?$", f"-r{n}", report["id"], count=1)
            p = self._path(report["id"])
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(report, indent=2))
        tmp.replace(p)  # atomic: a power cut cannot leave a half-written report
        return report

    def load(self, rid: str) -> dict:
        p = self._path(rid)
        if not p.exists():
            raise KeyError(rid)
        return json.loads(p.read_text())

    def delete(self, rid: str) -> None:
        self._path(rid).unlink(missing_ok=True)

    def list(self) -> list[dict]:
        out = []
        for p in sorted(self.root.glob("*.json"), reverse=True):
            try:
                r = json.loads(p.read_text())
            except (OSError, ValueError):
                continue
            out.append({k: r.get(k) for k in
                        ("id", "job", "technician", "created_iso", "test_type", "overall",
                         "provenance")})
        return out


def _flatten(prefix: str, value, out: list[tuple[str, str]]) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            _flatten(f"{prefix}.{k}" if prefix else str(k), v, out)
    elif isinstance(value, list) and value and all(isinstance(v, (dict, list)) for v in value):
        for i, v in enumerate(value):
            _flatten(f"{prefix}[{i}]", v, out)
    else:
        out.append((prefix, json.dumps(value) if isinstance(value, list) else str(value)))


def to_csv(report: dict) -> str:
    """One row per measurement so it pivots cleanly in a spreadsheet."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["report_id", "job", "technician", "datetime", "device_serial", "provenance",
                "test", "status", "summary", "measurement", "value"])
    base = [report["id"], report["job"], report["technician"], report["created_iso"],
            report["device"]["serial"]]
    for r in report["results"]:
        head = base + [r.get("provenance", ""), r["title"], r["status"], r["summary"]]
        flat: list[tuple[str, str]] = []
        _flatten("", r.get("measurements", {}), flat)
        if not flat:
            w.writerow(head + ["", ""])
        for k, v in flat:
            w.writerow(head + [k, v])
    return buf.getvalue()


def _latin(s) -> str:
    return str(s).replace("→", "->").encode("latin-1", "replace").decode("latin-1")


def to_pdf(report: dict) -> bytes:
    from fpdf import FPDF  # imported here so the engine runs without fpdf2 installed

    simulated = "simulated" in report.get("provenance", [])
    pdf = FPDF(format="Letter")
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    width = pdf.epw

    def line(text: str, size: int = 10, style: str = "", rgb=(20, 20, 20), h: float = 5.2):
        pdf.set_font("Helvetica", style, size)
        pdf.set_text_color(*rgb)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(width, h, _latin(text))

    line("NetScope X1 Test Report", 18, "B")
    if simulated:
        pdf.set_fill_color(200, 30, 30)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(width, 8, "SIMULATED DATA - NOT A FIELD MEASUREMENT", fill=True, align="C",
                 new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    dev = report["device"]
    for label, value in [
            ("Report", report["id"]), ("Job / work order", report["job"] or "-"),
            ("Technician", report["technician"] or "-"), ("Date", report["created_iso"]),
            ("Test type", report["test_type"]),
            ("Device", f"{dev['model']}  S/N {dev['serial']}  HW {dev['hw_rev']}  FW {dev['firmware']}"),
            ("Data source", ", ".join(report.get("provenance", [])))]:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(90, 90, 90)
        pdf.cell(38, 5.5, label)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(20, 20, 20)
        pdf.cell(0, 5.5, _latin(value), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    line(f"Overall: {report['overall'].replace('_', ' ')}", 13, "B",
         STATUS_RGB.get(report["overall"], (20, 20, 20)), 7)

    diag = report.get("diagnosis")
    if diag and diag.get("headline"):
        pdf.ln(1)
        line("Diagnosis", 12, "B", h=6.5)
        line(diag["headline"], 10, "B")
        if diag.get("explanation"):
            line(diag["explanation"])
        for title, key in (("Likely causes", "likely_causes"), ("Notes", "notes")):
            if diag.get(key):
                line(title, 10, "B")
                for c in diag[key]:
                    line(f"  - {c}")

    pdf.ln(2)
    line("Results", 12, "B", h=6.5)
    for r in report["results"]:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*STATUS_RGB.get(r["status"], (20, 20, 20)))
        pdf.cell(28, 5.5, r["status"].replace("_", " "))
        pdf.set_text_color(20, 20, 20)
        pdf.cell(0, 5.5, _latin(r["title"]), new_x="LMARGIN", new_y="NEXT")
        if r.get("summary"):
            line("    " + r["summary"])
        for f in r.get("findings", []):
            line("    - " + f, 9, rgb=(70, 70, 70), h=4.6)

    if report.get("corrective_actions"):
        pdf.ln(2)
        line("Recommended corrective actions", 12, "B", h=6.5)
        for i, a in enumerate(report["corrective_actions"], 1):
            line(f"{i}. {a}")
    pdf.ln(2)
    line("Technician notes", 12, "B", h=6.5)
    line(report.get("notes") or "-")
    pdf.ln(3)
    line("Cable results are continuity and TDR verification, not TIA/ISO certification.",
         8, "I", (110, 110, 110), 4)
    return bytes(pdf.output())
