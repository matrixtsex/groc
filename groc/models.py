from __future__ import annotations

from dataclasses import dataclass


DEFAULT_MODEL = "gpt-5.5"
DEFAULT_UPSTREAM_MODEL = "gpt-5.5"


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str


MODEL_CATALOG: tuple[ModelInfo, ...] = (
    ModelInfo("gpt-5.5", "GPT-5.5"),
    ModelInfo("gpt-5.4", "GPT-5.4"),
    ModelInfo("gpt-5.4-mini", "GPT-5.4 Mini"),
    ModelInfo("gpt-5.3", "GPT-5.3"),
    ModelInfo("gpt-5.3-spark", "GPT-5.3 Spark"),
    ModelInfo("gpt-5.2", "GPT-5.2"),
    ModelInfo("grok-build", "Groc fallback via GPT-5.5"),
)


def upstream_model(model: str, fallback: str = DEFAULT_UPSTREAM_MODEL) -> str:
    aliases = {
        "grok-build": fallback,
        "gpt-5.3": "gpt-5.3-codex",
        "gpt-5.3-spark": "gpt-5.3-codex-spark",
    }
    return aliases.get(model, model)
