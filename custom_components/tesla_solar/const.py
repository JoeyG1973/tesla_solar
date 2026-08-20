"""Constants for the Tesla Solar (Fleet) integration."""

DOMAIN = "tesla_solar"

# Tesla Fleet OAuth2 endpoints (region-independent auth server)
OAUTH2_AUTHORIZE = "https://auth.tesla.com/oauth2/v3/authorize"
OAUTH2_TOKEN = "https://auth.tesla.com/oauth2/v3/token"

# Scope needed to read energy-site (solar/Powerwall) data.
SCOPE = "openid offline_access energy_device_data"

# North America / Asia-Pacific Fleet API host. This is also the OAuth "audience".
# (EU users would use fleet-api.prd.eu.vn.cloud.tesla.com)
API_BASE = "https://fleet-api.prd.na.vn.cloud.tesla.com"
AUDIENCE = API_BASE

# Config entry keys
CONF_SITE_ID = "site_id"

# Options
CONF_MONTHLY_BUDGET = "monthly_call_budget"
# Fleet API "data request" free allowance is 5,000/month ($10 discount).
# Default leaves comfortable headroom (and room for the official Tesla Fleet
# integration if it is still installed alongside this one).
DEFAULT_MONTHLY_BUDGET = 3000
MIN_MONTHLY_BUDGET = 60
MAX_MONTHLY_BUDGET = 5000

# The four sensor "periods" we expose (these are metric keys, not raw API
# periods -- see the coordinator for how they map onto calendar_history calls).
PERIODS = ("day", "month", "year", "lifetime")

# Field in each time_series entry that represents solar generation (watt-hours)
SOLAR_FIELD = "solar_energy_exported"

# Field in each time_series entry carrying the bucket's start time (ISO 8601).
TIMESTAMP_FIELD = "timestamp"

# Seconds in a nominal 30-day month, used to convert a monthly call budget into
# a polling interval.
SECONDS_PER_MONTH = 30 * 24 * 3600  # 2,592,000

# Guardrails on the derived fast-poll interval (seconds).
MIN_FAST_INTERVAL = 300      # never poll "today" more often than every 5 min
MAX_FAST_INTERVAL = 86400    # never slower than once a day
# Target cadence for the slow (year/lifetime) call; the actual cadence is
# rounded to a whole number of fast cycles.
SLOW_TARGET_INTERVAL = 6 * 3600  # ~4x/day

# --- Failure and staleness handling -----------------------------------------
#
# Two independent failure modes, and they need different detectors:
#
# 1. The call fails (5xx, timeout, network). Tolerating a blip is right, but
#    tolerating it forever means the sensors keep publishing last-known values
#    that look plausible and are silently frozen. After this many consecutive
#    failures of the fast call we raise UpdateFailed so the entities go
#    unavailable and the failure becomes visible.
MAX_CONSECUTIVE_FAILURES = 3

# 2. The call SUCCEEDS and the data is stale. calendar_history returns a full
#    set of daily buckets for the period even when the site has stopped
#    reporting -- the trailing buckets are simply zero. HTTP 200 is therefore
#    NOT proof the data is current, and no amount of error handling will catch
#    it. The only reliable signal is the age of the most recent bucket that
#    actually contains production.
CONF_STALE_AFTER_HOURS = "stale_after_hours"
DEFAULT_STALE_AFTER_HOURS = 36
MIN_STALE_AFTER_HOURS = 12
MAX_STALE_AFTER_HOURS = 168

# Bounded retry for gateway-class errors on calendar_history, which 504s
# intermittently. Each retry spends one call from the monthly budget, so keep
# it small.
RETRY_STATUSES = (429, 500, 502, 503, 504)
MAX_RETRIES = 1
RETRY_BACKOFF = 3.0  # seconds before the single retry
