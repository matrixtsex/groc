from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from groc.models import DEFAULT_MODEL, DEFAULT_UPSTREAM_MODEL


DEFAULT_BACKEND_BASE_URL = "https://chatgpt.com/backend-api/codex"
DEFAULT_REFRESH_URL = "https://auth.openai.com/oauth/token"


@dataclass(frozen=True)
class Settings:
    home: Path
    bridge_host: str
    bridge_port: int
    bridge_log: Path
    grok_bin: str
    default_model: str
    reasoning_effort: str
    auth_home: Path
    codex_bin: str
    repo_url: str
    update_dir: Path
    upstream_model: str
    backend_base_url: str
    refresh_url: str
    auto_login: bool
    device_auth: bool
    raw_stderr: bool
    allow_untrusted_backend: bool

    @property
    def auth_file(self) -> Path:
        return self.auth_home / "auth.json"

    @property
    def bridge_base_url(self) -> str:
        return f"http://{self.bridge_host}:{self.bridge_port}"

    @property
    def bridge_health_url(self) -> str:
        return f"{self.bridge_base_url}/health"

    @property
    def api_base_url(self) -> str:
        return f"{self.bridge_base_url}/v1"


def env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value not in {"", "0", "false", "False", "no", "NO"}


def settings_from_env() -> Settings:
    backend_base_url = os.environ.get("GROC_BACKEND_BASE_URL", DEFAULT_BACKEND_BASE_URL).rstrip("/")
    refresh_url = os.environ.get("GROC_REFRESH_TOKEN_URL_OVERRIDE", DEFAULT_REFRESH_URL)
    return Settings(
        home=Path(os.environ.get("GROC_HOME", "~/.groc")).expanduser(),
        bridge_host=os.environ.get("GROC_BRIDGE_HOST", "127.0.0.1"),
        bridge_port=int(os.environ.get("GROC_BRIDGE_PORT", "11435")),
        bridge_log=Path(os.environ.get("GROC_BRIDGE_LOG", "/tmp/groc-bridge.log")).expanduser(),
        grok_bin=os.environ.get("GROC_GROK_BIN", str(Path("~/.local/bin/grok").expanduser())),
        default_model=os.environ.get("GROC_MODEL", DEFAULT_MODEL),
        reasoning_effort=os.environ.get("GROC_REASONING_EFFORT", "medium"),
        auth_home=Path(os.environ.get("GROC_AUTH_HOME", "~/.codex")).expanduser(),
        codex_bin=os.environ.get("GROC_CODEX_BIN", "codex"),
        repo_url=os.environ.get("GROC_REPO_URL", "https://github.com/matrixtsex/groc.git"),
        update_dir=Path(os.environ.get("GROC_UPDATE_DIR", "~/.local/share/groc-src")).expanduser(),
        upstream_model=os.environ.get("GROC_UPSTREAM_MODEL", DEFAULT_UPSTREAM_MODEL),
        backend_base_url=backend_base_url,
        refresh_url=refresh_url,
        auto_login=env_flag("GROC_AUTO_LOGIN", True),
        device_auth=env_flag("GROC_CODEX_DEVICE_AUTH", False),
        raw_stderr=env_flag("GROC_RAW_STDERR", False),
        allow_untrusted_backend=env_flag("GROC_ALLOW_UNTRUSTED_BACKEND", False),
    )


def validate_trusted_endpoints(settings: Settings) -> None:
    if settings.allow_untrusted_backend:
        return
    if settings.backend_base_url != DEFAULT_BACKEND_BASE_URL:
        raise ValueError(
            "GROC_BACKEND_BASE_URL is a dangerous override. "
            "Set GROC_ALLOW_UNTRUSTED_BACKEND=1 only if you trust the endpoint."
        )
    if settings.refresh_url != DEFAULT_REFRESH_URL:
        raise ValueError(
            "GROC_REFRESH_TOKEN_URL_OVERRIDE is a dangerous override. "
            "Set GROC_ALLOW_UNTRUSTED_BACKEND=1 only if you trust the endpoint."
        )
