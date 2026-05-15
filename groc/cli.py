from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import groc
from groc.auth import GrocAuthStore
from groc.errors import GrocError
from groc.grok_config import write_grok_config
from groc.models import MODEL_CATALOG
from groc.settings import Settings, settings_from_env, validate_trusted_endpoints


NOISE_PATTERNS = (
    'Failed to fetch models: Auth("No auth credentials for cli-chat-proxy")',
    "model refresh failed, leaving existing models unchanged",
    "plugin name collision resolved by scope precedence",
    "skill name does not match expected name from path",
    "skill metadata value is not a string; ignoring",
    "web_search disabled: resolved config has no API key",
    "hooks: skipped unrecognized event names",
    "required env var(s) not set",
    "MCP server init failed",
    "MCP server failed to initialize",
    "AuthorizationRequired",
)


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    label: str
    detail: str = ""
    warning: bool = False


def usage() -> str:
    return f"""groc {groc.__version__}

Usage:
  groc                         Launch Grok Build with ChatGPT OAuth
  groc [grok args...]          Forward args to Grok Build
  groc login                   Start ChatGPT OAuth login
  groc status                  Show auth, bridge, config, and default model
  groc doctor                  Check install health and print fixes
  groc doctor --fix            Offer dependency installs, then re-check health
  groc doctor --fix --yes      Install missing dependencies without prompts
  groc models                  List configured models
  groc models --check          Test configured models against ChatGPT OAuth
  groc update                  Pull and reinstall the latest Groc
  groc --version               Print Groc version

Common examples:
  groc --cwd ~/code/my-repo
  groc -p "explain this repo"
  groc -m gpt-5.4
  groc --effort high
  groc doctor --fix
"""


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def shell_join(command: list[str]) -> str:
    return shlex.join(command)


def package_manager() -> str | None:
    for candidate in ("brew", "apt-get", "dnf", "yum", "pacman"):
        if command_exists(candidate):
            return candidate
    return None


def package_install_commands(manager: str, package: str) -> list[list[str]]:
    if manager == "brew":
        return [["brew", "install", package]]
    if manager == "apt-get":
        return [["sudo", "apt-get", "install", "-y", package]]
    if manager == "dnf":
        return [["sudo", "dnf", "install", "-y", package]]
    if manager == "yum":
        return [["sudo", "yum", "install", "-y", package]]
    if manager == "pacman":
        return [["sudo", "pacman", "-S", "--noconfirm", package]]
    return []


def is_noise_line(line: str) -> bool:
    return any(pattern in line for pattern in NOISE_PATTERNS)


def has_option(args: list[str], *names: str) -> bool:
    names_set = set(names)
    for arg in args:
        if arg in names_set:
            return True
        if any(arg.startswith(f"{name}=") for name in names if name.startswith("--")):
            return True
    return False


def build_grok_command(settings: Settings, args: list[str]) -> list[str]:
    command = [settings.grok_bin]
    if not has_option(args, "-m", "--model"):
        command.extend(["-m", settings.default_model])
    if not has_option(args, "--effort"):
        command.extend(["--effort", settings.reasoning_effort])
    if not has_option(args, "--reasoning-effort"):
        command.extend(["--reasoning-effort", settings.reasoning_effort])
    command.extend(["--no-memory", "--disable-web-search"])
    command.extend(args)
    return command


def env_for_grok(settings: Settings) -> dict[str, str]:
    env = os.environ.copy()
    env["GROK_HOME"] = str(settings.home)
    return env


def read_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=5) as response:
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise GrocError(f"non-object response from {url}")
    return value


def post_json(url: str, payload: dict[str, Any], timeout: int = 300) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise GrocError(f"non-object response from {url}")
    return value


class BridgeProcess:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.process: subprocess.Popen[bytes] | None = None
        self.log_file: Any | None = None

    def running(self) -> bool:
        try:
            read_json(self.settings.bridge_health_url)
            return True
        except Exception:
            return False

    def ensure(self) -> None:
        if self.running():
            return

        for _ in range(3):
            self.settings.bridge_log.parent.mkdir(parents=True, exist_ok=True)
            self.log_file = self.settings.bridge_log.open("ab")
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "groc.bridge.server",
                    "--host",
                    self.settings.bridge_host,
                    "--port",
                    str(self.settings.bridge_port),
                ],
                stdout=self.log_file,
                stderr=subprocess.STDOUT,
                env=os.environ.copy(),
            )
            for _ in range(10):
                if self.running():
                    return
                if self.process.poll() is not None and self.running():
                    return
                time.sleep(0.5)
            self.stop()
            if self.running():
                return
            time.sleep(0.5)

        tail = ""
        try:
            tail = "\n".join(self.settings.bridge_log.read_text(encoding="utf-8", errors="replace").splitlines()[-20:])
        except FileNotFoundError:
            pass
        message = f"failed to start OAuth bridge at {self.settings.bridge_health_url}"
        if tail:
            message += f"\nbridge log: {self.settings.bridge_log}\n{tail}"
        raise GrocError(message)

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.process = None
        if self.log_file:
            self.log_file.close()
            self.log_file = None

    def __enter__(self) -> "BridgeProcess":
        self.ensure()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()


class GrocApp:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.auth_store = GrocAuthStore(settings.auth_home, settings.refresh_url)

    def ensure_config(self) -> None:
        write_grok_config(self.settings)

    def ensure_auth(self) -> None:
        if self.auth_store.ready():
            return
        if not self.settings.auto_login:
            raise GrocError(
                f"ChatGPT OAuth login is required in {self.settings.auth_file}\n"
                "run 'groc login' or unset GROC_AUTO_LOGIN to let groc start it"
            )
        print("groc: ChatGPT OAuth login required; starting login...", file=sys.stderr)
        self.login(device=self.settings.device_auth)

    def login(self, device: bool = False) -> int:
        if not command_exists(self.settings.codex_bin):
            raise GrocError(
                f"ChatGPT OAuth login requires '{self.settings.codex_bin}'\n"
                "install Codex CLI or set GROC_CODEX_BIN=/path/to/codex"
            )
        command = [self.settings.codex_bin, "login"]
        if device:
            command.append("--device-auth")
        status = subprocess.run(command).returncode
        if status != 0:
            return status
        if not self.auth_store.ready():
            raise GrocError(f"login did not create ChatGPT OAuth credentials at {self.settings.auth_file}")
        return 0

    def status(self) -> int:
        self.ensure_config()
        summary = self.auth_store.summary()
        bridge = BridgeProcess(self.settings)
        print(f"Groc {groc.__version__}")
        print(f"home: {self.settings.home}")
        print(f"config: {self.settings.home / 'config.toml'}")
        print(f"model: {self.settings.default_model}")
        print(f"reasoning: {self.settings.reasoning_effort}")
        print(f"bridge: {self.settings.bridge_base_url}")
        print(f"bridge log: {self.settings.bridge_log}")
        print(f"grok binary: {self.settings.grok_bin}")
        print(f"codex binary: {self.settings.codex_bin}")
        print(f"auth: {summary.message}")
        print(f"bridge status: {'running' if bridge.running() else 'stopped'}")
        return 0

    def doctor(self) -> int:
        self.ensure_config()
        checks = list(self.doctor_checks())
        print("Groc doctor")
        print()
        failures = 0
        warnings = 0
        for check in checks:
            if check.ok:
                print(f"ok   {check.label}")
            elif check.warning:
                warnings += 1
                print(f"warn {check.label}")
            else:
                failures += 1
                print(f"fail {check.label}")
            if check.detail:
                print(f"     {check.detail}")
        print()
        if failures == 0:
            if warnings == 0:
                print("Groc is ready.")
            else:
                print(f"Groc is usable, with {warnings} warning(s).")
            return 0
        print(f"Groc needs attention: {failures} failure(s), {warnings} warning(s).")
        print()
        print("Common fixes:")
        print("  bin/install")
        print('  export PATH="$HOME/.local/bin:$PATH"')
        print("  groc login")
        print("  GROC_BRIDGE_PORT=11436 groc")
        print("  groc doctor --fix")
        return 1

    def doctor_fix(self, yes: bool = False) -> int:
        self.ensure_config()
        dependency_failures = self.missing_dependency_ids()
        if not dependency_failures:
            print("groc: all required dependencies are already installed")
            return self.doctor()

        print("groc: missing dependencies detected:")
        for dep in dependency_failures:
            print(f"  - {dep}")
        print()

        installed_any = False
        for dep in dependency_failures:
            commands = self.install_commands_for_dependency(dep)
            if not commands:
                print(f"skip {dep}: no safe automatic installer found")
                print(f"      {self.install_hint_for_dependency(dep)}")
                continue

            print(f"install {dep}:")
            for command in commands:
                print(f"  {shell_join(command)}")

            if not yes:
                try:
                    answer = input(f"run installer for {dep}? [y/N] ").strip().lower()
                except EOFError:
                    answer = ""
                if answer not in {"y", "yes"}:
                    print(f"skip {dep}")
                    continue

            try:
                for command in commands:
                    subprocess.run(command, check=True)
                installed_any = True
            except subprocess.CalledProcessError as exc:
                print(f"fail {dep}")
                print(f"      installer failed with exit status {exc.returncode}")

        print()
        if not installed_any:
            print("groc: no dependency installers were executed successfully")
        return self.doctor()

    def missing_dependency_ids(self) -> list[str]:
        missing: list[str] = []
        if not command_exists("python3"):
            missing.append("python3")
        if not command_exists("curl"):
            missing.append("curl")
        if not command_exists("git"):
            missing.append("git")
        if not Path(self.settings.grok_bin).is_file():
            missing.append("grok")
        if not command_exists(self.settings.codex_bin):
            missing.append("codex")
        return missing

    def install_commands_for_dependency(self, dep: str) -> list[list[str]]:
        manager = package_manager()
        if dep in {"python3", "curl", "git"}:
            if manager is None:
                return []
            package = dep
            if dep == "python3" and manager == "brew":
                package = "python"
            return package_install_commands(manager, package)
        if dep == "codex":
            if command_exists("brew"):
                return [["brew", "install", "codex"]]
            if command_exists("npm"):
                return [["npm", "install", "-g", "@openai/codex"]]
            return []
        if dep == "grok":
            if not command_exists("bash"):
                return []
            return [["bash", "-lc", "curl -fsSL https://x.ai/cli/install.sh | bash"]]
        return []

    def install_hint_for_dependency(self, dep: str) -> str:
        manager = package_manager()
        if dep in {"python3", "curl", "git"} and manager is None:
            return "install a package manager (brew/apt-get/dnf/yum/pacman), then re-run 'groc doctor --fix'"
        if dep == "codex":
            return "install Codex with 'brew install codex' or 'npm install -g @openai/codex'"
        if dep == "grok":
            return "install Grok Build with 'curl -fsSL https://x.ai/cli/install.sh | bash'"
        return "install manually, then re-run 'groc doctor'"

    def doctor_checks(self) -> Iterable[CheckResult]:
        yield CheckResult(command_exists("python3"), "python3 is available")
        yield CheckResult(command_exists("curl"), "curl is available")
        yield CheckResult(command_exists("git"), "git is available")
        yield CheckResult(Path(self.settings.grok_bin).is_file(), f"grok binary exists: {self.settings.grok_bin}")
        yield CheckResult(command_exists(self.settings.codex_bin), f"codex CLI exists: {self.settings.codex_bin}")
        yield CheckResult((self.settings.home / "config.toml").is_file(), f"groc config exists: {self.settings.home / 'config.toml'}")
        yield CheckResult(self.auth_store.ready(), f"ChatGPT OAuth is ready: {self.settings.auth_file}")
        path_ok = str(Path("~/.local/bin").expanduser()) in os.environ.get("PATH", "").split(os.pathsep)
        yield CheckResult(path_ok, "~/.local/bin is on PATH", warning=True)
        yield CheckResult(True, "groc Python package imports")

        bridge = BridgeProcess(self.settings)
        if bridge.running():
            yield CheckResult(True, "bridge health endpoint is already running")
            return
        try:
            bridge.ensure()
            yield CheckResult(True, f"bridge can start on {self.settings.bridge_health_url}")
        except Exception as exc:
            yield CheckResult(False, f"bridge can start on {self.settings.bridge_health_url}", str(exc))
        finally:
            bridge.stop()

    def models(self) -> int:
        self.ensure_auth()
        with BridgeProcess(self.settings):
            data = read_json(f"{self.settings.api_base_url}/models")
        models = [item.get("id") for item in data.get("data", []) if isinstance(item, dict) and isinstance(item.get("id"), str)]
        print(f"Default model: {self.settings.default_model}")
        print()
        print("Available models:")
        for model in models:
            marker = "*" if model == self.settings.default_model else "-"
            suffix = " (default)" if model == self.settings.default_model else ""
            print(f"  {marker} {model}{suffix}")
        return 0

    def model_check(self, dry_run: bool = False) -> int:
        if dry_run:
            print("Model check plan:")
            for model in [item.id for item in MODEL_CATALOG]:
                print(f"plan {model}")
            return 0

        self.ensure_auth()
        with BridgeProcess(self.settings):
            print("Checking Groc model access through ChatGPT OAuth...")
            failures = 0
            for model in [item.id for item in MODEL_CATALOG]:
                try:
                    response = post_json(
                        f"{self.settings.api_base_url}/responses",
                        {"model": model, "input": "Reply exactly groc-model-ok", "max_output_tokens": 32},
                    )
                    text = response.get("output_text")
                    if isinstance(text, str) and "groc-model-ok" in text:
                        print(f"ok   {model}")
                    else:
                        failures += 1
                        print(f"fail {model}")
                except Exception as exc:
                    failures += 1
                    print(f"fail {model}")
                    print(f"     {exc}")
        return 0 if failures == 0 else 1

    def update(self) -> int:
        if not command_exists("git"):
            raise GrocError("git is required for groc update")
        self.settings.update_dir.parent.mkdir(parents=True, exist_ok=True)
        if (self.settings.update_dir / ".git").is_dir():
            subprocess.run(["git", "-C", str(self.settings.update_dir), "fetch", "--prune", "origin"], check=True)
            subprocess.run(["git", "-C", str(self.settings.update_dir), "reset", "--hard", "origin/master"], check=True)
        else:
            if self.settings.update_dir.exists():
                shutil.rmtree(self.settings.update_dir)
            subprocess.run(["git", "clone", self.settings.repo_url, str(self.settings.update_dir)], check=True)
        subprocess.run([str(self.settings.update_dir / "bin" / "install")], check=True)
        print(f"groc: updated from {self.settings.repo_url}")
        return 0

    def run_grok(self, args: list[str]) -> int:
        self.ensure_config()
        self.ensure_auth()
        command = build_grok_command(self.settings, args)
        with BridgeProcess(self.settings):
            if self.settings.raw_stderr or not args:
                return subprocess.run(command, env=env_for_grok(self.settings)).returncode
            process = subprocess.Popen(
                command,
                env=env_for_grok(self.settings),
                stderr=subprocess.PIPE,
                text=True,
            )
            assert process.stderr is not None
            for line in process.stderr:
                if not is_noise_line(line):
                    print(line, end="", file=sys.stderr)
            return process.wait()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    settings = settings_from_env()
    app = GrocApp(settings)
    try:
        validate_trusted_endpoints(settings)
        if not argv or argv[0] not in {"help", "-h", "--help", "version", "-V", "--version", "login", "status", "doctor", "update", "models"}:
            return app.run_grok(argv)

        command = argv.pop(0)
        if command in {"help", "-h", "--help"}:
            print(usage(), end="")
            return 0
        if command in {"version", "-V", "--version"}:
            print(f"groc {groc.__version__}")
            return 0
        if command == "login":
            if argv in ([], ["--browser"]):
                return app.login(device=False)
            if argv == ["--device-auth"]:
                return app.login(device=True)
            raise GrocError(f"unknown login option: {' '.join(argv)}", 2)
        if command == "status":
            return app.status()
        if command == "doctor":
            if not argv:
                return app.doctor()
            if argv == ["--fix"]:
                return app.doctor_fix(yes=False)
            if argv == ["--fix", "--yes"] or argv == ["--yes", "--fix"]:
                return app.doctor_fix(yes=True)
            raise GrocError(f"unknown doctor option: {' '.join(argv)}", 2)
        if command == "update":
            return app.update()
        if command == "models":
            if not argv:
                return app.models()
            if argv[0] == "--check":
                remaining = argv[1:]
                if remaining not in ([], ["--dry-run"]):
                    raise GrocError(f"unknown models --check option: {' '.join(remaining)}", 2)
                return app.model_check(dry_run=remaining == ["--dry-run"])
            raise GrocError(f"unknown models option: {' '.join(argv)}", 2)
        raise GrocError(f"unknown command: {command}", 2)
    except KeyboardInterrupt:
        return 130
    except GrocError as exc:
        print(f"groc: {exc}", file=sys.stderr)
        return exc.status
    except ValueError as exc:
        print(f"groc: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
