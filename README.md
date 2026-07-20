# Tesla Solar (Fleet)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Validate](https://github.com/JoeyG1973/tesla_solar/actions/workflows/validate.yml/badge.svg)](https://github.com/JoeyG1973/tesla_solar/actions/workflows/validate.yml)

A lightweight Home Assistant custom integration that reports **solar generation
totals** — today, this month, this year, and lifetime — for a Tesla energy
site, pulled directly from the Tesla **Fleet API** `calendar_history` endpoint.

It handles its own OAuth2 login and token refresh through Home Assistant, so it
does **not** depend on the official Tesla Fleet integration and needs no
`command_line` scripts.

## Why

The official Tesla Fleet integration exposes **daily** energy sensors that reset
at midnight, but no month/year/lifetime totals. This integration asks the Fleet
API for each period directly, so the numbers match the Tesla app exactly and are
self-correcting (no accumulation drift).

It's also efficient: because each `calendar_history` period response nests the
next-finer granularity, all four totals are fetched in just **two** API calls
per refresh (`month` → today + this month, `lifetime` → this year + lifetime)
rather than four.

## Sensors

| Entity | Description |
| --- | --- |
| `sensor.tesla_solar_solar_today` | Solar generated today (kWh) |
| `sensor.tesla_solar_solar_this_month` | Solar generated this month (kWh) |
| `sensor.tesla_solar_solar_this_year` | Solar generated this year (kWh) |
| `sensor.tesla_solar_solar_lifetime` | Lifetime solar generation (kWh) |

## Install (HACS)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=JoeyG1973&repository=tesla_solar&category=integration)

1. In HACS → **⋮** → **Custom repositories**, add
   `https://github.com/JoeyG1973/tesla_solar` with category **Integration**
   (or use the button above).
2. Install **Tesla Solar (Fleet)**, then restart Home Assistant.

## Setup

1. You need a Tesla developer application (Client ID + Secret) with the
   `energy_device_data` scope — the same app the official Tesla Fleet
   integration uses. Reuse those credentials.
2. **Settings → Devices & Services → Add Integration → Tesla Solar (Fleet)**.
3. On first use, Home Assistant asks for **Application Credentials** — paste your
   Client ID and Secret.
4. Complete the Tesla OAuth login. Four solar sensors appear.

## Polling budget

Under the integration's **Configure** button you can set a **monthly Fleet API
call budget**. The integration auto-tunes its polling from that number: the
`today`/`this month` call runs frequently and the slower `this year`/`lifetime`
call runs less often. At the default of 3,000 calls/month, `today` refreshes
about every 15 minutes and the yearly/lifetime totals about every 6 hours — well
inside the Fleet API's free allowance of 5,000 data requests/month.

## Region

Defaults to the North America / Asia-Pacific Fleet API host. EU users should
change `API_BASE`/`AUDIENCE` in `const.py` to
`https://fleet-api.prd.eu.vn.cloud.tesla.com`.

## Roadmap

- Live solar power, grid import/export, home usage, and battery sensors
  (the `calendar_history` response already contains these fields).
- Options-flow selector for region (EU host).

## Icon / brand

The integration's icon lives in Home Assistant's central
[`home-assistant/brands`](https://github.com/home-assistant/brands) repository;
custom integrations can't ship their own UI icon directly. Ready-to-submit
assets (a solar sun-over-panel icon) are in
[`brands/custom_integrations/tesla_solar/`](brands/custom_integrations/tesla_solar).
See [`brands/README.md`](brands/README.md) for the one-time submission steps that
make the icon show up in Home Assistant and HACS.

## License

[MIT](LICENSE)
