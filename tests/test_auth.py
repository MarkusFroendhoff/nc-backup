"""Tests für API-Token."""

import unittest

from nc_backup.auth import hash_api_token, verify_api_token


class ApiTokenTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        token = "test-token-value"
        digest = hash_api_token(token)
        self.assertTrue(verify_api_token(token, digest))
        self.assertFalse(verify_api_token("other", digest))
        self.assertFalse(verify_api_token(token, None))
        self.assertFalse(verify_api_token("", digest))
