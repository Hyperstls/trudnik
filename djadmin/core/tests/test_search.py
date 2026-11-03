"""Full-text query helper (J132)."""
from django.test import SimpleTestCase

from core.search import ts_query


class TsQueryTests(SimpleTestCase):
    def test_single_cyrillic_word_with_prefix(self):
        self.assertEqual(ts_query("Уборка"), "Уборка:*")

    def test_multiple_words_are_anded(self):
        self.assertEqual(ts_query("Уборка Москва"), "Уборка & Москва:*")

    def test_latin_or_digits_fall_back(self):
        self.assertEqual(ts_query("IT"), "")
        self.assertEqual(ts_query("111"), "")
        self.assertEqual(ts_query("уборка 2"), "")

    def test_short_or_punctuation_only_falls_back(self):
        self.assertEqual(ts_query("у"), "")
        self.assertEqual(ts_query("!!!"), "")

    def test_quotes_are_not_injected(self):
        self.assertEqual(ts_query("уборка'"), "уборка:*")
