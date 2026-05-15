from __future__ import annotations

import io
import unittest

from groc.bridge.server import BridgeHandler
from groc.errors import BridgeError


class BridgeServerTests(unittest.TestCase):
    def handler_with_body(self, body: bytes, content_length: str | None = None) -> BridgeHandler:
        handler = object.__new__(BridgeHandler)
        handler.headers = {"content-length": str(len(body)) if content_length is None else content_length}
        handler.rfile = io.BytesIO(body)
        return handler

    def test_read_json_accepts_object_body(self) -> None:
        handler = self.handler_with_body(b'{"model":"gpt-5.5"}')

        self.assertEqual(handler.read_json(), {"model": "gpt-5.5"})

    def test_read_json_rejects_bad_content_length_as_client_error(self) -> None:
        handler = self.handler_with_body(b"{}", content_length="bad")

        with self.assertRaises(BridgeError) as raised:
            handler.read_json()

        self.assertEqual(raised.exception.status, 400)

    def test_read_json_rejects_invalid_json_as_client_error(self) -> None:
        handler = self.handler_with_body(b"{")

        with self.assertRaises(BridgeError) as raised:
            handler.read_json()

        self.assertEqual(raised.exception.status, 400)

    def test_read_json_rejects_non_object_json_as_client_error(self) -> None:
        handler = self.handler_with_body(b'["not", "an", "object"]')

        with self.assertRaises(BridgeError) as raised:
            handler.read_json()

        self.assertEqual(raised.exception.status, 400)


if __name__ == "__main__":
    unittest.main()
