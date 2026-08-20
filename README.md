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

### Health diagnostics

| Entity | Description |
| --- | --- |
| `binary_sensor.tesla_solar_data_problem` | On when the figures should not be trusted — the API is failing, **or** it is succeeding while the site has stopped reporting |
| `sensor.tesla_solar_last_reported_production` | Start of the most recent bucket that actually contained production |
| `sensor.tesla_solar_last_successful_update` | Last time the `month` call returned 200 |

## Detecting a frozen feed

This is worth understanding, because the failure is silent by design.

When an energy site stops reporting to Tesla — gateway unplugged, network
outage, dead cellular backhaul — `calendar_history` **keeps returning HTTP
200**. The response still contains a full set of daily buckets; the trailing
ones are simply zero. Nothing about it is an error, so `today` reads `0.0`,
`this month` freezes at whatever the site last reported, and the dashboard
looks entirely healthy.

No amount of error handling catches that. The only reliable signal is the age
of the most recent bucket that contains production, which is what
`sensor.tesla_solar_last_reported_production` exposes and what
`binary_sensor.tesla_solar_data_problem` alarms on (default: no production for
36 h; configurable under **Configure**).

The same sensor also turns on when the coordinator is genuinely failing, so a
single automation covers both cases:

```yaml
automation:
  - alias: Tesla Solar data problem
    trigger:
      - trigger: state
        entity_id: binary_sensor.tesla_solar_data_problem
        to: "on"
        for: "01:00:00"
    action:
      - action: notify.persistent_notification
        data:
          title: Tesla Solar data problem
          message: >
            {{ state_attr('binary_sensor.tesla_solar_data_problem', 'reason') }} —
            last production
            {{ state_attr('binary_sensor.tesla_solar_data_problem',
                          'hours_since_production') }} h ago.
```

Call failures are tolerated for 2 cycles (Tesla's `calendar_history` 504s
intermittently, and each 5xx already gets one automatic retry); on the third
consecutive failure the coordinator raises `UpdateFailed` so the energy
entities go **unavailable** rather than continuing to publish stale values.

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

The same screen sets the **stale-data threshold** in hours (default 36, range
12–168) used by `binary_sensor.tesla_solar_data_problem`. Lower it to catch
outages sooner; raise it if genuinely zero-output days trip it.

## Region

Defaults to the North America / Asia-Pacific Fleet API host. EU users should
change `API_BASE`/`AUDIENCE` in `const.py` to
`https://fleet-api.prd.eu.vn.cloud.tesla.com`.

## Roadmap

- Live solar power, grid import/export, home usage, and battery sensors
  (the `calendar_history` response already contains these fields).
- Options-flow selector for region (EU host).
- Repairs issue (rather than just a binary sensor) when the feed goes stale.

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
