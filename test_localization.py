import unittest

from localization import DEFAULT_LANGUAGE, TEXT, translate


class LocalizationTests(unittest.TestCase):
    def test_english_is_the_release_default(self):
        self.assertEqual(DEFAULT_LANGUAGE, "en")

    def test_every_language_has_the_same_message_keys(self):
        expected = set(TEXT[DEFAULT_LANGUAGE])
        for language, messages in TEXT.items():
            with self.subTest(language=language):
                self.assertEqual(set(messages), expected)

    def test_formatted_messages_use_runtime_values(self):
        self.assertEqual(translate("en", "moves", count=24), "24 MOVES")
        self.assertEqual(translate("en", "damage_popup", damage=20), "20 DAMAGE")
        self.assertEqual(
            translate("en", "level_wave", level=1, wave=1, total=3),
            "LEVEL 1 · WAVE 1/3",
        )


if __name__ == "__main__":
    unittest.main()
