# Seerr for Home Assistant

Search and request movies and TV shows through [Seerr](https://github.com/seerr-team/seerr)
(also Overseerr and Jellyseerr) from Home Assistant: from automations, scripts, or by voice with
an LLM conversation agent.

**TL;DR:** add the integration with your Seerr URL and API key, then say "add the TV show Dig to
Plex" to an Assist pipeline whose conversation agent uses the Assist LLM API.

## Setup

1. Copy `custom_components/seerr` to your Home Assistant `custom_components` folder (or add this
   repository to HACS as a custom repository) and restart.
2. Settings → Devices & services → Add integration → Seerr. Enter the server URL (a bare host
   uses `http` and port 5055) and the API key from Seerr's Settings → General.

Requests are made as the API key's user, usually the admin, so Seerr approves them
automatically.

## Actions

- `seerr.search`: `query`, optional `media_type` (`movie`/`tv`) and `year`. Returns each
  result's TMDB id, year and status (`available`, `partially_available`, `pending`,
  `processing`, `unknown`, ...).
- `seerr.request`: a `query` (with optional `media_type` and `year`), or a `tmdb_id` with a
  `media_type`; optional `is_4k`. TV shows are requested with every season. Returns `result`:
  `requested`, `already_available`, `already_requested`, `ambiguous` (with `options`) or
  `not_found`. Called without reading the response, `ambiguous` and `not_found` raise an error.

A title is only requested when it is clear which one is meant. Among the results whose title
is the query, a new one (out this year or last, or still to come) is meant over older ones, so
"Dig" in 2026 is the 2026 show, not the 2015 one. Of those left, the only one, or one with ten
times the votes of the next, is requested (Oppenheimer 2023 over a 1980 mini-series). "The
Office" (US or UK) comes back as `ambiguous`, so you can choose. Give a year or a media type to
pick an older title.

## Voice (LLM tools)

The integration adds two tools to the Assist LLM API, `seerr__search_media` and
`seerr__request_media`. An LLM conversation agent (Claude, OpenAI, Ollama, ...) with "Control
Home Assistant" set to Assist can then handle requests like "do we have Severance?" or "add the
movie Dune to Plex", and asks you which one you mean when a title is ambiguous.

## Development

```bash
uv venv --python 3.14 && uv pip install -r requirements_test.txt
.venv/bin/pytest && .venv/bin/ruff check . && .venv/bin/mypy
```
