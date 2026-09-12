"""Regression: POST /api/backup must accept empty object and PHP's []."""

from __future__ import annotations

import io
import json
import unittest

from nc_backup_web.server import Handler, parse_request_json


class ParseRequestJsonTests(unittest.TestCase):
    def test_empty_object(self) -> None:
        self.assertEqual(parse_request_json(b"{}"), {})

    def test_empty_array_from_php(self) -> None:
        self.assertEqual(parse_request_json(b"[]"), {})
        self.assertEqual(parse_request_json("[]"), {})

    def test_empty_body(self) -> None:
        self.assertEqual(parse_request_json(b""), {})
        self.assertEqual(parse_request_json(""), {})

    def test_object_with_fields(self) -> None:
        self.assertEqual(
            parse_request_json(b'{"enabled": true, "on_calendar": "02:30"}'),
            {"enabled": True, "on_calendar": "02:30"},
        )

    def test_nonempty_array_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            parse_request_json(b"[1]")
        self.assertEqual(str(ctx.exception), "JSON-Objekt erwartet")

    def test_wrong_types_rejected(self) -> None:
        for raw in (b'"text"', b"null", b"true", b"0"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError) as ctx:
                    parse_request_json(raw)
                self.assertEqual(str(ctx.exception), "JSON-Objekt erwartet")

    def test_invalid_json_still_raises(self) -> None:
        with self.assertRaises(json.JSONDecodeError):
            parse_request_json(b"{")


class ReadJsonHandlerTests(unittest.TestCase):
    def _read(self, raw: bytes, length: int | None = None) -> dict:
        fake = type("FakeHandler", (), {})()
        fake.headers = {"Content-Length": str(len(raw) if length is None else length)}
        fake.rfile = io.BytesIO(raw)
        return Handler._read_json(fake)

    def test_empty_content_length(self) -> None:
        fake = type("FakeHandler", (), {})()
        fake.headers = {}
        fake.rfile = io.BytesIO(b"ignored")
        self.assertEqual(Handler._read_json(fake), {})

    def test_handler_accepts_object_and_empty_array(self) -> None:
        self.assertEqual(self._read(b"{}"), {})
        self.assertEqual(self._read(b"[]"), {})
        self.assertEqual(self._read(b'{"provider":"local"}'), {"provider": "local"})

    def test_handler_rejects_nonempty_array(self) -> None:
        with self.assertRaises(ValueError):
            self._read(b'["x"]')


if __name__ == "__main__":
    unittest.main()
