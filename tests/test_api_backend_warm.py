"""ApiBackend's first-call warm gate: instructor registers provider/mode handlers
lazily on the first call, so concurrent first calls race it ("Available modes: []" —
seen live on `audit <dir>`, whose fan-out makes the very first calls concurrent).
The gate serializes until one call succeeds, then runs fully concurrent."""

from __future__ import annotations

import threading
import time

import pytest

from temper_skills.backends.api import ApiBackend


def _backend(monkeypatch, fake):
    be = ApiBackend()
    monkeypatch.setattr(be, "_complete", fake)
    return be


def test_first_call_runs_alone_then_the_rest_fan_out(monkeypatch):
    events, ev_lock = [], threading.Lock()

    def fake(system, user, schema):
        with ev_lock:
            events.append("start")
        time.sleep(0.03)
        with ev_lock:
            events.append("end")
        return "ok"

    be = _backend(monkeypatch, fake)
    threads = [threading.Thread(target=lambda: be.complete("s", "u", None)) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(events) == 12
    # the gated first call fully completes before any other call starts …
    assert events[:2] == ["start", "end"]
    # … and the remaining five DO overlap (the gate must not serialize forever)
    tail = events[2:]
    max_active = active = 0
    for e in tail:
        active += 1 if e == "start" else -1
        max_active = max(max_active, active)
    assert max_active > 1


def test_failed_first_call_does_not_mark_warm(monkeypatch):
    calls = []

    def fake(system, user, schema):
        calls.append(1)
        raise RuntimeError("boom")

    be = _backend(monkeypatch, fake)
    with pytest.raises(RuntimeError):
        be.complete("s", "u", None)
    assert be._warmed is False  # the next caller becomes the warmer
