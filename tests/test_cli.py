from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from groc.cli import GrocApp, build_grok_command, is_noise_line, main, usage
from groc.settings import Settings


def settings() -> Settings:
    root = Path(tempfile.gettempdir()) / "groc-tests"
    return Settings(
        home=root / "home",
        bridge_host="127.0.0.1",
        bridge_port=11435,
        bridge_log=root / "bridge.log",
        grok_bin="/usr/local/bin/grok",
        default_model="gpt-5.5",
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


class CliTests(unittest.TestCase):
    def test_build_grok_command_sets_product_defaults(self) -> None:
        command = build_grok_command(settings(), ["--cwd", "/tmp/project"])

        self.assertEqual(command[:6], ["/usr/local/bin/grok", "-m", "gpt-5.5", "--effort", "medium", "--reasoning-effort"])
        self.assertIn("--no-memory", command)
        self.assertIn("--disable-web-search", command)
        self.assertEqual(command[-2:], ["--cwd", "/tmp/project"])

    def test_build_grok_command_respects_explicit_model_and_effort(self) -> None:
        command = build_grok_command(settings(), ["-m", "gpt-5.4", "--effort", "high", "--reasoning-effort", "high"])

        self.assertEqual(command.count("-m"), 1)
        self.assertEqual(command.count("--effort"), 1)
        self.assertEqual(command.count("--reasoning-effort"), 1)
        self.assertIn("gpt-5.4", command)

    def test_known_grok_noise_is_filtered(self) -> None:
        self.assertTrue(is_noise_line('Failed to fetch models: Auth("No auth credentials for cli-chat-proxy")'))
        self.assertTrue(is_noise_line("plugin name collision resolved by scope precedence"))
        self.assertFalse(is_noise_line("actual model failure"))

    def test_model_check_dry_run_does_not_require_auth(self) -> None:
        output = StringIO()

        with redirect_stdout(output):
            status = GrocApp(settings()).model_check(dry_run=True)

        self.assertEqual(status, 0)
        self.assertIn("plan gpt-5.5", output.getvalue())
        self.assertIn("plan grok-build", output.getvalue())

    def test_usage_mentions_doctor_fix(self) -> None:
        text = usage()
        self.assertIn("groc doctor --fix", text)
        self.assertIn("groc doctor --fix --yes", text)

    def test_main_routes_doctor_fix_yes(self) -> None:
        with (
            patch("groc.cli.settings_from_env", return_value=settings()),
            patch("groc.cli.validate_trusted_endpoints"),
            patch.object(GrocApp, "doctor_fix", return_value=0) as doctor_fix,
        ):
            status = main(["doctor", "--fix", "--yes"])

        self.assertEqual(status, 0)
        doctor_fix.assert_called_once_with(yes=True)

    def test_install_hint_for_codex_without_package_tools(self) -> None:
        app = GrocApp(settings())
        present = {"python3", "curl", "git", "bash"}

        with patch("groc.cli.command_exists", side_effect=lambda command: command in present):
            self.assertEqual(app.install_commands_for_dependency("codex"), [])
            hint = app.install_hint_for_dependency("codex")

        self.assertIn("brew install codex", hint)
        self.assertIn("@openai/codex", hint)


if __name__ == "__main__":
    unittest.main()
