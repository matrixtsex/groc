from __future__ import annotations

import base64
import json
import tempfile
import time
import unittest
from pathlib import Path

from groc.auth import GrocAuthStore, decode_jwt_payload, jwt_expired


def jwt_with(payload: dict[str, object]) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii").rstrip("=")
    return f"header.{encoded}.signature"


class GrocAuthStoreTests(unittest.TestCase):
    def test_decode_jwt_payload_tolerates_invalid_values(self) -> None:
        self.assertEqual(decode_jwt_payload("not-a-jwt"), {})
        self.assertEqual(decode_jwt_payload("a.b.c"), {})

    def test_ready_and_summary_use_codex_chatgpt_oauth_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            auth_home = Path(directory)
            access = jwt_with({"exp": int(time.time()) + 3600})
            (auth_home / "auth.json").write_text(
                json.dumps(
                    {
                        "auth_mode": "chatgpt",
                        "tokens": {
                            "access_token": access,
                            "refresh_token": "refresh",
                            "account_id": "acct_1234567890",
                        },
                    }
                ),
                encoding="utf-8",
            )

            store = GrocAuthStore(auth_home)
            summary = store.summary()

            self.assertTrue(store.ready())
            self.assertTrue(summary.ok)
            self.assertIn("acct...7890", summary.message)
            self.assertNotIn("acct_1234567890", summary.message)

    def test_ready_rejects_missing_refresh_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            auth_home = Path(directory)
            (auth_home / "auth.json").write_text(
                json.dumps({"auth_mode": "chatgpt", "tokens": {"access_token": "access"}}),
                encoding="utf-8",
            )

            self.assertFalse(GrocAuthStore(auth_home).ready())

    def test_jwt_expired_applies_refresh_skew(self) -> None:
        expired = jwt_with({"exp": int(time.time()) - 1})
        nearly_expired = jwt_with({"exp": int(time.time()) + 10})
        valid = jwt_with({"exp": int(time.time()) + 3600})

        self.assertTrue(jwt_expired(expired))
        self.assertTrue(jwt_expired(nearly_expired))
        self.assertFalse(jwt_expired(valid))


if __name__ == "__main__":
    unittest.main()
