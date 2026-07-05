# PWEB Amano — Home Assistant Integration

A Home Assistant custom integration for **PWEB** (Amano Korea apartment/officetel management portals) — sites like `https://a12345.pweb.kr`. These portals have no public API, so this integration logs in with your ID/password and parses the site's HTML.

## Status

The discount (할인) screens are implemented: balance, registration history, and on-demand actions for whichever vehicle is currently parked. General dashboard data (notices, management fees, etc.) is out of scope for now — that page's layout hasn't been inspected.

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

## Security

Your password is hashed (SHA-256) client-side before being sent to the portal, matching the site's own login page behavior. It is never logged or stored in plaintext beyond the config entry.
