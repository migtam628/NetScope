"""Local HTTP API + UI host.

On the device this listens on 127.0.0.1 only and the kiosk browser is its
single client.  The same server with the simulator HAL is the desktop
simulator.  HAL calls block, so they run on a worker thread; the UI polls
job state.
"""
from __future__ import annotations

import asyncio
import itertools
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from aiohttp import web

from .. import __version__
from ..engine import autodiag, cloud_ai, rules
from ..engine.tools import TOOLS, run_tool
from ..hal.base import Hal, HalError, HalUnsupported
from ..hal.sim import SCENARIOS, SimHal
from ..models import TestResult
from ..reports import store as rstore

MAX_JOBS = 50


def make_app(hal: Hal, reports: rstore.ReportStore, ui_dir: Path) -> web.Application:
    app = web.Application(client_max_size=4 * 1024 * 1024)
    pool = ThreadPoolExecutor(max_workers=1)  # one measurement at a time: one test port
    jobs: dict[str, dict] = {}
    ids = itertools.count(1)

    def j(data, status: int = 200) -> web.Response:
        return web.json_response(data, status=status)

    async def info(_):
        d = dict(version=__version__, provenance=hal.provenance, backend=hal.name,
                 ai_configured=cloud_ai.configured(), time=time.time())
        try:
            d["device"] = hal.device_info()
        except HalUnsupported:
            d["device"] = {}
        try:
            d["battery"] = hal.battery()
        except (HalUnsupported, HalError):
            d["battery"] = None
        return j(d)

    async def tools(_):
        return j([dict(id=t.id, title=t.title, category=t.category, disruptive=t.disruptive,
                       params=[dict(name=n, type=ty, default=df) for n, ty, df in t.params])
                  for t in TOOLS.values()])

    def _work(job: dict, tool_id: str, params: dict) -> None:
        try:
            if tool_id == "autodiag":
                job["result"] = autodiag.run(
                    hal, on_step=lambda r: job["steps"].append(r.to_dict()),
                    on_start=lambda k: job.update(current=k))
            else:
                job["current"] = tool_id
                r = run_tool(hal, tool_id, params)
                job["steps"].append(r.to_dict())
                job["result"] = dict(overall=r.status.value, results=[r.to_dict()],
                                     diagnosis=None, provenance=[r.provenance])
            job["state"] = "done"
        except Exception as e:  # surfaced to the UI rather than killing the worker
            job.update(state="error", error=f"{type(e).__name__}: {e}")
        job["current"] = None

    async def start_job(req: web.Request):
        body = await req.json()
        tool_id = body.get("tool")
        if tool_id != "autodiag" and tool_id not in TOOLS:
            return j(dict(error=f"unknown tool '{tool_id}'"), 400)
        jid = str(next(ids))
        jobs[jid] = dict(id=jid, tool=tool_id, state="running", current=None, steps=[],
                         result=None, error=None,
                         plan=[dict(id=k, title=t) for k, t in autodiag.STEPS]
                         if tool_id == "autodiag" else None)
        for old in list(jobs)[:-MAX_JOBS]:
            jobs.pop(old, None)
        asyncio.get_running_loop().run_in_executor(pool, _work, jobs[jid], tool_id,
                                                  body.get("params") or {})
        return j(dict(id=jid))

    async def get_job(req: web.Request):
        job = jobs.get(req.match_info["id"])
        return j(job) if job else j(dict(error="no such job"), 404)

    async def assistant(req: web.Request):
        body = await req.json()
        results = body.get("results") or []
        local = body.get("diagnosis") or rules.diagnose(
            {r["test_id"]: TestResult.from_dict(r) for r in results}).to_dict()
        out = dict(local=local, cloud=None, cloud_error=None)
        if body.get("cloud"):
            try:
                out["cloud"] = await asyncio.get_running_loop().run_in_executor(
                    None, cloud_ai.analyse, results, local)
            except Exception as e:
                out["cloud_error"] = str(e)
        return j(out)

    async def list_reports(_):
        return j(reports.list())

    async def save_report(req: web.Request):
        b = await req.json()
        if not b.get("results"):
            return j(dict(error="a report needs at least one result"), 400)
        try:
            device = hal.device_info()
        except HalUnsupported:
            device = {}
        rep = rstore.build_report(device, b.get("test_type", "Test"), b["results"],
                                  job=b.get("job", ""), technician=b.get("technician", ""),
                                  notes=b.get("notes", ""), diagnosis=b.get("diagnosis"),
                                  overall=b.get("overall"))
        return j(reports.save(rep), 201)

    async def get_report(req: web.Request):
        rid, fmt = req.match_info["id"], req.match_info.get("fmt", "json")
        try:
            rep = reports.load(rid)
        except KeyError:
            return j(dict(error="no such report"), 404)
        disp = {"Content-Disposition": f'attachment; filename="netscope-{rid}.{fmt}"'}
        if fmt == "csv":
            return web.Response(text=rstore.to_csv(rep), content_type="text/csv", headers=disp)
        if fmt == "pdf":
            return web.Response(body=rstore.to_pdf(rep), content_type="application/pdf",
                                headers=disp)
        return j(rep)

    async def del_report(req: web.Request):
        reports.delete(req.match_info["id"])
        return j(dict(ok=True))

    async def scenarios(_):
        if not isinstance(hal, SimHal):
            return j(dict(current=None, scenarios=[]))
        return j(dict(current=hal.scenario,
                      scenarios=[dict(id=k, title=v["title"]) for k, v in SCENARIOS.items()]))

    async def set_scenario(req: web.Request):
        if not isinstance(hal, SimHal):
            return j(dict(error="scenarios exist only in the simulator"), 400)
        try:
            hal.set_scenario((await req.json()).get("id", ""))
        except KeyError as e:
            return j(dict(error=str(e)), 400)
        return j(dict(current=hal.scenario))

    async def index(_):
        return web.FileResponse(ui_dir / "index.html", headers={"Cache-Control": "no-store"})

    app.add_routes([
        web.get("/", index),
        web.get("/api/info", info), web.get("/api/tools", tools),
        web.post("/api/jobs", start_job), web.get("/api/jobs/{id}", get_job),
        web.post("/api/assistant", assistant),
        web.get("/api/reports", list_reports), web.post("/api/reports", save_report),
        web.get("/api/reports/{id}", get_report),
        web.get("/api/reports/{id}/export.{fmt:(json|csv|pdf)}", get_report),
        web.delete("/api/reports/{id}", del_report),
        web.get("/api/sim/scenarios", scenarios), web.post("/api/sim/scenario", set_scenario),
        web.static("/ui", ui_dir),
    ])
    return app
