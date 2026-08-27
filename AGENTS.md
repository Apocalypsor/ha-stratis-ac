# AGENTS.md

## Scope

These instructions apply to the entire repository. This project is a Home Assistant custom integration distributed through HACS. It exposes STRATIS-managed thermostats as native `climate` entities.

## Product invariants

- Treat the STRATIS API as an undocumented external contract. Base behavior on captured evidence and isolate protocol details in `custom_components/stratis_ac/api.py` and `models.py`.
- Never commit HAR files, access tokens, refresh tokens, authorization headers, user IDs, property IDs, unit IDs, device IDs, addresses, or raw API responses containing personal data.
- OAuth access tokens expire after 3600 seconds. Refresh tokens rotate. Persist the returned refresh token before using the refreshed access token, and serialize all refreshes with one lock.
- A 401 may trigger one forced refresh and one retry only. Never create an unbounded authentication retry loop.
- Diagnostics must redact every credential and account identifier stored in the config entry.
- Map STRATIS `AUTO` to Home Assistant `HVACMode.HEAT_COOL`, not `HVACMode.AUTO`, because it represents an automatic heating/cooling range.
- Temperature writes must preserve the STRATIS payload shape: `value` is the requested setpoint, `value_int` is the last confirmed integral value, and `scale` is the device-native unit.
- Keep the integration cloud-polling and resilient. WebSocket support may be added later, but polling must remain a complete fallback.

## Architecture

- `api.py`: OAuth and HTTP transport; no Home Assistant entity logic.
- `models.py`: defensive parsing and STRATIS data models.
- `coordinator.py`: account/property/device refresh and update errors.
- `config_flow.py`: initial refresh-token setup and reauthentication.
- `climate.py`: Home Assistant climate behavior and protocol mapping.
- `diagnostics.py`: redacted support data only.

Use a single config entry per STRATIS account and create one climate entity per thermostat across all accessible properties. Store runtime objects in `ConfigEntry.runtime_data`.

## Development conventions

- Support Python 3.13 and the minimum Home Assistant version declared in `hacs.json`.
- Use async I/O only in integration code. Reuse Home Assistant's shared `aiohttp` session.
- Add type annotations to public and internal functions. Prefer small, explicit data models over passing raw nested dictionaries through the integration.
- User-visible text belongs in `strings.json` and translations. Keep English and Simplified Chinese translations in sync.
- Do not log response bodies from authentication endpoints or full request headers.
- Avoid adding dependencies unless the Home Assistant runtime does not already provide the needed capability.

## Verification

Before handing off a change:

1. Run `uv sync --locked --all-groups`.
2. Run `uv run --locked python -m compileall custom_components tests`.
3. Run `uv run --locked ruff check .` and
   `uv run --locked ruff format --check .`.
4. Run `uv run --locked pytest`.
5. Validate `manifest.json`, `hacs.json`, `strings.json`, and translation JSON files.
6. Confirm the repository contains no bearer or refresh tokens with a secret scan or targeted search.

Tests must cover token refresh rotation, auth retry limits, model parsing, mode mappings, temperature payload construction, config flow success/error/reauth, and coordinator auth failures.
