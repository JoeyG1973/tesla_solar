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

# Seconds in a nominal 30-day month, used to convert a monthly call budget into
# a polling interval.
SECONDS_PER_MONTH = 30 * 24 * 3600  # 2,592,000

# Guardrails on the derived fast-poll interval (seconds).
MIN_FAST_INTERVAL = 300      # never poll "today" more often than every 5 min
MAX_FAST_INTERVAL = 86400    # never slower than once a day
# Target cadence for the slow (year/lifetime) call; the actual cadence is
# rounded to a whole number of fast cycles.
SLOW_TARGET_INTERVAL = 6 * 3600  # ~4x/day
