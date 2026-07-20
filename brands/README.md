# Brand assets

Home Assistant shows an integration's icon/logo from the central
[`home-assistant/brands`](https://github.com/home-assistant/brands) repository —
a custom integration cannot ship its own UI icon directly. Until these are
merged into `brands`, Home Assistant shows a generic placeholder ("icon not
available").

## Files

`custom_integrations/tesla_solar/`
- `icon.png`    — 256×256
- `icon@2x.png` — 512×512
- `logo.png`    — 256×256
- `logo@2x.png` — 512×512

(`generate_icon.py` reproduces them with Pillow.)

## Submit

1. Fork `home-assistant/brands`.
2. Copy `brands/custom_integrations/tesla_solar/` from this repo into the
   `custom_integrations/` folder of your `brands` fork.
3. Open a PR. Once merged, the icon appears in Home Assistant and HACS
   automatically — no change to this integration is needed.
