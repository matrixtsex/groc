# Security Policy

## Supported Versions

Security fixes target the latest tagged release and `master`.

## Reporting a Vulnerability

Open a private GitHub security advisory if available. If that is not available,
open an issue with a minimal description and avoid posting OAuth tokens, account
IDs, access logs, or request bodies.

Useful reports include:

- Token disclosure in output, logs, archives, or release assets.
- Bridge exposure beyond localhost.
- Endpoint override behavior that could silently redirect credentials.
- Auth refresh bugs that corrupt `~/.codex/auth.json`.
- Request conversion bugs that leak local-only metadata.

## Design Boundaries

Groc is a local adapter for a user-controlled ChatGPT OAuth session. It does not
collect credentials, operate a remote service, or patch third-party binaries.

The bridge defaults to `127.0.0.1`. Do not bind it to a public interface unless
you fully understand the risk.

`GROC_BACKEND_BASE_URL` and `GROC_REFRESH_TOKEN_URL_OVERRIDE` are dangerous
because they can redirect OAuth-bearing requests. They are rejected unless
`GROC_ALLOW_UNTRUSTED_BACKEND=1` is also set.
