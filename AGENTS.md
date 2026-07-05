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
  - `POST /state/doListMst` (startDate/endDate yyyyMMdd, `rowcount`) — discount registration history + a `summary` row (used_cnt/used_basic/used_charge/discount_price). Backs the registration-status sensor and the parking-history calendar. `account_no` **must be sent as the logged-in user's own id** — confirmed by live testing (account `9999` against 2 years/9575 rows) that leaving it blank returns every account's registrations building-wide (38 distinct account_no values seen), not just the session's own. A visitor-car registration still carries the registering resident's own account_no, so filtering on it doesn't drop those. Rows carry both `entry_date` (입차) and `dtOutDate` (출차) - the calendar spans that full duration, not just the registration timestamp.
  - `GET /pay/doViewDscnt` — server-renders the "잔여 할인" (remaining discount balance, KRW) straight into the HTML table; no AJAX call needed. Backs the balance sensor.
  - `POST /discount/registration/listForDiscount` (`iLotArea`, `entryDate` yyyyMMdd, `carNo`) — finds a currently-parked vehicle's entry id (`id`, aka `peId`). `iLotArea` is derived from the host itself (`api.extract_ilot_area`): PWEB hostnames are `a<iLotArea>.pweb.kr`, e.g. `a12345.pweb.kr` → iLotArea `12345`. **`carNo` only matches within one of the plate's two digit groups** - confirmed live against a real currently-parked car (`237도2469`): searching `"237"` or `"2469"` alone each find it, but the full plate, the Hangul character alone, or the two digit groups concatenated (`"2372469"`) all find nothing. `api.async_find_parked_entry` extracts the trailing digit run from `car_no` before searching for exactly this reason - passing a plate through unmodified silently finds zero results for every car. The actual `/discount/registration/save` call is not picky - it took the untouched full plate fine in the same live test.
  - `GET /login` (unauthenticated) — renders the site/building name into `<title>` even when logged out (`api.async_fetch_site_name`). The config flow asks for the numeric iLotArea first, builds the host from it, and shows this name back to the user to confirm before asking for credentials.
  - `POST /discount/registration/save` (`peId`, `carNo`, `discountType`, `memo`) — registers a discount; returns JSON `true`/`false`. Backs the `register_discount` service.
  - `POST /setup/dscntTypeSetting/doListMst` (no params needed beyond the session cookie) — the site's **full admin-configured** discount-type catalog (`id`, `discount_name`, `discount_price`, `discount_value` in minutes, `del_yn`). Site-wide config, not scoped to the calling account, and may include types this account never actually uses (10 entries confirmed for this site as of 2026-07-05: ids 1-5/9-12, including an office-only `공무 무료` and an apparently unrelated "파킹쉐어" ticket scheme). Fetched every poll and exposed as-is (minus `del_yn` ones) via the registration-status sensor's `available_discount_types` attribute - the reference for what a different site's real options look like, since `discount_type`'s `services.yaml` selector (see below) is hardcoded to this one.
  - **`register_discount`'s `discount_type` selector is a hardcoded dropdown of this account's 2 actually-used types** (`1`/`[무료] 1시간 할인`, `6`/`[유료] 1시간 할인`, confirmed via `/stats/doLisPeriodtMst` - see below), with `custom_value: true` so other sites/policies can still type a different ID. This is a deliberate UX tradeoff: HA's `services.yaml` selector options are parsed once at integration load and can't be built per-config-entry/live, so a truly dynamic per-account dropdown *inside the service call form* isn't possible for a plain custom integration - chosen over the alternatives (no dropdown at all, or a separate `select` entity you set beforehand) after discussing the tradeoff directly.
  - **`list_unregistered_vehicles` service** (`services.py`) - there's no endpoint that lists every currently-parked car, so it brute-forces `listForDiscount` with each single digit `0`-`9` as `carNo` (guaranteed to hit every plate, which always has digits) across each of the last `days` days, dedupes by `id`, and keeps only rows with `dscnt_cnt == "0"` (not yet registered). Explicitly calls `client.async_login()` first, unlike `register_discount` (which relies on the coordinator's last poll still having a fresh session) - this is an on-demand query that could run long after that, same reasoning as the calendar's `async_get_discount_events` (see the timezone/naive-datetime hard rule below for why that distinction mattered before). Uses `SupportsResponse.ONLY` to return the list directly to the caller rather than creating new entities.
  - `POST /stats/doLisPeriodtMst` (`startDate`/`endDate` yyyyMMdd, `userId`, `master_id`, `rowcount`) — per-discount-type usage stats (`dcName`, `dcCount`, `dcPrice`, `sumPrice`) for the given `userId`, scoped server-side (unlike `/state/doListMst`, no separate account_no fix needed here). Not called at runtime; used only to confirm live that this account's real usage is a small subset of the full catalog (2 of 10 types) - i.e. the full catalog can't be assumed to reflect what's actually relevant, which is why the coordinator exposes the full catalog rather than us guessing a filtered subset.
  - `POST /discount/registration/getForDiscount` (`id`, `member_id`) returns a per-vehicle-filtered discount-type subset (`listDiscountType`) - would be an even more precise source, but only works for a still-parked vehicle (errors `출차된 차량입니다` otherwise), so it's not usable for a general catalog lookup.
  - Vehicle entry/exit: this account's menus (할인/계정관리/통계관리, fully enumerated) expose **no dedicated in/out log**. The only entry/exit data available is bundled with discount registrations (`entry_date` + `dtOutDate` + `paid_stat` in `/state/doListMst`), diffed per-poll in `coordinator.py._detect_new_entries_and_exits` and exposed by the `event` platform (`vehicle_parking`, tracked plates only) as two distinct signals with different reliability: **"exit"** fires when `paid_stat` flips to `10` for a plate already being tracked - a genuine real-time signal, for a car whose discount was registered while still parked. **"entry"** fires the first time a plate's tckttrns_id/idno is ever seen - not a live detection, just "we noticed this registration exists" using its `entry_date` attribute, since registration often happens well after (sometimes right at/near) the car actually leaving. In the common case (registration only appears once the car's already gone, i.e. `paid_stat` is already `10` the first time it's seen) both fire together in the same poll. **`EventEntity` only keeps the last `_trigger_event()` call until state is written** - firing multiple events in one `_handle_coordinator_update()` (e.g. entry+exit together, or 2 exits in the same poll) silently drops all but the final one unless `async_write_ha_state()` is called after each trigger, not just once at the end.
  - These endpoints are confirmed for one site/account only. Field names, `iLotArea` derivation, and menu availability may differ for other sites or account types (e.g. admin vs residential) — verify against real HTML before assuming they generalize.
- **`register_discount` is not "give my own car a discount" - it's "apply a discount type to whatever car is currently parked."** A resident can (and does) register discounts for visitors' and family members' cars, not just their own. So a discount-registration record's `account_no` tells you *who registered it*, not *whose car it is* - there's no `account_no`→"my car" relationship. The **parking-history calendar and vehicle-parking event only cover the car plates configured via the options flow** (Settings → Devices & Services → this integration → Configure, `CONF_CAR_PLATES` in `entry.options`, a list) - they don't cover every discount registration this account has ever made, since most of those are for other people's cars.
- **One HA device per tracked car plate, separate from the main site device.** `calendar.py`/`event.py` each build one entity (and device, `identifiers={(DOMAIN, f"{entry.entry_id}_{plate}")}`, `via_device=(DOMAIN, entry.entry_id)`) per plate in `CONF_CAR_PLATES`, re-created on every entry reload (`async_setup_entry` reads `entry.options` fresh) - so devices appear/disappear as plates are added/removed via Configure. This is deliberately separate from discount-management concerns: the sensors and refresh button stay on the one site-level device (`entry.entry_id`, `DeviceEntryType.SERVICE`); a tracked car isn't a "service" so its device has no `entry_type` set. **A blank/whitespace-only entry in that list gets its own (unnamed) device** - HA's device registry doesn't reject an empty `name`. `config_flow.py`'s `_clean_car_plates()` strips/drops blanks before saving (both the setup flow's car-plates step and the options flow route through it), and `calendar.py`/`event.py` also filter defensively at read time for entries already saved before that fix existed. **Removing/editing a plate via Configure does not by itself clean up its old device** - `entity_platform.async_add_entities()` has no concept of "prune what I didn't just add," so a stale plate's device (and entities, cascaded via the `EVENT_DEVICE_REGISTRY_UPDATED` "remove" listener `EntityRegistry` sets up on itself) would linger forever otherwise. `__init__.py`'s `_async_remove_orphaned_vehicle_devices()` runs on every `async_setup_entry` (i.e. every reload, including the one options changes trigger) and explicitly removes any of this entry's devices whose identifier isn't the site device or a currently-tracked plate. **`services.yaml`'s `register_discount.device_id` selector filters on `entity: {domain: sensor}`** to only offer the site device - a plain `integration: pweb_amano` filter would also list every tracked vehicle's device now that they exist, which is misleading (the service registers against the site/session, not a specific car).
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
│   ├── config_flow.py       ← setup: iLotArea → confirm site name → userId/userPwd → optional car plates; options: tracked car plates (same field, editable any time)
│   ├── sensor.py            ← last-sync, discount-balance, registration-status sensors
│   ├── calendar.py          ← parking-history calendar for tracked car plates (on-demand date-range queries)
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
6. **Any datetime handed to HA must be timezone-aware.** `dt_util.as_local()`/`dt_util.utcnow()`, never naive `datetime.strptime()`/`datetime.now()`. HA validates this and raises: a naive `last_sync` broke the TIMESTAMP sensor (#12), and a naive `CalendarEvent.start`/`end` breaks the parking-history calendar for any date range containing at least one registration (`CalendarEvent.__post_init__` calls `_has_timezone`, raising `HomeAssistantError` - silently, since HA doesn't log it as an unhandled exception - whenever a naive datetime is used). The portal's timestamps are its own local wall-clock time with no explicit timezone, so parse naive then `dt_util.as_local()` (which attaches tzinfo as-is, no numeric shift) - don't treat them as UTC.
7. **`brand/` assets are Amano Korea's official CI marks** (downloaded from amano.co.kr's public brand page: `icon.png` = the AMANO triangle mark padded to a square, `logo.png`/`dark_logo.png` = the "Time & Air / AMANO" wordmark, light/dark variants). Used solely to identify the integrated service — this is an unofficial, community-maintained integration, not published or endorsed by Amano Korea.
8. **`EventEntity._trigger_event()` doesn't write state by itself** - it just overwrites private `__last_event_*` fields, which `state`/`state_attributes` read from at write time. Calling it more than once inside one `_handle_coordinator_update()` without an `async_write_ha_state()` after each call silently drops every firing but the last (see `event.py`).

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
