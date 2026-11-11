"""Result model shared by the engine, the API, the UI and the report store.

Every result carries its provenance ("simulated", "host", "hardware") so that
simulated data can never be mistaken for a field measurement.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    NOT_TESTED = "NOT_TESTED"


_RANK = {Status.NOT_TESTED: 0, Status.PASS: 1, Status.WARNING: 2, Status.FAIL: 3}


def worst(statuses) -> Status:
    """FAIL > WARNING > PASS > NOT_TESTED; an empty list is NOT_TESTED."""
    return max(statuses, key=_RANK.__getitem__, default=Status.NOT_TESTED)


@dataclass
class TestResult:
    __test__ = False  # not a pytest class

    test_id: str
    title: str
    status: Status = Status.NOT_TESTED
    summary: str = ""
    measurements: dict = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    provenance: str = "unknown"
    duration_s: float = 0.0
    started: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return dict(test_id=self.test_id, title=self.title, status=self.status.value,
                    summary=self.summary, measurements=self.measurements,
                    findings=list(self.findings), recommendations=list(self.recommendations),
                    provenance=self.provenance, duration_s=self.duration_s, started=self.started)

    @classmethod
    def from_dict(cls, d: dict) -> "TestResult":
        return cls(test_id=d["test_id"], title=d.get("title", d["test_id"]),
                   status=Status(d.get("status", "NOT_TESTED")), summary=d.get("summary", ""),
                   measurements=dict(d.get("measurements") or {}),
                   findings=list(d.get("findings") or []),
                   recommendations=list(d.get("recommendations") or []),
                   provenance=d.get("provenance", "unknown"),
                   duration_s=float(d.get("duration_s") or 0.0),
                   started=float(d.get("started") or time.time()))


def not_tested(test_id: str, title: str, why: str, provenance: str = "unknown") -> TestResult:
    return TestResult(test_id, title, Status.NOT_TESTED, f"Not tested: {why}",
                      provenance=provenance)
