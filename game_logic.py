from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Optional


COLORS = ("red", "blue", "green")
MAX_LEVEL = 5
MERGE_DAMAGE = {1: 1, 2: 2, 3: 4, 4: 8}
MAX_LEVEL_ATTACK = 10
BASE_DRAGS = 24
DRAGS_PER_STAGE = 6


@dataclass(frozen=True)
class WaveSpec:
    kind: str
    hp: int


@dataclass(frozen=True)
class LevelSpec:
    moves: int
    waves: tuple[WaveSpec, ...]


LEVELS = (
    LevelSpec(24, (WaveSpec("normal", 30),)),
    LevelSpec(42, (WaveSpec("normal", 36), WaveSpec("boss", 150))),
    LevelSpec(
        60,
        (WaveSpec("normal", 42), WaveSpec("normal", 48), WaveSpec("boss", 210)),
    ),
    LevelSpec(
        82,
        (
            WaveSpec("normal", 52),
            WaveSpec("boss", 200),
            WaveSpec("normal", 58),
            WaveSpec("boss", 270),
        ),
    ),
)


@dataclass
class Piece:
    color: str
    level: int = 1


@dataclass
class Monster:
    color: str
    stage: int = 1
    hp: int = 30
    max_hp: int = 30
    defeated: int = 0

    def take_damage(self, amount: int) -> bool:
        if self.hp <= 0:
            return False
        self.hp = max(0, self.hp - amount)
        if self.hp > 0:
            return False
        self.defeated += 1
        return True

    def advance(self) -> None:
        self.stage += 1
        self.max_hp = 30 + (self.stage - 1) * 15
        self.hp = self.max_hp


@dataclass
class MoveResult:
    kind: str
    damage: int = 0
    color: Optional[str] = None
    monster_defeated: bool = False
    wave_cleared: bool = False
    source: Optional[tuple[int, int]] = None
    target: Optional[tuple[int, int]] = None
    source_level: int = 0


@dataclass
class RefillMove:
    piece: Piece
    source: tuple[int, int]
    target: tuple[int, int]
    is_new: bool = False


class GameState:
    rows = 6
    cols = 7

    def __init__(self, seed: Optional[int] = None):
        self.random = random.Random(seed)
        self.board: list[list[Optional[Piece]]] = [
            [None for _ in range(self.cols)] for _ in range(self.rows)
        ]
        self.level = 1
        self.wave_index = 0
        self.monsters: dict[str, Monster] = {}
        self.boss: Optional[Monster] = None
        self.score = 0
        self.merges = 0
        self.moves_remaining = self.level_spec.moves
        self.game_over = False
        self.game_won = False
        self.wave_cleared = False
        self._load_wave()
        self._fill_initial_board()

    @staticmethod
    def moves_for_stage(stage: int) -> int:
        if 1 <= stage <= len(LEVELS):
            return LEVELS[stage - 1].moves
        return BASE_DRAGS + (stage - 1) * DRAGS_PER_STAGE

    @property
    def level_spec(self) -> LevelSpec:
        return LEVELS[self.level - 1]

    @property
    def wave_spec(self) -> WaveSpec:
        return self.level_spec.waves[self.wave_index]

    @property
    def wave_number(self) -> int:
        return self.wave_index + 1

    @property
    def total_waves(self) -> int:
        return len(self.level_spec.waves)

    @property
    def is_boss_wave(self) -> bool:
        return self.wave_spec.kind == "boss"

    def _load_wave(self) -> None:
        """载入当前波；棋盘与本关剩余拖拽次数都不会在这里重置。"""
        spec = self.wave_spec
        self.wave_cleared = False
        if spec.kind == "boss":
            boss_number = sum(
                wave.kind == "boss"
                for wave in self.level_spec.waves[: self.wave_index + 1]
            )
            self.boss = Monster(
                "boss", stage=boss_number, hp=spec.hp, max_hp=spec.hp
            )
            self.monsters = {}
        else:
            self.boss = None
            self.monsters = {
                color: Monster(
                    color, stage=self.level, hp=spec.hp, max_hp=spec.hp
                )
                for color in COLORS
            }

    def _new_piece(self) -> Piece:
        return Piece(self.random.choice(COLORS), self.random.choice((1, 1, 1, 2)))

    def _fill_initial_board(self) -> None:
        """生成没有横向或纵向相同邻居的初始棋盘。"""
        choices = [Piece(color, level) for color in COLORS for level in (1, 2)]
        for row in range(self.rows):
            for col in range(self.cols):
                blocked = set()
                if row > 0 and self.board[row - 1][col]:
                    above = self.board[row - 1][col]
                    blocked.add((above.color, above.level))
                if col > 0 and self.board[row][col - 1]:
                    left = self.board[row][col - 1]
                    blocked.add((left.color, left.level))
                available = [piece for piece in choices if (piece.color, piece.level) not in blocked]
                picked = self.random.choice(available)
                self.board[row][col] = Piece(picked.color, picked.level)

    def valid_cell(self, cell: tuple[int, int]) -> bool:
        row, col = cell
        return 0 <= row < self.rows and 0 <= col < self.cols

    def move(self, source: tuple[int, int], target: tuple[int, int]) -> MoveResult:
        if self.game_over or self.game_won:
            return MoveResult("game_over")
        if not self.valid_cell(source) or not self.valid_cell(target) or source == target:
            return MoveResult("invalid")

        sr, sc = source
        tr, tc = target
        first = self.board[sr][sc]
        second = self.board[tr][tc]
        if first is None:
            return MoveResult("invalid")

        if self._same(first, second) and first.level < MAX_LEVEL:
            if self.moves_remaining <= 0:
                return MoveResult("no_moves")
            self.moves_remaining -= 1
            return self._merge_cells(source, target)

        return MoveResult("return")

    @staticmethod
    def _same(first: Optional[Piece], second: Optional[Piece]) -> bool:
        return bool(
            first
            and second
            and first.color == second.color
            and first.level == second.level
        )

    def activate(self, cell: tuple[int, int]) -> MoveResult:
        """单击最高级物品时将其消耗，并攻击对应颜色的怪物。"""
        if self.game_over or self.game_won:
            return MoveResult("game_over")
        if not self.valid_cell(cell):
            return MoveResult("invalid")
        row, col = cell
        piece = self.board[row][col]
        if piece is None or piece.level != MAX_LEVEL:
            return MoveResult("inactive")
        if not self.is_boss_wave and self.monsters[piece.color].hp <= 0:
            self.board[row][col] = None
            return MoveResult("clear", color=piece.color, target=cell)

        damage = MAX_LEVEL_ATTACK
        self.board[row][col] = None
        return MoveResult(
            "attack",
            damage=damage,
            color=piece.color,
            target=cell,
        )

    def resolve_attack(
        self, color: str, damage: int, target: Optional[tuple[int, int]] = None
    ) -> MoveResult:
        """炮弹发射时统一扣除怪物生命。"""
        defeated, cleared = self._deal_damage(color, damage)
        self.score += damage * 5 + (50 if defeated else 0) + (100 if cleared else 0)
        return MoveResult(
            "attack_resolved",
            damage=damage,
            color=color,
            monster_defeated=defeated,
            wave_cleared=cleared,
            target=target,
        )

    def _deal_damage(self, color: str, damage: int) -> tuple[bool, bool]:
        if self.wave_cleared:
            return False, False
        if self.is_boss_wave:
            assert self.boss is not None
            defeated = self.boss.take_damage(damage)
            cleared = self.boss.hp <= 0
        else:
            defeated = self.monsters[color].take_damage(damage)
            cleared = all(monster.hp <= 0 for monster in self.monsters.values())
        if cleared:
            self.wave_cleared = True
        return defeated, cleared

    def advance_wave(self) -> Optional[str]:
        """结算完成后进入下一波或下一关，并描述发生的转场。"""
        if not self.wave_cleared:
            return None
        if self.wave_index + 1 < self.total_waves:
            self.wave_index += 1
            self._load_wave()
            return "wave"
        if self.level < len(LEVELS):
            self.level += 1
            self.wave_index = 0
            self.moves_remaining = self.level_spec.moves
            self._load_wave()
            return "level"
        self.game_won = True
        return "won"

    def has_usable_max_piece(self) -> bool:
        for row in self.board:
            for piece in row:
                if piece and piece.level == MAX_LEVEL:
                    return True
        return False

    def check_failure(self) -> bool:
        if self.moves_remaining <= 0 and not self.has_usable_max_piece():
            self.game_over = True
        return self.game_over

    def _pair_for_direction(
        self, cell: tuple[int, int], neighbor: tuple[int, int]
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        """返回 source、target；横向留左格，纵向留下格。"""
        row, col = cell
        other_row, other_col = neighbor
        if row == other_row:
            target = (row, min(col, other_col))
        else:
            target = (max(row, other_row), col)
        source = neighbor if target == cell else cell
        return source, target

    def _ordered_merge_options(
        self, focus: Optional[tuple[int, int]] = None
    ) -> list[tuple[tuple[int, int], tuple[int, int]]]:
        """列出相邻合成及两种落点；旧方向规则用于最优路径相同时的排序。"""
        options: list[tuple[tuple[int, int], tuple[int, int]]] = []
        seen: set[frozenset[tuple[int, int]]] = set()

        def add_pair(
            cell: tuple[int, int],
            neighbor: tuple[int, int],
            prefer_forward: bool = False,
        ) -> None:
            row, col = cell
            nr, nc = neighbor
            if not self._same(self.board[row][col], self.board[nr][nc]):
                return
            if self.board[row][col].level >= MAX_LEVEL:  # type: ignore[union-attr]
                return
            pair_key = frozenset((cell, neighbor))
            if pair_key in seen:
                return
            seen.add(pair_key)
            if prefer_forward:
                options.append((cell, neighbor))
                options.append((neighbor, cell))
            else:
                preferred = self._pair_for_direction(cell, neighbor)
                options.append(preferred)
                options.append((preferred[1], preferred[0]))

        if focus and self.valid_cell(focus):
            row, col = focus
            for dr, dc in ((1, 0), (0, -1), (0, 1), (-1, 0)):
                neighbor = (row + dr, col + dc)
                if self.valid_cell(neighbor):
                    add_pair(focus, neighbor, prefer_forward=True)

        for row in range(self.rows - 1, -1, -1):
            for col in range(self.cols):
                for dr, dc in ((1, 0), (0, -1), (0, 1), (-1, 0)):
                    neighbor = (row + dr, col + dc)
                    if self.valid_cell(neighbor):
                        add_pair((row, col), neighbor)
        return options

    @staticmethod
    def _piece_key(piece: Optional[Piece]) -> Optional[tuple[str, int]]:
        return None if piece is None else (piece.color, piece.level)

    def _board_key(self) -> tuple[tuple[Optional[tuple[str, int]], ...], ...]:
        return tuple(tuple(self._piece_key(piece) for piece in row) for row in self.board)

    @staticmethod
    def _simulate_merge(
        board: tuple[tuple[Optional[tuple[str, int]], ...], ...],
        source: tuple[int, int],
        target: tuple[int, int],
    ) -> tuple[tuple[tuple[Optional[tuple[str, int]], ...], ...], int]:
        mutable = [list(row) for row in board]
        sr, sc = source
        tr, tc = target
        color, level = mutable[tr][tc]  # type: ignore[misc]
        new_level = level + 1
        mutable[sr][sc] = None
        mutable[tr][tc] = (color, new_level)
        return tuple(tuple(row) for row in mutable), new_level

    def _best_chain_score(
        self,
        board: tuple[tuple[Optional[tuple[str, int]], ...], ...],
        focus: tuple[int, int],
    ) -> tuple[int, int]:
        """返回从新合成物继续出发可达到的最高等级和连续合成次数。"""
        row, col = focus
        piece = board[row][col]
        if piece is None:
            return (0, 0)

        best = (piece[1], 0)
        for dr, dc in ((1, 0), (0, -1), (0, 1), (-1, 0)):
            neighbor = (row + dr, col + dc)
            if not self.valid_cell(neighbor):
                continue
            nr, nc = neighbor
            if board[nr][nc] != piece:
                continue
            # 连锁时优先让刚生成的物品继续前进到下一个物品的位置。
            for source, target in ((focus, neighbor), (neighbor, focus)):
                next_board, created_level = self._simulate_merge(board, source, target)
                if created_level >= MAX_LEVEL:
                    score = (created_level, 1)
                else:
                    child_level, child_merges = self._best_chain_score(next_board, target)
                    score = (max(created_level, child_level), 1 + child_merges)
                if score > best:
                    best = score
        return best

    def find_auto_merge(
        self, focus: Optional[tuple[int, int]] = None
    ) -> Optional[tuple[tuple[int, int], tuple[int, int]]]:
        """选择能形成最高级连续合成的第一步。"""
        board = self._board_key()
        best_pair = None
        best_score = (0, 0)
        for source, target in self._ordered_merge_options(focus):
            next_board, created_level = self._simulate_merge(board, source, target)
            if created_level >= MAX_LEVEL:
                score = (created_level, 1)
            else:
                child_level, child_merges = self._best_chain_score(next_board, target)
                score = (max(created_level, child_level), 1 + child_merges)
            if score > best_score:
                best_score = score
                best_pair = (source, target)
        return best_pair

    def auto_merge_once(
        self, focus: Optional[tuple[int, int]] = None
    ) -> MoveResult:
        pair = self.find_auto_merge(focus)
        if pair is None:
            return MoveResult("none")

        source, target = pair
        return self._merge_cells(source, target)

    def _merge_cells(
        self, source: tuple[int, int], target: tuple[int, int]
    ) -> MoveResult:
        sr, sc = source
        tr, tc = target
        piece = self.board[tr][tc]
        assert piece is not None
        new_level = piece.level + 1
        self.board[sr][sc] = None
        self.merges += 1
        self.score += piece.level * 10
        damage = MERGE_DAMAGE[piece.level]

        self.board[tr][tc] = Piece(piece.color, new_level)
        kind = "max_merge" if new_level == MAX_LEVEL else "merge"
        return MoveResult(
            kind,
            damage=damage,
            color=piece.color,
            source=source,
            target=target,
            source_level=piece.level,
        )

    def refill(self) -> list[RefillMove]:
        moves: list[RefillMove] = []
        for col in range(self.cols):
            existing = [
                (row, self.board[row][col])
                for row in range(self.rows)
                if self.board[row][col]
            ]
            empty_count = self.rows - len(existing)
            next_column: list[Piece] = []

            for target_row in range(empty_count):
                piece = self._new_piece()
                next_column.append(piece)
                moves.append(
                    RefillMove(
                        piece,
                        (target_row - empty_count, col),
                        (target_row, col),
                        True,
                    )
                )

            for index, (source_row, piece) in enumerate(existing):
                target_row = empty_count + index
                next_column.append(piece)
                if source_row != target_row:
                    moves.append(
                        RefillMove(piece, (source_row, col), (target_row, col))
                    )

            for row, piece in enumerate(next_column):
                self.board[row][col] = piece
        return moves

    def reset(self) -> None:
        self.__init__()
