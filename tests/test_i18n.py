"""Tests für i18n."""

import unittest

from nc_backup.i18n import Translator, detect_browser_lang, normalize_lang


class I18nTests(unittest.TestCase):
    def test_german_default(self) -> None:
        self.assertEqual(Translator("de")("backup_now"), "Backup jetzt starten")

    def test_english(self) -> None:
        self.assertEqual(Translator("en")("backup_now"), "Start backup now")

    def test_browser_lang(self) -> None:
        self.assertEqual(detect_browser_lang("en-US,en;q=0.9"), "en")
        self.assertEqual(detect_browser_lang("de-DE,de;q=0.9"), "de")

    def test_normalize(self) -> None:
        self.assertEqual(normalize_lang("EN"), "en")
        self.assertEqual(normalize_lang("fr"), "de")


if __name__ == "__main__":
    unittest.main()
