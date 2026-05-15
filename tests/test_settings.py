from __future__ import annotations

import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from groc.settings import DEFAULT_BACKEND_BASE_URL, DEFAULT_REFRESH_URL, settings_from_env, validate_trusted_endpoints


class SettingsTests(unittest.TestCase):
    def test_defaults_are_local_and_trusted(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = settings_from_env()

        self.assertEqual(settings.bridge_host, "127.0.0.1")
        self.assertEqual(settings.backend_base_url, DEFAULT_BACKEND_BASE_URL)
        self.assertEqual(settings.refresh_url, DEFAULT_REFRESH_URL)
        validate_trusted_endpoints(settings)

    def test_backend_override_requires_explicit_unsafe_opt_in(self) -> None:
        settings = replace(settings_from_env(), backend_base_url="https://example.invalid")

        with self.assertRaises(ValueError):
            validate_trusted_endpoints(settings)

        validate_trusted_endpoints(replace(settings, allow_untrusted_backend=True))

    def test_refresh_override_requires_explicit_unsafe_opt_in(self) -> None:
        settings = replace(settings_from_env(), refresh_url="https://example.invalid/oauth/token")

        with self.assertRaises(ValueError):
            validate_trusted_endpoints(settings)

        validate_trusted_endpoints(replace(settings, allow_untrusted_backend=True))


if __name__ == "__main__":
    unittest.main()
