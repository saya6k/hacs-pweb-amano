# Repository agent instructions

> `CLAUDE.md` is a local symlink to this file (gitignored) — edit `AGENTS.md`.

Agent assets live under `.agents/` (the source of truth): `skills/`, `workflows/` (commands), `agents/`, and `memory/` (Claude's per-project memory). `.claude/` is a real directory: its `settings.json` is Claude-specific and tracked; its per-item symlinks into `.agents/` (`skills`, `commands` → `workflows`, `agents`) and `settings.local.json` are local-only, as is the `CLAUDE.md` → `AGENTS.md` symlink.

This file briefs coding agents on the conventions and load-bearing facts of `hacs-pweb-amano`. Read this before making changes.

## What this integration is

A HACS custom integration for **PWEB** (Amano Korea) apartment/officetel management portals — sites like `https://a12345.pweb.kr` that run the 아마노코리아 관리사무소 시스템. There is no public API; the portal is a legacy JSP-style site (`*.do` endpoints, `JSESSIONID` cookies) meant to be driven through a browser, so this integration logs in and parses HTML.

- **Login:** `POST {base_url}/login` with form fields `userId` (plaintext) and `userPwd` (**sha256 hex digest of the plaintext password** — the site's own login page hashes client-side before submitting, see `login.js`/`sha256-0.9.0.min.js`). Success is any 2xx response; failure is HTTP 500 with a JSON `errorMsg`, or HTTP 401 (personal-info agreement required — not handled).
- **Session:** the login response sets a `JSESSIONID` cookie; every subsequent page fetch must reuse the same `aiohttp.ClientSession` (cookie jar) or the site treats you as logged out.
- **Dashboard scraping (post-login landing page `/`) is still unimplemented.** Nobody has inspected that page's layout — `api.py:async_fetch_dashboard` fetches and returns the raw page but nothing parses it. Don't invent fields for it without seeing the real markup.
- **The discount (할인) screens *are* implemented**, based on real authenticated HTML from one account (오피스텔 unit, account_no `9999`, site `a12345.pweb.kr`). Endpoints used, all requiring the session cookie:
  - `POST /state/doListMst` (startDate/endDate yyyyMMdd, `rowcount`) — discount registration history + a `summary` row (used_cnt/used_basic/used_charge/discount_price). Backs the registration-status sensor and the discount-history calendar. `account_no` **must be sent as the logged-in user's own id** — confirmed by live testing (account `9999` against 2 years/9575 rows) that leaving it blank returns every account's registrations building-wide (38 distinct account_no values seen), not just the session's own. A visitor-car registration still carries the registering resident's own account_no, so filtering on it doesn't drop those.
  - `GET /pay/doViewDscnt` — server-renders the "잔여 할인" (remaining discount balance, KRW) straight into the HTML table; no AJAX call needed. Backs the balance sensor.
  - `POST /discount/registration/listForDiscount` (`iLotArea`, `entryDate` yyyyMMdd, `carNo`) — finds a currently-parked vehicle's entry id (`id`, aka `peId`). `iLotArea` is derived from the host itself (`api.extract_ilot_area`): PWEB hostnames are `a<iLotArea>.pweb.kr`, e.g. `a12345.pweb.kr` → iLotArea `12345`.
  - `GET /login` (unauthenticated) — renders the site/building name into `<title>` even when logged out (`api.async_fetch_site_name`). The config flow asks for the numeric iLotArea first, builds the host from it, and shows this name back to the user to confirm before asking for credentials.
  - `POST /discount/registration/save` (`peId`, `carNo`, `discountType`, `memo`) — registers a discount; returns JSON `true`/`false`. Backs the `register_discount` service.
  - Vehicle entry/exit: this account's menus (할인/계정관리/통계관리, fully enumerated) expose **no dedicated in/out log**. The only entry-time data available is bundled with discount registrations (`entry_date` + `paid_stat` in `/state/doListMst`), so the `event` platform only fires **exit** events (`paid_stat` flipping to `10`, diffed per-poll in `coordinator.py`) — there is no entry event.
  - These endpoints are confirmed for one site/account only. Field names, `iLotArea` derivation, and menu availability may differ for other sites or account types (e.g. admin vs residential) — verify against real HTML before assuming they generalize.
- **`robots.txt` on this host disallows crawling** (`Disallow: /`). That's aimed at search engines. This integration only ever fetches pages behind the user's own login, at a normal HA polling cadence (not a crawler) — keep it that way; don't add multi-page crawling or high-frequency polling.

## Repository layout

```
hacs-pweb-amano/
├── custom_components/pweb_amano/
│   ├── __init__.py        ← async_setup_entry/async_unload_entry, creates the coordinator, registers services
│   ├── const.py            ← DOMAIN, CONF_* keys, default scan interval, service name
│   ├── api.py               ← PwebAmanoApiClient: login, discount state/balance/registration (aiohttp)
│   ├── exceptions.py       ← PwebAmanoAuthError / PwebAmanoConnectionError / PwebAmanoRegistrationError
│   ├── coordinator.py       ← DataUpdateCoordinator, calls api.py, diffs paid_stat for exit events
│   ├── config_flow.py       ← 3 steps: iLotArea → confirm site name → userId/userPwd
│   ├── sensor.py            ← last-sync, discount-balance, registration-status sensors
│   ├── calendar.py          ← discount-history calendar (on-demand date-range queries)
│   ├── event.py             ← vehicle-exit event entity
│   ├── services.py          ← register_discount action service
│   ├── services.yaml        ← service field/selector definitions for the UI
│   ├── manifest.json
│   ├── strings.json         ← English source of truth for translations
│   └── translations/en.json, ko.json
├── .devcontainer/
├── scripts/
│   ├── setup                ← installs HA + dev deps in the container
│   └── develop               ← runs HA from this checkout for live testing
├── hacs.json
└── README.md
```

## Hard rules

1. **Never set `_attr_name` on an entity that has `_attr_translation_key`.** HA's `Entity._name_internal` returns `_attr_name` first and never consults the translation map afterwards — this silently breaks non-English UI. Pick one.
2. **Translations live in two places.** `strings.json` is the English source of truth; `translations/<lang>.json` must share the same key tree — update both together.
3. **The coordinator owns all network I/O.** Entities read `self.coordinator.data[...]`; they never call `api.py` directly.
4. **`manifest.json` declares `iot_class: cloud_polling`.** Don't add push/websocket behavior.
5. **Password never leaves memory as plaintext longer than needed.** Hash with `hashlib.sha256` right before the login POST; don't log the raw password or the hash.
6. **`brand/` assets are Amano Korea's official CI marks** (downloaded from amano.co.kr's public brand page: `icon.png` = the AMANO triangle mark padded to a square, `logo.png`/`dark_logo.png` = the "Time & Air / AMANO" wordmark, light/dark variants). Used solely to identify the integrated service — this is an unofficial, community-maintained integration, not published or endorsed by Amano Korea.

## Testing

```bash
scripts/develop          # boots HA on :8123 with this integration mounted
```

No automated test suite. Validate by adding the integration via Settings → Devices & Services with a real account and watching `home-assistant.log`.

## Release workflow

This repo (and other `ha-*` HACS components, excluding `ha-app*`) ships on a
two-track rolling draft release, maintained by release-drafter since
`0f908fb` (#7): a `rc` (prerelease) draft and a `stable` draft, both updated
continuously as PRs merge to `main`.

1. Verify locally with the devcontainer (`scripts/develop`) before merging —
   see Testing above.
2. Once merged and the `rc` draft looks right, publish it as a prerelease
   from the GitHub Releases UI.
3. After the prerelease has been exercised with no issues, promote/publish
   the corresponding `stable` draft.

## When in doubt

- Login fails with 500? Read the JSON body's `errorMsg` — the site returns a human-readable reason.
- Need new sensors? Get authenticated HTML from the user first (browser dev tools, "view source" after login) — don't guess field names.
