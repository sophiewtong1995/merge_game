import time
import unittest
from types import SimpleNamespace
from unittest import mock

import pygame

import game as game_module
from game import Game


class EscapeKeyTests(unittest.TestCase):
    def dispatch_escape(self, *, browser: bool, during_level_clear: bool) -> bool:
        instance = Game.__new__(Game)
        instance.running = True
        instance.level_clear_started_at = time.monotonic() if during_level_clear else 0.0
        event = SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_ESCAPE)

        with (
            mock.patch.object(game_module, "RUNNING_IN_BROWSER", browser),
            mock.patch.object(pygame.event, "get", return_value=[event]),
        ):
            instance.events()

        return instance.running

    def test_escape_is_ignored_in_browser(self):
        for during_level_clear in (False, True):
            with self.subTest(during_level_clear=during_level_clear):
                self.assertTrue(
                    self.dispatch_escape(
                        browser=True, during_level_clear=during_level_clear
                    )
                )

    def test_escape_still_exits_desktop_game(self):
        for during_level_clear in (False, True):
            with self.subTest(during_level_clear=during_level_clear):
                self.assertFalse(
                    self.dispatch_escape(
                        browser=False, during_level_clear=during_level_clear
                    )
                )


if __name__ == "__main__":
    unittest.main()
