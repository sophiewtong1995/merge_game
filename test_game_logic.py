import unittest

from game_logic import BASE_DRAGS, GameState, Piece


class GameLogicTests(unittest.TestCase):
    def setUp(self):
        self.game = GameState(seed=1)

    def clear_board(self):
        self.game.board = [
            [None for _ in range(self.game.cols)] for _ in range(self.game.rows)
        ]

    def test_initial_board_has_no_automatic_merges(self):
        for seed in range(20):
            self.assertIsNone(GameState(seed=seed).find_auto_merge())

    def test_horizontal_merge_keeps_left_cell(self):
        self.clear_board()
        self.game.board[0][0] = Piece("red", 1)
        self.game.board[0][1] = Piece("red", 1)
        result = self.game.auto_merge_once()
        self.assertEqual(result.kind, "merge")
        self.assertEqual(result.target, (0, 0))
        self.assertEqual(result.damage, 1)
        self.assertEqual(self.game.board[0][0], Piece("red", 2))
        self.assertIsNone(self.game.board[0][1])

    def test_vertical_merge_keeps_lower_cell(self):
        self.clear_board()
        self.game.board[2][4] = Piece("green", 2)
        self.game.board[3][4] = Piece("green", 2)
        result = self.game.auto_merge_once()
        self.assertEqual(result.target, (3, 4))
        self.assertEqual(result.damage, 2)
        self.assertIsNone(self.game.board[2][4])
        self.assertEqual(self.game.board[3][4], Piece("green", 3))

    def test_distant_matching_pieces_merge_at_drag_target(self):
        self.clear_board()
        self.game.board[0][0] = Piece("red", 1)
        self.game.board[5][6] = Piece("red", 1)
        result = self.game.move((0, 0), (5, 6))
        self.assertEqual(result.kind, "merge")
        self.assertEqual(result.target, (5, 6))
        self.assertIsNone(self.game.board[0][0])
        self.assertEqual(self.game.board[5][6], Piece("red", 2))
        self.assertEqual(self.game.moves_remaining, BASE_DRAGS - 1)

    def test_different_piece_returns_without_changing_board(self):
        self.clear_board()
        self.game.board[0][0] = Piece("red", 1)
        self.game.board[5][6] = Piece("blue", 1)
        result = self.game.move((0, 0), (5, 6))
        self.assertEqual(result.kind, "return")
        self.assertEqual(self.game.board[0][0], Piece("red", 1))
        self.assertEqual(self.game.board[5][6], Piece("blue", 1))
        self.assertEqual(self.game.moves_remaining, BASE_DRAGS)

    def test_empty_target_returns_without_moving_piece(self):
        self.clear_board()
        self.game.board[0][0] = Piece("green", 2)
        result = self.game.move((0, 0), (4, 4))
        self.assertEqual(result.kind, "return")
        self.assertEqual(self.game.board[0][0], Piece("green", 2))
        self.assertIsNone(self.game.board[4][4])

    def test_focus_uses_down_left_right_up_priority(self):
        self.clear_board()
        center = (2, 3)
        for cell in (center, (3, 3), (2, 2), (2, 4), (1, 3)):
            row, col = cell
            self.game.board[row][col] = Piece("blue", 1)
        result = self.game.auto_merge_once(center)
        self.assertEqual(result.target, (3, 3))
        self.assertIsNone(self.game.board[2][3])
        self.assertEqual(self.game.board[3][3], Piece("blue", 2))

    def test_optimal_path_builds_highest_level(self):
        self.clear_board()
        self.game.board[0][0] = Piece("red", 2)
        self.game.board[0][1] = Piece("red", 1)
        self.game.board[1][0] = Piece("red", 3)
        self.game.board[1][1] = Piece("red", 1)

        first = self.game.auto_merge_once()
        self.assertEqual(first.target, (0, 1))
        self.assertEqual(self.game.board[0][1], Piece("red", 2))

        second = self.game.auto_merge_once(first.target)
        self.assertEqual(second.target, (0, 0))
        self.assertEqual(self.game.board[0][0], Piece("red", 3))

        third = self.game.auto_merge_once(second.target)
        self.assertEqual(third.kind, "merge")
        self.assertEqual(third.target, (1, 0))
        self.assertEqual(self.game.board[1][0], Piece("red", 4))
        self.assertEqual(self.game.merges, 3)

    def test_chain_finishes_at_last_matching_piece(self):
        self.clear_board()
        self.game.board[0][0] = Piece("blue", 1)
        self.game.board[0][1] = Piece("blue", 1)
        self.game.board[0][2] = Piece("blue", 2)

        first = self.game.auto_merge_once()
        self.assertEqual(first.source, (0, 0))
        self.assertEqual(first.target, (0, 1))
        self.assertEqual(self.game.board[0][1], Piece("blue", 2))

        second = self.game.auto_merge_once(first.target)
        self.assertEqual(second.source, (0, 1))
        self.assertEqual(second.target, (0, 2))
        self.assertEqual(self.game.board[0][2], Piece("blue", 3))
        self.assertIsNone(self.game.board[0][1])

    def test_optimal_path_can_build_level_five_without_removing_it(self):
        self.clear_board()
        self.game.board[0][0] = Piece("green", 3)
        self.game.board[0][1] = Piece("green", 2)
        self.game.board[1][0] = Piece("green", 4)
        self.game.board[1][1] = Piece("green", 2)

        focus = None
        results = []
        for _ in range(3):
            result = self.game.auto_merge_once(focus)
            results.append(result.kind)
            focus = result.target

        self.assertEqual(results, ["merge", "merge", "max_merge"])
        self.assertEqual(self.game.board[1][0], Piece("green", 5))
        self.assertEqual(self.game.monsters["green"].hp, 30)

    def test_level_four_merge_creates_persistent_level_five(self):
        self.clear_board()
        self.game.board[0][0] = Piece("blue", 4)
        self.game.board[0][1] = Piece("blue", 4)
        result = self.game.auto_merge_once()
        self.assertEqual(result.kind, "max_merge")
        self.assertEqual(result.target, (0, 0))
        self.assertEqual(self.game.board[0][0], Piece("blue", 5))
        self.assertIsNone(self.game.board[0][1])
        self.assertEqual(result.damage, 8)
        self.assertEqual(self.game.monsters["blue"].hp, 30)

    def test_clicking_level_five_attacks_and_removes_it(self):
        self.clear_board()
        self.game.board[2][2] = Piece("blue", 5)
        result = self.game.activate((2, 2))
        self.assertEqual(result.kind, "attack")
        self.assertEqual(result.damage, 10)
        self.assertEqual(self.game.monsters["blue"].hp, 30)
        self.assertIsNone(self.game.board[2][2])
        self.game.resolve_attack(result.color, result.damage, result.target)
        self.assertEqual(self.game.monsters["blue"].hp, 20)

    def test_monsters_advance_together_after_whole_wave_is_defeated(self):
        self.clear_board()
        cells = {"red": (0, 0), "blue": (0, 1), "green": (0, 2)}
        for color, cell in cells.items():
            self.game.monsters[color].hp = 1
            row, col = cell
            self.game.board[row][col] = Piece(color, 5)

        red_attack = self.game.activate(cells["red"])
        blue_attack = self.game.activate(cells["blue"])
        first = self.game.resolve_attack("red", red_attack.damage, red_attack.target)
        second = self.game.resolve_attack("blue", blue_attack.damage, blue_attack.target)
        self.assertTrue(first.monster_defeated)
        self.assertTrue(second.monster_defeated)
        self.assertFalse(first.wave_cleared)
        self.assertEqual(self.game.monsters["red"].hp, 0)
        self.assertTrue(all(monster.stage == 1 for monster in self.game.monsters.values()))

        green_attack = self.game.activate(cells["green"])
        third = self.game.resolve_attack("green", green_attack.damage, green_attack.target)
        self.assertTrue(third.wave_cleared)
        self.assertTrue(all(monster.stage == 1 for monster in self.game.monsters.values()))
        self.assertTrue(all(monster.hp == 0 for monster in self.game.monsters.values()))

        self.assertTrue(self.game.advance_wave())
        self.assertTrue(all(monster.stage == 2 for monster in self.game.monsters.values()))
        self.assertTrue(all(monster.hp == 45 for monster in self.game.monsters.values()))
        self.assertEqual(self.game.moves_remaining, 30)

    def test_remaining_chain_damage_does_not_reach_next_wave(self):
        self.clear_board()
        self.game.monsters["red"].hp = 1
        self.game.monsters["blue"].hp = 0
        self.game.monsters["green"].hp = 0
        self.game.board[0][0] = Piece("red", 1)
        self.game.board[0][1] = Piece("red", 1)
        self.game.board[1][0] = Piece("blue", 2)
        self.game.board[1][1] = Piece("blue", 2)

        clearing_hit = self.game.move((0, 1), (0, 0))
        self.assertFalse(clearing_hit.wave_cleared)
        self.assertEqual(self.game.monsters["red"].hp, 1)
        resolved = self.game.resolve_attack("red", clearing_hit.damage, clearing_hit.target)
        self.assertTrue(resolved.wave_cleared)
        self.assertTrue(self.game.wave_cleared)

        remaining_merge = self.game.auto_merge_once((1, 0))
        self.game.resolve_attack("blue", remaining_merge.damage, remaining_merge.target)
        self.assertTrue(all(monster.stage == 1 for monster in self.game.monsters.values()))

        self.game.advance_wave()
        self.assertTrue(all(monster.hp == 45 for monster in self.game.monsters.values()))

    def test_level_five_is_not_consumed_for_already_defeated_color(self):
        self.clear_board()
        self.game.monsters["red"].hp = 0
        self.game.board[2][2] = Piece("red", 5)
        result = self.game.activate((2, 2))
        self.assertEqual(result.kind, "waiting")
        self.assertEqual(self.game.board[2][2], Piece("red", 5))

    def test_automatic_merge_does_not_consume_drag(self):
        self.clear_board()
        self.game.board[0][0] = Piece("red", 1)
        self.game.board[0][1] = Piece("red", 1)
        self.game.auto_merge_once()
        self.assertEqual(self.game.moves_remaining, BASE_DRAGS)

    def test_zero_drags_fails_only_after_usable_level_five_is_gone(self):
        self.clear_board()
        self.game.moves_remaining = 0
        self.game.board[0][0] = Piece("blue", 5)
        self.assertFalse(self.game.check_failure())
        self.assertFalse(self.game.game_over)

        attack = self.game.activate((0, 0))
        self.game.resolve_attack(attack.color, attack.damage, attack.target)
        self.assertTrue(self.game.check_failure())
        self.assertTrue(self.game.game_over)

    def test_no_manual_merge_when_drag_count_is_zero(self):
        self.clear_board()
        self.game.moves_remaining = 0
        self.game.board[0][0] = Piece("green", 1)
        self.game.board[5][6] = Piece("green", 1)
        result = self.game.move((0, 0), (5, 6))
        self.assertEqual(result.kind, "no_moves")
        self.assertEqual(self.game.board[0][0], Piece("green", 1))
        self.assertEqual(self.game.board[5][6], Piece("green", 1))

    def test_every_merge_level_has_expected_damage(self):
        for level, expected_damage in ((1, 1), (2, 2), (3, 4), (4, 8)):
            with self.subTest(level=level):
                game = GameState(seed=level)
                game.board = [[None for _ in range(game.cols)] for _ in range(game.rows)]
                game.board[0][0] = Piece("red", level)
                game.board[0][1] = Piece("red", level)
                result = game.auto_merge_once()
                self.assertEqual(result.damage, expected_damage)
                self.assertEqual(game.monsters["red"].hp, 30)
                game.resolve_attack(result.color, result.damage, result.target)
                self.assertEqual(game.monsters["red"].hp, 30 - expected_damage)

    def test_refill_removes_empty_cells(self):
        self.game.board[0][0] = None
        self.game.board[4][3] = None
        moves = self.game.refill()
        new_moves = [move for move in moves if move.is_new]
        self.assertTrue(moves)
        self.assertTrue(new_moves)
        self.assertTrue(all(piece is not None for row in self.game.board for piece in row))
        self.assertTrue(all(move.piece.level in (1, 2) for move in new_moves))

    def test_refill_reports_existing_falls_and_new_pieces_from_above(self):
        self.clear_board()
        self.game.board[1][0] = Piece("red", 2)
        self.game.board[4][0] = Piece("blue", 1)
        moves = self.game.refill()
        column_moves = [move for move in moves if move.target[1] == 0]
        existing = [move for move in column_moves if not move.is_new]
        new_moves = [move for move in column_moves if move.is_new]
        self.assertEqual({move.target for move in existing}, {(4, 0), (5, 0)})
        self.assertTrue(all(move.source[0] < 0 for move in new_moves))


if __name__ == "__main__":
    unittest.main()
