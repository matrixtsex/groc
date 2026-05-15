# Security Model

Groc handles a sensitive local OAuth session, so the trust boundary is explicit:
the user, the local machine, Codex's auth file, Grok Build, Groc, and the
ChatGPT backend.

## Assets

- `~/.codex/auth.json`
- ChatGPT access token
- ChatGPT refresh token
- ChatGPT account identifier
- Local request and response payloads

## Local Defaults

- The bridge binds to `127.0.0.1`.
- The default bridge port is `11435`.
- The bridge log path is `/tmp/groc-bridge.log`.
- Groc status redacts the account identifier.
- No token values are printed by normal commands.
- Groc config stores `api_key = "local"` instead of a real API key.

## Endpoint Overrides

Two environment variables can redirect sensitive requests:

```text
GROC_BACKEND_BASE_URL
GROC_REFRESH_TOKEN_URL_OVERRIDE
```

Both are rejected unless this is also set:

```text
GROC_ALLOW_UNTRUSTED_BACKEND=1
```

This is intentionally noisy because a malicious endpoint can receive OAuth
headers or refresh-token payloads.

## What Groc Does Not Do

- It does not run a remote hosted bridge.
- It does not patch Grok Build.
- It does not collect tokens.
- It does not write tokens to Groc config.
- It does not enable telemetry in the shipped Groc config.

## Operational Guidance

- Run `groc doctor` after install and after updates.
- Keep the bridge bound to localhost.
- Do not share bridge logs if they contain request content.
- Do not set endpoint overrides from untrusted shell snippets.
- Treat `~/.codex/auth.json` like a password store.
