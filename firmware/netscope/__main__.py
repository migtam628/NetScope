"""Command line entry point.

    python -m netscope serve                          simulator UI at http://127.0.0.1:8080/
    python -m netscope scenarios                      list simulated situations
    python -m netscope --scenario dns_fail run autodiag
    python -m netscope run poe -p load_w=20 --authorize
    sudo python -m netscope --hal linux --iface eth0 serve
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__

MARK = {"PASS": "[PASS]", "FAIL": "[FAIL]", "WARNING": "[WARN]", "NOT_TESTED": "[ -- ]"}


def make_hal(args):
    if args.hal == "linux":
        from .hal.linux import LinuxHal
        return LinuxHal(args.iface, args.wlan, args.coproc)
    from .hal.sim import SimHal
    return SimHal(args.scenario)


def _value(text: str):
    try:
        return json.loads(text)
    except ValueError:
        return text


def print_result(r: dict) -> None:
    print(f"{MARK[r['status']]} {r['title']}: {r['summary']}")
    for f in r["findings"]:
        print(f"         - {f}")
    for f in r["recommendations"]:
        print(f"         > {f}")


def cmd_run(args) -> int:
    from .engine import autodiag
    from .engine.tools import TOOLS, run_tool
    hal = make_hal(args)
    if args.tool == "autodiag":
        out = autodiag.run(hal)
    elif args.tool in TOOLS:
        params = {k: _value(v) for k, v in (p.split("=", 1) for p in args.param)}
        if args.authorize:
            params["authorized"] = True
        r = run_tool(hal, args.tool, params)
        out = dict(overall=r.status.value, results=[r.to_dict()], diagnosis=None,
                   provenance=[r.provenance])
    else:
        print(f"unknown tool '{args.tool}'. Tools: autodiag, " + ", ".join(TOOLS), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"NetScope X1 {__version__}  data source: {', '.join(out['provenance'])}")
        for r in out["results"]:
            print_result(r)
        print(f"OVERALL: {out['overall']}")
        d = out["diagnosis"]
        if d:
            print(f"\nDiagnosis: {d['headline']}\n  {d['explanation']}")
            for c in d["likely_causes"]:
                print(f"  cause: {c}")
            for i, s in enumerate(d["next_steps"], 1):
                print(f"  {i}. {s}")
            for n in d["notes"]:
                print(f"  note: {n}")
    return 1 if out["overall"] == "FAIL" else 0


def cmd_serve(args) -> int:
    from aiohttp import web

    from .api.server import make_app
    from .reports.store import ReportStore
    ui = Path(args.ui) if args.ui else Path(__file__).resolve().parents[1] / "ui"
    if not (ui / "index.html").exists():
        print(f"UI files not found in {ui} (pass --ui)", file=sys.stderr)
        return 2
    hal = make_hal(args)
    app = make_app(hal, ReportStore(args.reports), ui)
    print(f"NetScope X1 {__version__}  backend: {hal.name}  data source: {hal.provenance}")
    print(f"Open http://{args.host}:{args.port}/")
    web.run_app(app, host=args.host, port=args.port, print=None)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="netscope", description=f"NetScope X1 engine {__version__}")
    p.add_argument("--hal", choices=["sim", "linux"], default="sim")
    p.add_argument("--scenario", default="healthy", help="simulator scenario (see 'scenarios')")
    p.add_argument("--iface", default="eth0", help="test-port interface (linux backend)")
    p.add_argument("--wlan", default="wlan0", help="Wi-Fi interface (linux backend)")
    p.add_argument("--coproc", default=None, help="coprocessor serial device (device only)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("serve", help="run the API and touch UI")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8080)
    s.add_argument("--reports", default=str(Path.home() / ".netscope" / "reports"))
    s.add_argument("--ui", default=None, help="directory holding index.html")

    sub.add_parser("scenarios", help="list simulator scenarios")

    r = sub.add_parser("run", help="run one tool, or 'autodiag', and print the result")
    r.add_argument("tool")
    r.add_argument("-p", "--param", action="append", default=[], metavar="NAME=VALUE")
    r.add_argument("--authorize", action="store_true",
                   help="allow tests that can disturb the network (PoE load, throughput, capture)")
    r.add_argument("--json", action="store_true")

    args = p.parse_args(argv)
    if args.command == "scenarios":
        from .hal.sim import SCENARIOS
        for k, v in SCENARIOS.items():
            print(f"{k:14} {v['title']}")
        return 0
    return cmd_serve(args) if args.command == "serve" else cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
