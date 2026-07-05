# PWEB Amano — Home Assistant Integration

[![Built with Claude Code](https://img.shields.io/badge/Built%20with%20Claude%20Code-D97757?style=for-the-badge&logo=claude&logoColor=white)](https://claude.ai/code)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-41BDF5?style=for-the-badge&logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5?style=for-the-badge&logo=homeassistantcommunitystore&logoColor=white)](https://hacs.xyz/)
[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

A Home Assistant custom integration for **PWEB** (아마노코리아 관리사무소 시스템) apartment/officetel management portals — sites like `https://a12345.pweb.kr`. These portals have no public API, so this integration logs in with your ID/password and parses the site's HTML.

## Status

The discount (할인) screens are implemented: balance, registration history, and on-demand actions for whichever vehicle is currently parked. General dashboard data (notices, management fees, etc.) is out of scope for now — that page's layout hasn't been inspected. See `AGENTS.md` for details.

Entities polled every 5 minutes:

- **Last sync** — timestamp of the last successful login + fetch.
- **Discount balance** — remaining discount balance (KRW).
- **Discount registration status** — plus an `available_discount_types` attribute listing the site's full admin-configured discount catalog.
- **Refresh** button — forces an immediate poll.

Optionally, tracking specific car plates (via setup or Settings → Devices & Services → PWEB Amano → Configure) also gives each plate its own device with:

- **Parking history** calendar — spans each visit's actual entry→exit duration.
- **Vehicle entry/exit** event — "entry" fires the first time a registration for that plate is seen; "exit" fires in real time when the vehicle is marked as having left.

Two services are available for on-demand actions:

- **`pweb_amano.register_discount`** — registers a discount type for a currently-parked vehicle (by plate; not limited to your own tracked cars).
- **`pweb_amano.list_unregistered_vehicles`** — lists currently-parked vehicles that don't have a discount registered yet.

## Installation (HACS)

1. HACS → Integrations → ⋮ → Custom repositories → add this repo as an "Integration".
2. Install **PWEB Amano**, restart Home Assistant.
3. Settings → Devices & Services → Add Integration → **PWEB Amano**.
4. Enter the numeric lot-area code from your portal's address (e.g. `12345` for `a12345.pweb.kr`), confirm the detected site name, then your ID and password.
5. Optionally list car plates to track right away — this can also be added or edited later via Configure.

## Development

```bash
scripts/setup     # first time — installs HA + deps into config/
scripts/develop   # boots HA on :8123 with this integration mounted
```

## Security note

Your password is hashed (SHA-256) client-side before being sent to the portal, matching the site's own login page behavior. It is never logged or stored in plaintext beyond the config entry.
