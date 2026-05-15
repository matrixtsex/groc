from __future__ import annotations

import json
from typing import Any


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")
