from __future__ import annotations

import unittest

from groc.models import MODEL_CATALOG, upstream_model


class ModelTests(unittest.TestCase):
    def test_catalog_contains_public_model_ids(self) -> None:
        ids = [model.id for model in MODEL_CATALOG]

        self.assertEqual(ids[0], "gpt-5.5")
        self.assertIn("gpt-5.4", ids)
        self.assertIn("gpt-5.3-spark", ids)
        self.assertIn("grok-build", ids)

    def test_upstream_aliases_match_chatgpt_backend_ids(self) -> None:
        self.assertEqual(upstream_model("gpt-5.3"), "gpt-5.3-codex")
        self.assertEqual(upstream_model("gpt-5.3-spark"), "gpt-5.3-codex-spark")
        self.assertEqual(upstream_model("grok-build", fallback="gpt-5.5"), "gpt-5.5")
        self.assertEqual(upstream_model("gpt-5.4"), "gpt-5.4")


if __name__ == "__main__":
    unittest.main()
