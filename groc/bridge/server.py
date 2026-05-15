from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, BinaryIO

from groc.auth import GrocAuthStore
from groc.bridge.client import GrocResponsesClient
from groc.bridge.wire import extract_output_text, responses_input_from_chat
from groc.errors import BridgeError
from groc.jsonutil import json_bytes
from groc.models import MODEL_CATALOG, upstream_model
from groc.settings import settings_from_env, validate_trusted_endpoints


MAX_REQUEST_BYTES = 8 * 1024 * 1024


def write_sse_event(wfile: Any, event: dict[str, Any]) -> None:
    if isinstance(event.get("type"), str):
        wfile.write(f"event: {event['type']}\n".encode("utf-8"))
    wfile.write(b"data: " + json_bytes(event) + b"\n\n")
    wfile.flush()


def relay_responses_stream(response: BinaryIO, wfile: Any) -> None:
    output_items: list[dict[str, Any]] = []
    current_event_lines: list[str] = []

    def handle_event(lines: list[str]) -> None:
        data_lines = [line[5:].lstrip() for line in lines if line.startswith("data:")]
        if not data_lines:
            return
        data = "\n".join(data_lines)
        if data == "[DONE]":
            wfile.write(b"data: [DONE]\n\n")
            wfile.flush()
            return
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            wfile.write(("data: " + data + "\n\n").encode("utf-8"))
            wfile.flush()
            return
        if not isinstance(event, dict):
            return

        if event.get("type") == "response.output_item.done" and isinstance(event.get("item"), dict):
            output_items.append(event["item"])
        elif event.get("type") in {"response.completed", "response.incomplete"}:
            response_obj = event.get("response")
            if isinstance(response_obj, dict) and not response_obj.get("output"):
                response_obj["output"] = output_items
                event["response"] = response_obj
        write_sse_event(wfile, event)

    for raw_line in response:
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line:
            handle_event(current_event_lines)
            current_event_lines = []
        else:
            current_event_lines.append(line)
    if current_event_lines:
        handle_event(current_event_lines)


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "groc-bridge/0.4"

    @property
    def groc(self) -> GrocResponsesClient:
        return self.server.groc  # type: ignore[attr-defined]

    @property
    def default_model(self) -> str:
        return self.server.default_model  # type: ignore[attr-defined]

    @property
    def upstream_model_name(self) -> str:
        return self.server.upstream_model_name  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("content-length", "0") or "0")
        except ValueError as exc:
            raise BridgeError("invalid content-length header", 400) from exc
        if length > MAX_REQUEST_BYTES:
            raise BridgeError("request body is too large", 413)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BridgeError("request body must be valid JSON", 400) from exc
        if not isinstance(value, dict):
            raise BridgeError("request body must be a JSON object", 400)
        return value

    def send_json(self, value: Any, status: int = 200) -> None:
        body = json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message: str, status: int = 500) -> None:
        self.send_json({"error": {"message": message, "type": "bridge_error"}}, status=status)

    def send_sse_events(self, events: list[dict[str, Any]]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for event in events:
            self.wfile.write(b"data: " + json_bytes(event) + b"\n\n")
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/v1/models":
            self.send_json(
                {
                    "object": "list",
                    "data": [
                        {
                            "id": model.id,
                            "object": "model",
                            "created": 0,
                            "owned_by": "groc",
                            "name": model.name,
                        }
                        for model in MODEL_CATALOG
                    ],
                }
            )
            return
        if self.path.rstrip("/") == "/health":
            self.send_json({"ok": True, "model": self.default_model, "upstream_model": self.upstream_model_name})
            return
        self.send_error_json("not found", status=404)

    def do_POST(self) -> None:
        try:
            if self.path.rstrip("/") == "/v1/responses":
                self.handle_responses()
                return
            if self.path.rstrip("/") == "/v1/chat/completions":
                self.handle_chat_completions()
                return
            self.send_error_json("not found", status=404)
        except BridgeError as exc:
            sys.stderr.write(f"bridge error {exc.status}: {str(exc)[:500]}\n")
            self.send_error_json(str(exc), status=exc.status)
        except Exception as exc:
            sys.stderr.write(f"bridge unexpected error: {str(exc)[:500]}\n")
            self.send_error_json("internal bridge error", status=500)

    def handle_responses(self) -> None:
        body = self.read_json()
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            with self.groc.open_response(body, stream=True) as response:
                relay_responses_stream(response, self.wfile)
            return

        response = self.groc.response_json(body)
        response.setdefault("output_text", extract_output_text(response))
        self.send_json(response)

    def handle_chat_completions(self) -> None:
        body = self.read_json()
        requested_model = str(body.get("model") or self.default_model)
        responses_body: dict[str, Any] = {
            "model": requested_model,
            "input": responses_input_from_chat(body),
        }
        for source, target in [
            ("max_tokens", "max_output_tokens"),
            ("max_completion_tokens", "max_output_tokens"),
            ("temperature", "temperature"),
            ("top_p", "top_p"),
        ]:
            if source in body:
                responses_body[target] = body[source]

        response = self.groc.response_json(responses_body)
        text = extract_output_text(response)
        completion_id = "chatcmpl_" + uuid.uuid4().hex
        created = int(time.time())
        if body.get("stream"):
            self.send_sse_events(
                [
                    {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": requested_model,
                        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
                    },
                    {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": requested_model,
                        "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
                    },
                    {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": requested_model,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    },
                ]
            )
            return

        self.send_json(
            {
                "id": completion_id,
                "object": "chat.completion",
                "created": created,
                "model": requested_model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": text},
                        "finish_reason": "stop",
                    }
                ],
                "usage": response.get("usage"),
            }
        )


class GrocBridgeServer(ThreadingHTTPServer):
    allow_reuse_address = True
    groc: GrocResponsesClient
    default_model: str
    upstream_model_name: str


def create_server(
    host: str,
    port: int,
    auth_home: Path,
    backend_base_url: str,
    refresh_url: str,
    default_model: str,
    upstream_model_name: str,
) -> GrocBridgeServer:
    auth_store = GrocAuthStore(auth_home, refresh_url=refresh_url)
    server = GrocBridgeServer((host, port), BridgeHandler)
    server.groc = GrocResponsesClient(
        auth_store,
        backend_base_url,
        default_model=default_model,
        upstream_model=lambda model: upstream_model(model, upstream_model_name),
    )
    server.default_model = default_model
    server.upstream_model_name = upstream_model_name
    return server


def main(argv: list[str] | None = None) -> int:
    settings = settings_from_env()
    try:
        validate_trusted_endpoints(settings)
    except ValueError as exc:
        print(f"groc-bridge: {exc}", file=sys.stderr)
        return 2

    parser = argparse.ArgumentParser(description="Groc OpenAI-compatible bridge backed by ChatGPT OAuth")
    parser.add_argument("--host", default=settings.bridge_host)
    parser.add_argument("--port", type=int, default=settings.bridge_port)
    parser.add_argument("--auth-home", dest="auth_home", default=str(settings.auth_home))
    parser.add_argument("--backend-base-url", dest="backend_base_url", default=settings.backend_base_url)
    args = parser.parse_args(argv)

    server = create_server(
        args.host,
        args.port,
        Path(args.auth_home).expanduser(),
        args.backend_base_url.rstrip("/"),
        settings.refresh_url,
        settings.default_model,
        settings.upstream_model,
    )
    print(f"groc bridge listening on http://{args.host}:{args.port}/v1", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
