# Architecture

Groc has three runtime layers:

```text
bin/groc
  -> groc.cli
    -> groc.bridge.server on 127.0.0.1
      -> ChatGPT backend with Codex OAuth headers
```

## Components

`bin/groc` and `bin/groc-bridge` are thin shims. They set `PYTHONPATH` for a
repo checkout or local install and then execute the Python package.

`groc.cli` owns product orchestration:

- Parse commands.
- Check or start ChatGPT OAuth login.
- Render `~/.groc/config.toml` from current runtime settings.
- Start and stop the local bridge.
- Launch Grok Build with the Groc config home.
- Run diagnostics, model listing, updates, and model checks.

`groc.auth` owns Codex ChatGPT OAuth:

- Load `~/.codex/auth.json`.
- Validate the expected ChatGPT token shape.
- Redact account details for status output.
- Refresh access tokens with the refresh token.
- Build headers for backend requests.

`groc.bridge.server` exposes a minimal OpenAI-compatible API:

- `GET /health`
- `GET /v1/models`
- `POST /v1/responses`
- `POST /v1/chat/completions`

`groc.bridge.wire` converts request and response shapes between Grok Build's
OpenAI-compatible expectations and the ChatGPT backend.

`groc.bridge.client` sends authenticated requests to the ChatGPT backend and
retries once after a 401 refresh.

## Runtime Flow

1. User runs `groc`.
2. `groc.cli` loads environment-backed settings.
3. `groc.auth.GrocAuthStore` checks `~/.codex/auth.json`.
4. If auth is missing, `codex login` is launched.
5. `groc.cli.BridgeProcess` starts `groc.bridge.server`.
6. Grok Build runs with `GROK_HOME=~/.groc`.
7. Grok Build calls `http://127.0.0.1:11435/v1`.
8. The bridge calls the ChatGPT backend with OAuth headers.
9. Responses are relayed back to Grok Build.

## Design Rules

- Keep subprocess and terminal behavior in `groc.cli`.
- Keep HTTP handler code in `groc.bridge.server`.
- Keep backend request code in `groc.bridge.client`.
- Keep request/response transformation pure and testable in `groc.bridge.wire`.
- Keep token parsing and refresh in `groc.auth`.
- Keep config rendering in `groc.grok_config`.
- Keep model aliases in `groc.models`.

This keeps the product testable without requiring live credentials for most
changes.
