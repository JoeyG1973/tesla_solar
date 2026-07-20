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
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_BASE,
    CONF_MONTHLY_BUDGET,
    CONF_SITE_ID,
    DEFAULT_MONTHLY_BUDGET,
    DOMAIN,
    MAX_FAST_INTERVAL,
    MIN_FAST_INTERVAL,
    PERIODS,
    SECONDS_PER_MONTH,
    SLOW_TARGET_INTERVAL,
    SOLAR_FIELD,
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

    async def _async_token(self) -> str:
        """Return a valid access token, refreshing via HA if needed."""
        try:
            await self._session.async_ensure_token_valid()
        except Exception as err:  # noqa: BLE001 - surface as reauth
            raise ConfigEntryAuthFailed(f"Token refresh failed: {err}") from err
        return self._session.token["access_token"]

    async def _api_get(self, path: str, token: str) -> dict[str, Any]:
        """Perform an authenticated GET against the Fleet API."""
        async with self._client.get(
            f"{API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            if resp.status in (401, 403):
                raise ConfigEntryAuthFailed(f"Unauthorized ({resp.status}) for {path}")
            if resp.status != 200:
                text = await resp.text()
                raise UpdateFailed(f"HTTP {resp.status} for {path}: {text[:200]}")
            return await resp.json()

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

    @staticmethod
    def _bucket_kwh(entry: dict[str, Any]) -> float:
        """Solar generation (kWh) for one time_series bucket."""
        return round(float(entry.get(SOLAR_FIELD, 0) or 0) / 1000, 3)

    @classmethod
    def _sum_kwh(cls, series: list[dict[str, Any]]) -> float:
        """Total solar generation (kWh) across a time_series."""
        return round(sum(cls._bucket_kwh(e) for e in series), 3)

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
            if month_series:
                result["month"] = self._sum_kwh(month_series)
                result["day"] = self._bucket_kwh(month_series[-1])
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Tesla Solar: failed to fetch month/day: %s", err)

        # Slow call: period=lifetime -> yearly buckets. Last bucket = this year,
        # full sum = lifetime.
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

        return result
