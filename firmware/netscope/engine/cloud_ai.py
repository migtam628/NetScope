"""Optional cloud AI analysis.

Off unless the owner configures an endpoint and key.  The device is fully
usable without it: engine/rules.py is the default assistant and is always
shown; a cloud answer is added alongside it, never instead of it.

Privacy: only test results are sent.  Reports can contain internal IPs,
switch names and VLANs, so `redact()` masks them unless the owner turns
redaction off.  Nothing is sent without an explicit tap on "Ask AI".

Config (environment or /etc/netscope/ai.env):
  NETSCOPE_AI_URL    Anthropic-Messages-compatible endpoint
  NETSCOPE_AI_KEY    API key
  NETSCOPE_AI_MODEL  model id
  NETSCOPE_AI_REDACT 1 (default) or 0

STATUS: request builder and redaction are unit-tested; the HTTP call has
not been exercised against a live endpoint from this repository.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

SYSTEM = (
    "You are a network field-service assistant. You are given structured test results from "
    "a handheld tester. Explain the most likely fault in plain technical language, give a "
    "short ordered repair procedure, and write a brief work-order completion note. Only "
    "reason from the measurements given; say so when the data is insufficient. Results "
    "marked NOT_TESTED were not measured. Never claim a cable is certified.")


def configured() -> bool:
    return bool(os.environ.get("NETSCOPE_AI_URL") and os.environ.get("NETSCOPE_AI_KEY")
                and os.environ.get("NETSCOPE_AI_MODEL"))


_IP = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b")
_MAC = re.compile(r"\b([0-9a-f]{2}:){5}[0-9a-f]{2}\b", re.I)
_PUBLIC_OK = {"1.1.1.1", "8.8.8.8", "9.9.9.9"}


_NAME_KEYS = ("system_name", "ssid", "domain", "serial", "chassis_id", "port_description")


def redact(payload: dict) -> dict:
    """Mask host parts of IPs, MACs and site names; keep structure and numbers.

    Names are collected from their fields first and then removed everywhere,
    because the same switch name also appears inside summary sentences.
    """
    names: set[str] = set()

    def collect(v, key=""):
        if isinstance(v, dict):
            for k, x in v.items():
                collect(x, k)
        elif isinstance(v, list):
            for x in v:
                collect(x, key)
        elif isinstance(v, str) and key in _NAME_KEYS and len(v) >= 3:
            names.add(v)
    collect(payload)
    ordered = sorted(names, key=len, reverse=True)

    def fix(s: str) -> str:
        for n in ordered:
            s = s.replace(n, "<redacted>")
        s = _IP.sub(lambda m: m.group(0) if m.group(0) in _PUBLIC_OK
                    else f"{m.group(1)}.x.x.{m.group(4)}", s)
        return _MAC.sub(lambda m: m.group(0)[:8] + ":xx:xx:xx", s)

    def walk(v):
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return fix(v) if isinstance(v, str) else v
    return walk(payload)


def build_request(results: list[dict], local_diagnosis: dict | None) -> dict:
    body = dict(results=[{k: r[k] for k in ("title", "status", "summary", "measurements",
                                           "findings", "provenance")} for r in results],
                local_rules_diagnosis=local_diagnosis)
    if os.environ.get("NETSCOPE_AI_REDACT", "1") != "0":
        body = redact(body)
    return dict(model=os.environ.get("NETSCOPE_AI_MODEL", ""), max_tokens=900, system=SYSTEM,
                messages=[dict(role="user", content=json.dumps(body, separators=(",", ":")))])


def analyse(results: list[dict], local_diagnosis: dict | None, timeout: float = 30.0) -> str:
    if not configured():
        raise RuntimeError("Cloud AI is not configured on this device.")
    req = urllib.request.Request(
        os.environ["NETSCOPE_AI_URL"],
        data=json.dumps(build_request(results, local_diagnosis)).encode(),
        headers={"content-type": "application/json", "x-api-key": os.environ["NETSCOPE_AI_KEY"],
                 "anthropic-version": "2023-06-01"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
