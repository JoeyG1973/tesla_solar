"""DataUpdateCoordinator for Tesla Solar (Fleet).

Solar totals are pulled from the Fleet API ``calendar_history`` endpoint. That
endpoint only accepts a single ``period`` per request, but each period's
response nests the next-finer granularity:

* ``period=month``  -> one bucket per day   -> last bucket = *today*,
                                                sum          = *this month*
* ``period=lifetime`` -> one bucket per year -> last bucket = *this year*,
                                                sum          = *lifetime*

So all four sensor values are covered by just **two** API calls per full
refresh instead of four. The "today/this month" call runs every cycle; the
slower "this year/lifetime" call runs every ``slow_every`` cycles.

Two failure modes are handled separately, because they look nothing alike:

* **The call fails.** Tolerated for a few cycles (transient 5xx on
  ``calendar_history`` are common), then escalated to ``UpdateFailed`` so the
  entities go unavailable instead of publishing frozen last-known values.
* **The call succeeds and the data is stale.** When a site stops reporting to
  Tesla, ``calendar_history`` keeps returning HTTP 200 with a full set of
  buckets whose trailing entries are simply zero. Nothing about the response
  is an error. The only reliable signal is the age of the most recent bucket
  that actually contains production -- see :attr:`last_production`.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    API_BASE,
    CONF_MONTHLY_BUDGET,
    CONF_SITE_ID,
    CONF_STALE_AFTER_HOURS,
    DEFAULT_MONTHLY_BUDGET,
    DEFAULT_STALE_AFTER_HOURS,
    DOMAIN,
    MAX_CONSECUTIVE_FAILURES,
    MAX_FAST_INTERVAL,
    MAX_RETRIES,
    MIN_FAST_INTERVAL,
    PERIODS,
    RETRY_BACKOFF,
    RETRY_STATUSES,
    SECONDS_PER_MONTH,
    SLOW_TARGET_INTERVAL,
    SOLAR_FIELD,
    TIMESTAMP_FIELD,
)

_LOGGER = logging.getLogger(__name__)


def compute_schedule(monthly_budget: int) -> tuple[int, int, float]:
    """Turn a monthly call budget into (fast_interval_s, slow_every, est_calls).

    Two calls exist: a *fast* one (today + this month) run every cycle, and a
    *slow* one (this year + lifetime) run every ``slow_every`` cycles. We give
    the slow call a modest fixed share (~4x/day, capped at a third of the
    budget) and spend the rest on the fast call.
    """
    budget = max(1, int(monthly_budget))
    # Slow call: aim for ~SLOW_TARGET_INTERVAL cadence, but never more than a
    # third of the whole budget.
    slow_per_month = min(SECONDS_PER_MONTH / SLOW_TARGET_INTERVAL, budget / 3.0)
    slow_per_month = max(1.0, slow_per_month)
    fast_per_month = max(1.0, budget - slow_per_month)

    fast_interval = SECONDS_PER_MONTH / fast_per_month
    fast_interval = min(max(fast_interval, MIN_FAST_INTERVAL), MAX_FAST_INTERVAL)

    slow_target = SECONDS_PER_MONTH / slow_per_month
    slow_every = max(1, round(slow_target / fast_interval))

    # Recompute the realized monthly call count after clamping/rounding.
    actual_fast = SECONDS_PER_MONTH / fast_interval
    est_calls = actual_fast + actual_fast / slow_every
    return int(round(fast_interval)), int(slow_every), est_calls


class TeslaSolarCoordinator(DataUpdateCoordinator[dict[str, float]]):
    """Fetch solar generation totals from the Tesla Fleet API."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, session: OAuth2Session
    ) -> None:
        """Initialize the coordinator."""
        budget = int(entry.options.get(CONF_MONTHLY_BUDGET, DEFAULT_MONTHLY_BUDGET))
        fast_interval, slow_every, est_calls = compute_schedule(budget)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=fast_interval),
        )
        self.entry = entry
        self._session = session
        self._client = async_get_clientsession(hass)
        self._site_id: str | None = entry.data.get(CONF_SITE_ID)
        self._slow_every = slow_every
        self._cycle = 0
        self.monthly_budget = budget
        self.estimated_monthly_calls = est_calls

        # Health tracking. These drive the diagnostic entities; without them a
        # frozen feed is indistinguishable from a working one.
        self._consecutive_failures = 0
        self.last_successful_update: datetime | None = None
        self.last_production: datetime | None = None
        self.last_error: str | None = None

        _LOGGER.info(
            "Tesla Solar schedule: budget=%s/mo -> fast every %ss, slow every %s "
            "cycles (~%s calls/mo)",
            budget,
            fast_interval,
            slow_every,
            int(round(est_calls)),
        )
        # Retain the last-known value for each metric so buckets survive cycles
        # where they are not refetched.
        self.data = {p: None for p in PERIODS}

    # --- health -------------------------------------------------------------

    @property
    def stale_after(self) -> timedelta:
        """How old the newest production bucket may get before it is stale."""
        hours = int(
            self.entry.options.get(
                CONF_STALE_AFTER_HOURS, DEFAULT_STALE_AFTER_HOURS
            )
        )
        return timedelta(hours=hours)

    @property
    def data_age(self) -> timedelta | None:
        """Age of the most recent bucket that contained production."""
        if self.last_production is None:
            return None
        return dt_util.utcnow() - self.last_production

    @property
    def is_stale(self) -> bool:
        """True when Tesla is answering but the site has stopped reporting."""
        age = self.data_age
        return age is not None and age > self.stale_after

    @property
    def has_problem(self) -> bool:
        """True when the data cannot be trusted, for any reason."""
        return self.is_stale or not self.last_update_success

    # --- transport ----------------------------------------------------------

    async def _async_token(self) -> str:
        """Return a valid access token, refreshing via HA if needed."""
        try:
            await self._session.async_ensure_token_valid()
        except Exception as err:  # noqa: BLE001 - surface as reauth
            raise ConfigEntryAuthFailed(f"Token refresh failed: {err}") from err
        return self._session.token["access_token"]

    async def _api_get(self, path: str, token: str) -> dict[str, Any]:
        """Perform an authenticated GET against the Fleet API.

        Gateway-class statuses get one bounded retry: Tesla's
        ``calendar_history`` endpoint 504s intermittently and a single retry
        clears most of them. Auth failures are never retried -- they are
        raised straight through so Home Assistant opens a reauth flow.
        """
        attempt = 0
        while True:
            async with self._client.get(
                f"{API_BASE}{path}",
                headers={"Authorization": f"Bearer {token}"},
            ) as resp:
                if resp.status in (401, 403):
                    raise ConfigEntryAuthFailed(
                        f"Unauthorized ({resp.status}) for {path}"
                    )
                if resp.status == 200:
                    return await resp.json()
                text = await resp.text()
                status = resp.status

            if status in RETRY_STATUSES and attempt < MAX_RETRIES:
                attempt += 1
                _LOGGER.debug(
                    "Tesla Solar: HTTP %s for %s, retry %s/%s in %ss",
                    status,
                    path,
                    attempt,
                    MAX_RETRIES,
                    RETRY_BACKOFF,
                )
                await asyncio.sleep(RETRY_BACKOFF)
                continue

            raise UpdateFailed(f"HTTP {status} for {path}: {text[:200]}")

    async def _async_resolve_site(self, token: str) -> str:
        """Find and cache the first energy_site_id on the account."""
        if self._site_id:
            return self._site_id
        data = await self._api_get("/api/1/products", token)
        for item in data.get("response", []):
            site = item.get("energy_site_id")
            if site is not None:
                self._site_id = str(site)
                # Persist so we skip the lookup next time.
                self.hass.config_entries.async_update_entry(
                    self.entry, data={**self.entry.data, CONF_SITE_ID: self._site_id}
                )
                return self._site_id
        raise UpdateFailed("No energy site found on this Tesla account")

    async def _fetch_series(
        self, token: str, site_id: str, period: str
    ) -> list[dict[str, Any]]:
        """Return the raw time_series list for a calendar_history period."""
        data = await self._api_get(
            f"/api/1/energy_sites/{site_id}/calendar_history"
            f"?kind=energy&period={period}",
            token,
        )
        return data.get("response", {}).get("time_series", []) or []

    # --- parsing ------------------------------------------------------------

    @staticmethod
    def _bucket_wh(entry: dict[str, Any]) -> float:
        """Raw solar generation (watt-hours) for one time_series bucket."""
        try:
            return float(entry.get(SOLAR_FIELD, 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _bucket_kwh(cls, entry: dict[str, Any]) -> float:
        """Solar generation (kWh) for one time_series bucket."""
        return round(cls._bucket_wh(entry) / 1000, 3)

    @classmethod
    def _sum_kwh(cls, series: list[dict[str, Any]]) -> float:
        """Total solar generation (kWh) across a time_series."""
        return round(sum(cls._bucket_kwh(e) for e in series), 3)

    @classmethod
    def _latest_production(
        cls, series: list[dict[str, Any]]
    ) -> datetime | None:
        """Start time of the newest bucket that actually contains production.

        Trailing zero buckets are the fingerprint of a site that has stopped
        reporting, so they are deliberately skipped rather than treated as
        "we have data for today".
        """
        for entry in reversed(series):
            if cls._bucket_wh(entry) <= 0:
                continue
            raw = entry.get(TIMESTAMP_FIELD)
            if not raw:
                return None
            parsed = dt_util.parse_datetime(str(raw))
            if parsed is None:
                return None
            return dt_util.as_utc(parsed)
        return None

    # --- refresh ------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, float]:
        """Fetch solar totals: 'month' call every cycle, 'lifetime' periodically."""
        token = await self._async_token()
        site_id = await self._async_resolve_site(token)

        result = dict(self.data)  # start from last-known values
        run_slow = self._cycle % self._slow_every == 0
        self._cycle += 1

        # Fast call: period=month -> daily buckets. Last bucket = today,
        # full sum = this month.
        try:
            month_series = await self._fetch_series(token, site_id, "month")
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:  # noqa: BLE001
            self._consecutive_failures += 1
            self.last_error = str(err)
            if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                # Stop serving last-known values as if they were current. The
                # entities go unavailable, which is the honest state.
                raise UpdateFailed(
                    f"{self._consecutive_failures} consecutive failures fetching "
                    f"month/day; last error: {err}"
                ) from err
            _LOGGER.warning(
                "Tesla Solar: failed to fetch month/day "
                "(%s/%s consecutive, serving last-known values): %s",
                self._consecutive_failures,
                MAX_CONSECUTIVE_FAILURES,
                err,
            )
        else:
            self._consecutive_failures = 0
            self.last_error = None
            self.last_successful_update = dt_util.utcnow()
            if month_series:
                result["month"] = self._sum_kwh(month_series)
                result["day"] = self._bucket_kwh(month_series[-1])
                latest = self._latest_production(month_series)
                if latest is not None and (
                    self.last_production is None or latest > self.last_production
                ):
                    self.last_production = latest

        # Slow call: period=lifetime -> yearly buckets. Last bucket = this year,
        # full sum = lifetime. A failure here never fails the whole refresh --
        # these two values legitimately go many cycles without a fetch.
        if run_slow:
            try:
                life_series = await self._fetch_series(token, site_id, "lifetime")
                if life_series:
                    result["lifetime"] = self._sum_kwh(life_series)
                    result["year"] = self._bucket_kwh(life_series[-1])
            except ConfigEntryAuthFailed:
                raise
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Tesla Solar: failed to fetch year/lifetime: %s", err)

        if self.is_stale:
            _LOGGER.warning(
                "Tesla Solar: API is responding but the site has not reported "
                "production since %s (%s h ago, threshold %s h). Check that the "
                "gateway is online.",
                self.last_production,
                round((self.data_age or timedelta()).total_seconds() / 3600, 1),
                int(self.stale_after.total_seconds() // 3600),
            )

        return result
