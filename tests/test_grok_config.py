from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from groc.grok_config import render_grok_config, write_grok_config
from groc.settings import Settings


def settings(port: int = 11435, model: str = "gpt-5.5") -> Settings:
    root = Path(tempfile.gettempdir()) / "groc-config-tests"
    return Settings(
        home=root / "home",
        bridge_host="127.0.0.1",
        bridge_port=port,
        bridge_log=root / "bridge.log",
        grok_bin="/usr/local/bin/grok",
        default_model=model,
        reasoning_effort="medium",
        auth_home=root / "auth",
        codex_bin="codex",
        repo_url="https://github.com/matrixtsex/groc.git",
        update_dir=root / "src",
        upstream_model="gpt-5.5",
        backend_base_url="https://chatgpt.com/backend-api/codex",
        refresh_url="https://auth.openai.com/oauth/token",
        auto_login=True,
        device_auth=False,
        raw_stderr=False,
        allow_untrusted_backend=False,
    )


class GrokConfigTests(unittest.TestCase):
    def test_render_uses_runtime_bridge_port_and_default_model(self) -> None:
        rendered = render_grok_config(settings(port=11436, model="gpt-5.4"))

        self.assertIn('default = "gpt-5.4"', rendered)
        self.assertIn('base_url = "http://127.0.0.1:11436/v1"', rendered)
        self.assertIn('fork_secondary_model = "gpt-5.4"', rendered)

    def test_write_grok_config_creates_home(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_settings = settings()
            config_settings = Settings(
                **{**config_settings.__dict__, "home": Path(directory) / "missing" / "home"}
            )

            write_grok_config(config_settings)

            self.assertTrue((config_settings.home / "config.toml").is_file())


if __name__ == "__main__":
    unittest.main()
