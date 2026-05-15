from __future__ import annotations

import urllib.error
import urllib.request
from typing import Any, BinaryIO, Callable

from groc.auth import GrocAuthStore
from groc.bridge.wire import groc_wire_body, response_from_sse
from groc.errors import BridgeError
from groc.jsonutil import json_bytes


class GrocResponsesClient:
    def __init__(
        self,
        auth_store: GrocAuthStore,
        base_url: str,
        default_model: str,
        upstream_model: Callable[[str], str],
    ) -> None:
        self.auth_store = auth_store
        self.responses_url = f"{base_url.rstrip('/')}/responses"
        self.default_model = default_model
        self.upstream_model = upstream_model

    def open_response(self, body: dict[str, Any], stream: bool) -> BinaryIO:
        request_body = groc_wire_body(body, self.default_model, self.upstream_model)
        request_body["stream"] = stream
        return self._open_response(request_body, stream, allow_refresh=True)

    def response_json(self, body: dict[str, Any]) -> dict[str, Any]:
        with self.open_response(body, stream=True) as response:
            return response_from_sse(response)

    def _open_response(
        self,
        body: dict[str, Any],
        stream: bool,
        allow_refresh: bool,
    ) -> BinaryIO:
        request = urllib.request.Request(
            self.responses_url,
            data=json_bytes(body),
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream" if stream else "application/json",
                **self.auth_store.auth_headers(),
            },
            method="POST",
        )
        try:
            return urllib.request.urlopen(request, timeout=300)
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and allow_refresh:
                self.auth_store.refresh_after_unauthorized()
                return self._open_response(body, stream, allow_refresh=False)
            detail = exc.read().decode("utf-8", errors="replace")
            raise BridgeError(detail or f"ChatGPT backend returned HTTP {exc.code}", exc.code) from exc
        except Exception as exc:
            raise BridgeError(f"ChatGPT backend request failed: {exc}", 502) from exc
