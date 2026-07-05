---
name: feedback-reproduce-with-real-code
description: "When debugging this integration, reproduce against the live portal with the actual client code instead of just asking for HA logs"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 0329fe41-28f1-456c-8d63-c651901c9647
---

When investigating a bug report in this integration (calendar errors, unexpected events, wrong sensor values), prefer writing a small standalone script that imports the real `custom_components/pweb_amano/api.py` (it has no `homeassistant` dependency — only `exceptions.py`) and calls it directly against the live portal with the user's real credentials, rather than defaulting to "please paste the HA log traceback."

**Why:** The user pushed back on going straight to asking for logs/history db snapshots with "직접 코드 사용하면 여기서 로직 재현 가능하잖아" (if we use the code directly, we can reproduce the logic right here). Running the actual code against the real account surfaced a real, confirmed bug (`/state/doListMst`'s `account_no` must be sent as the logged-in user's id — leaving it blank returns the whole building's data, not just the account's own, contradicting what AGENTS.md used to claim) that guessing from code review alone would not have found.

**How to apply:**
- `api.py` can be loaded standalone via `importlib` with a dummy parent package (bypassing the real `__init__.py`, which does need `homeassistant`) — see the pattern: register a fake module in `sys.modules`, load `exceptions.py` then `api.py` from file.
- Local dev-machine gotchas unrelated to the actual bug: this Mac's python.org build's aiodns/pycares is broken (`Channel.getaddrinfo() takes 3 positional arguments...`) — force `aiohttp.connector.DefaultResolver = aiohttp.resolver.ThreadedResolver`. Also its SSL trust store lacks the DigiCert Global Root G2 chain — additionally `load_verify_locations(cafile=certifi.where())` on `api._SSL_CONTEXT`. Neither of these need to go in the repo; they're just local-environment workarounds for running one-off diagnostic scripts.
- Ask the user directly for credentials when they've already indicated they're fine sharing them in-session (as opposed to defaulting to only reading old logs/db snapshots) — but only make read-only calls (login + GET/POST fetch endpoints), never registration/mutation endpoints, during diagnostics.
- An old `~/Downloads/home-assistant_v2.db` recorder snapshot existed on this machine but the user flagged it as stale ("그거 최신 아니야") — don't rely on found-on-disk DB/log snapshots without confirming freshness with the user first.
