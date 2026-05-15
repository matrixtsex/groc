from __future__ import annotations

import os

from groc.models import MODEL_CATALOG
from groc.settings import Settings


def toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_grok_config(settings: Settings) -> str:
    lines = [
        "[models]",
        f"default = {toml_string(settings.default_model)}",
        "",
        "[subagents]",
        "enabled = true",
        f"default_model = {toml_string(settings.default_model)}",
        "",
        "[features]",
        "telemetry = false",
        "lsp_tools = false",
        "",
        "[memory]",
        "enabled = false",
        "",
    ]

    for model in MODEL_CATALOG:
        configured_model = settings.upstream_model if model.id == "grok-build" else model.id
        lines.extend(
            [
                f"[model.{toml_string(model.id)}]",
                f"model = {toml_string(configured_model)}",
                f"base_url = {toml_string(settings.api_base_url)}",
                f"name = {toml_string(model.name + ' (ChatGPT OAuth)')}",
                'api_key = "local"',
                'api_backend = "responses"',
                "context_window = 1000000",
                "",
            ]
        )

    lines.extend(
        [
            "[ui]",
            "max_thoughts_width = 120",
            f"fork_secondary_model = {toml_string(settings.default_model)}",
            "yolo = false",
            "compact_mode = false",
            "",
        ]
    )
    return "\n".join(lines)


def write_grok_config(settings: Settings) -> None:
    settings.home.mkdir(parents=True, exist_ok=True)
    path = settings.home / "config.toml"
    tmp = path.with_suffix(".toml.tmp")
    tmp.write_text(render_grok_config(settings), encoding="utf-8")
    os.replace(tmp, path)
