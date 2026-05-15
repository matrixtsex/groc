from __future__ import annotations


class GrocError(RuntimeError):
    """User-facing Groc failure."""

    def __init__(self, message: str, status: int = 1) -> None:
        super().__init__(message)
        self.status = status


class BridgeError(RuntimeError):
    """HTTP bridge error sent back as an OpenAI-compatible error payload."""

    def __init__(self, message: str, status: int = 500) -> None:
        super().__init__(message)
        self.status = status
