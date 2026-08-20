#!/usr/bin/env python3
"""Regression tests for failure handling and stale-feed detection.

Self-contained: stubs the handful of Home Assistant symbols the coordinator
imports, so it runs anywhere with a plain ``python3 tests/test_staleness.py``
and no dependencies.

Replays the shape of a real incident (2026-08-16 -> 19): the Tesla site stopped
reporting, ``calendar_history`` kept returning HTTP 200 with zeroed trailing
buckets, and every sensor stayed "available" while silently frozen.
"""
from __future__ import annotations

import asyncio
import importlib
import logging
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# --------------------------------------------------------------------------
# Minimal Home Assistant stubs
# --------------------------------------------------------------------------


def _module(name: str, **attrs: object) -> types.ModuleType:
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


class _ConfigEntry:
    def __init__(self, data=None, options=None, entry_id="e1"):
        self.data = data or {}
        self.options = options or {}
        self.entry_id = entry_id

    def __class_getitem__(cls, item):
        return cls


class _ConfigEntryAuthFailed(Exception):
    pass


class _UpdateFailed(Exception):
    pass


class _DataUpdateCoordinator:
    def __init__(self, hass, logger, name=None, update_interval=None):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.last_update_success = True
        self.data = None

    def __class_getitem__(cls, item):
        return cls


class _OAuth2Session:
    def __init__(self):
        self.token = {"access_token": "tok"}

    async def async_ensure_token_valid(self):
        return None


def _utcnow():
    return datetime.now(timezone.utc)


def _parse_datetime(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


_module("homeassistant")
_module("homeassistant.config_entries", ConfigEntry=_ConfigEntry)
_module("homeassistant.core", HomeAssistant=type("HomeAssistant", (), {}))
_module("homeassistant.exceptions", ConfigEntryAuthFailed=_ConfigEntryAuthFailed)
_module("homeassistant.helpers")
_module(
    "homeassistant.helpers.aiohttp_client",
    async_get_clientsession=lambda hass: None,
)
_module(
    "homeassistant.helpers.config_entry_oauth2_flow", OAuth2Session=_OAuth2Session
)
_module(
    "homeassistant.helpers.update_coordinator",
    DataUpdateCoordinator=_DataUpdateCoordinator,
    UpdateFailed=_UpdateFailed,
)
_module("homeassistant.util")
_module(
    "homeassistant.util.dt",
    utcnow=_utcnow,
    parse_datetime=_parse_datetime,
    as_utc=_as_utc,
)

_pkg = types.ModuleType("ts")
_pkg.__path__ = [str(REPO / "custom_components" / "tesla_solar")]
sys.modules["ts"] = _pkg

const = importlib.import_module("ts.const")
coord = importlib.import_module("ts.coordinator")
Coordinator = coord.TeslaSolarCoordinator

# Freeze "now" at the evening of the incident.
NOW = datetime(2026, 8, 19, 21, 26, tzinfo=timezone(timedelta(hours=-4)))
coord.dt_util.utcnow = lambda: NOW.astimezone(timezone.utc)

# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

# kWh per day, Aug 1..16 -- the site stopped reporting after the 16th.
AUGUST = [
    42.17, 37.83, 29.11, 51.17, 28.75, 42.90, 39.32, 43.14,
    47.85, 37.26, 41.00, 41.00, 41.00, 40.51, 47.05, 14.82,
]


def bucket(day: int, kwh: float) -> dict:
    return {
        "timestamp": f"2026-08-{day:02d}T00:00:00-04:00",
        "solar_energy_exported": kwh * 1000,
    }


REPORTED = [bucket(i + 1, v) for i, v in enumerate(AUGUST)]
# What Tesla actually returned: HTTP 200, full month, trailing zeros.
STALLED = REPORTED + [bucket(d, 0.0) for d in (17, 18, 19)]
HEALTHY = REPORTED + [bucket(17, 31.87), bucket(18, 31.84), bucket(19, 43.74)]

_FAILURES: list[str] = []


def check(name: str, got: object, want: object) -> None:
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")
        _FAILURES.append(name)


def make(options: dict | None = None) -> Coordinator:
    entry = _ConfigEntry(data={"site_id": "123"}, options=options or {})
    c = Coordinator.__new__(Coordinator)
    _DataUpdateCoordinator.__init__(c, None, logging.getLogger("test"), name="t")
    c.entry = entry
    c._session = _OAuth2Session()
    c._client = None
    c._site_id = "123"
    c._slow_every = 4
    c._cycle = 0
    c._consecutive_failures = 0
    c.last_successful_update = None
    c.last_production = None
    c.last_error = None
    c.data = {p: None for p in const.PERIODS}
    return c


async def refresh(c: Coordinator, series_or_exc, cycles: int = 1):
    async def fetch(token, site, period):
        if isinstance(series_or_exc, Exception):
            raise series_or_exc
        return series_or_exc if period == "month" else []

    c._fetch_series = fetch
    c._async_token = lambda: asyncio.sleep(0, result="tok")
    c._async_resolve_site = lambda token: asyncio.sleep(0, result="123")
    out = None
    for _ in range(cycles):
        out = await c._async_update_data()
        c.data = out
    return out


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

logging.disable(logging.CRITICAL)

# Parsing
check("month total sums every bucket", Coordinator._sum_kwh(STALLED),
      round(sum(AUGUST), 3))
check("trailing zero bucket reads as 0 kWh today",
      Coordinator._bucket_kwh(STALLED[-1]), 0.0)
check("latest production skips trailing zeros",
      Coordinator._latest_production(STALLED).isoformat(),
      "2026-08-16T04:00:00+00:00")
check("latest production on a healthy series",
      Coordinator._latest_production(HEALTHY).isoformat(),
      "2026-08-19T04:00:00+00:00")
check("empty series -> None", Coordinator._latest_production([]), None)
check("all-zero series -> None",
      Coordinator._latest_production([bucket(1, 0), bucket(2, 0)]), None)
check("unparseable timestamp -> None",
      Coordinator._latest_production(
          [{"timestamp": "nonsense", "solar_energy_exported": 5}]), None)
check("missing field is 0 kWh", Coordinator._bucket_kwh({}), 0.0)
check("null field is 0 kWh",
      Coordinator._bucket_kwh({"solar_energy_exported": None}), 0.0)

# The incident: HTTP 200, stale data
c = make()
res = asyncio.run(refresh(c, STALLED))
check("stalled feed still returns a month total", res["month"],
      round(sum(AUGUST), 3))
check("stalled feed reports today = 0", res["day"], 0.0)
check("stalled feed IS flagged stale", c.is_stale, True)
check("stalled feed sets has_problem", c.has_problem, True)
check("reported age exceeds threshold",
      c.data_age > c.stale_after, True)

healthy = make()
asyncio.run(refresh(healthy, HEALTHY))
check("healthy feed is not stale", healthy.is_stale, False)
check("healthy feed has no problem", healthy.has_problem, False)

lenient = make(options={const.CONF_STALE_AFTER_HOURS: 168})
asyncio.run(refresh(lenient, STALLED))
check("a 168 h threshold tolerates the same data", lenient.is_stale, False)

# Failure escalation
err = _UpdateFailed("HTTP 504 for /api/1/energy_sites/123/calendar_history")
flaky = make()
for _ in range(const.MAX_CONSECUTIVE_FAILURES - 1):
    asyncio.run(refresh(flaky, err))
check("failures below the limit are tolerated", flaky._consecutive_failures,
      const.MAX_CONSECUTIVE_FAILURES - 1)
check("last_error is recorded", "504" in (flaky.last_error or ""), True)

raised = False
try:
    asyncio.run(refresh(flaky, err))
except _UpdateFailed as exc:
    raised = "consecutive" in str(exc)
check("hitting the limit raises UpdateFailed", raised, True)

recovering = make()
asyncio.run(refresh(recovering, err))
asyncio.run(refresh(recovering, HEALTHY))
check("counter resets after a success", recovering._consecutive_failures, 0)
check("last_error clears after a success", recovering.last_error, None)

# last_production must never move backwards
monotonic = make()
asyncio.run(refresh(monotonic, HEALTHY))
newest = monotonic.last_production
asyncio.run(refresh(monotonic, STALLED))
check("last_production is monotonic", monotonic.last_production, newest)

# Scheduling maths is untouched by these changes
check("compute_schedule(3000)", coord.compute_schedule(3000), (900, 24, 3000.0))
check("compute_schedule(60)", coord.compute_schedule(60), (64800, 2, 60.0))

logging.disable(logging.NOTSET)
print()
if _FAILURES:
    print(f"{len(_FAILURES)} FAILED: {', '.join(_FAILURES)}")
    sys.exit(1)
print("all tests passed")
