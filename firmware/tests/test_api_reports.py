"""HTTP API end to end (simulator HAL) and report exports."""
import asyncio
import csv
import io

import pytest
from aiohttp.test_utils import TestClient, TestServer

from netscope.api.server import make_app
from netscope.engine import autodiag
from netscope.hal import coproc as cp
from netscope.hal.sim import SimHal
from netscope.reports import store as rstore

from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "ui"


def run(coro):
    return asyncio.run(coro)


async def _client(tmp_path, scenario="healthy"):
    app = make_app(SimHal(scenario), rstore.ReportStore(tmp_path), UI)
    c = TestClient(TestServer(app))
    await c.start_server()
    return c


async def _job(c, tool, params=None):
    r = await c.post("/api/jobs", json=dict(tool=tool, params=params or {}))
    jid = (await r.json())["id"]
    for _ in range(200):
        job = await (await c.get(f"/api/jobs/{jid}")).json()
        if job["state"] != "running":
            return job
        await asyncio.sleep(0.01)
    raise AssertionError("job did not finish")


def test_full_flow_autodiag_to_exports(tmp_path):
    async def go():
        c = await _client(tmp_path, "no_internet")
        try:
            info = await (await c.get("/api/info")).json()
            assert info["provenance"] == "simulated" and info["battery"]["percent"] == 78
            assert (await c.get("/")).status == 200

            job = await _job(c, "autodiag")
            assert job["state"] == "done" and len(job["steps"]) == len(autodiag.STEPS)
            res = job["result"]
            assert res["overall"] == "FAIL" and res["diagnosis"]["layer"] == "upstream"

            r = await c.post("/api/reports", json=dict(
                job="WO-48213", technician="M. T.", notes="Modem has no sync light.",
                test_type="Auto Diagnose", results=res["results"],
                diagnosis=res["diagnosis"], overall=res["overall"]))
            assert r.status == 201
            rep = await r.json()
            assert rep["job"] == "WO-48213" and rep["device"]["serial"] == "SIM-000001"
            assert rep["provenance"] == ["simulated"] and rep["corrective_actions"]

            listing = await (await c.get("/api/reports")).json()
            assert [x["id"] for x in listing] == [rep["id"]]

            text = await (await c.get(f"/api/reports/{rep['id']}/export.csv")).text()
            rows = list(csv.DictReader(io.StringIO(text)))
            assert {r["test"] for r in rows} >= {"Cable Test", "Internet"}
            assert all(r["job"] == "WO-48213" and r["provenance"] == "simulated" for r in rows)

            pdf = await (await c.get(f"/api/reports/{rep['id']}/export.pdf")).read()
            assert pdf[:5] == b"%PDF-" and len(pdf) > 2000

            assert (await c.get("/api/reports/..%2Fetc/export.csv")).status == 404
            await c.delete(f"/api/reports/{rep['id']}")
            assert await (await c.get("/api/reports")).json() == []
        finally:
            await c.close()
    run(go())


def test_scenario_switch_and_single_tool(tmp_path):
    async def go():
        c = await _client(tmp_path)
        try:
            sc = await (await c.get("/api/sim/scenarios")).json()
            assert sc["current"] == "healthy" and len(sc["scenarios"]) >= 15
            assert (await c.post("/api/sim/scenario", json=dict(id="nope"))).status == 400
            await c.post("/api/sim/scenario", json=dict(id="short"))
            job = await _job(c, "cable")
            assert job["result"]["overall"] == "FAIL"
            assert (await c.post("/api/jobs", json=dict(tool="rm -rf"))).status == 400
            a = await (await c.post("/api/assistant",
                                    json=dict(results=job["result"]["results"]))).json()
            assert a["local"]["layer"] == "cable" and a["cloud"] is None
            a = await (await c.post("/api/assistant", json=dict(
                results=job["result"]["results"], cloud=True))).json()
            assert a["cloud"] is None and "not configured" in a["cloud_error"]
        finally:
            await c.close()
    run(go())


def test_report_ids_are_unique_and_pdf_marks_simulated(tmp_path):
    st = rstore.ReportStore(tmp_path)
    res = autodiag.run(SimHal("healthy"))
    a = st.save(rstore.build_report({"serial": "X"}, "Auto", res["results"], job="WO 1/2"))
    b = st.save(rstore.build_report({"serial": "X"}, "Auto", res["results"], job="WO 1/2"))
    assert a["id"] != b["id"] and len(st.list()) == 2
    with pytest.raises(KeyError):
        st.load("../../etc/passwd")
    assert b"%PDF-" in rstore.to_pdf(a)[:8]


def test_coproc_frame_vectors_and_resync():
    # Same vectors as firmware/coproc/test_host.c
    assert cp.crc16(b"123456789") == 0x29B1
    assert cp.encode(cp.CMD_PING, 1).hex() == "7e000101" + f"{cp.crc16(bytes([0, 1, 1])):04x}"
    f = cp.encode(cp.CMD_RELAY, 7, bytes([cp.RELAY_TEST]))
    assert f.hex() == "7e01130701" + f"{cp.crc16(bytes([1, 0x13, 7, 1])):04x}"
    noise = b"\x00\x7e\xff\x10"
    frame, rest = cp.decode(noise + f + b"\x7e")
    assert frame == (cp.CMD_RELAY, 7, b"\x01")
    assert cp.decode(f[:-1])[0] is None  # incomplete frame waits for more bytes
    bad = bytearray(f)
    bad[4] ^= 0xFF
    assert cp.decode(bytes(bad))[0] is None  # CRC failure is dropped


def test_coproc_wiremap_packing_roundtrip():
    from netscope.cable.model import CableModel, simulate_matrix
    m = simulate_matrix(CableModel(30, shorts=[(1, 2)]))
    back = cp.unpack_wiremap(cp.pack_wiremap(m))
    for a in range(8):
        for b in range(8):
            if m[a][b] is None:
                assert back[a][b] is None
            else:
                assert abs(back[a][b] - m[a][b]) <= 0.5


def test_coproc_client_over_fake_port():
    class Port:
        def __init__(self): self.out = b""
        def write(self, data):
            (cmd, seq, _), _ = cp.decode(data)
            self.out += cp.encode(cp.CMD_KEY, 0, b"\x01")  # unsolicited event first
            if cmd == cp.CMD_WIREMAP:
                self.out += cp.encode(cp.CMD_ERROR, seq, bytes([3]))
            else:
                self.out += cp.encode(cmd, seq, b"ok")
        def read(self, n):
            d, self.out = self.out[:n], self.out[n:]
            return d
    c = cp.Coproc(Port())
    assert c.request(cp.CMD_PING) == b"ok"
    with pytest.raises(cp.ProtoError, match="unsafe voltage"):
        c.request(cp.CMD_WIREMAP)
