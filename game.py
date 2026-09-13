from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
import sys
import time

import pygame

from game_logic import COLORS, LEVELS, MAX_LEVEL, GameState, Piece
from localization import DEFAULT_LANGUAGE, translate


WIDTH, HEIGHT = 540, 900
FPS = 60
MERGE_ANIMATION_DURATION = 0.26
FALL_ANIMATION_DURATION = 0.30
PROJECTILE_TRAVEL_DURATION = 0.42
PROJECTILE_IMPACT_DURATION = 0.55
BOARD_X, BOARD_Y = 25, 405
CELL = 70
BOARD_W, BOARD_H = CELL * 7, CELL * 6
ASSET_DIR = Path(__file__).resolve().parent / "assets"
FONT_DIR = ASSET_DIR / "fonts"
PIECE_SPRITE_SIZE = (68, 68)
MONSTER_SPRITE_SIZE = (126, 126)
BOSS_SPRITE_SIZE = (180, 180)
PROJECTILE_SPRITE_SIZE = (44, 44)
PROJECTILE_TRAIL_SIZE = (122, 28)
PROJECTILE_IMPACT_SIZE = (118, 118)
PROJECTILE_CROWN_SIZE = (106, 88)
MONSTER_DEFEAT_SPRITE_SIZE = (148, 148)
BOSS_DEFEAT_SPRITE_SIZE = (200, 200)
MONSTER_DEFEAT_FRAME_TIMES = (0.11, 0.23, 0.36, 0.53, 0.86)
BOSS_DEFEAT_FRAME_TIMES = (0.135, 0.285, 0.455, 0.685, 1.105)
DEFEAT_FINAL_HOLD = 0.45
LEVEL_CLEAR_GATHER_DURATION = 0.82
LEVEL_CLEAR_BURST_AT = 0.72
LEVEL_CLEAR_CARD_AT = 1.02
LEVEL_CLEAR_BUTTON_AT = 1.42

PALETTE = {
    "sky": (104, 204, 235),
    "sand": (255, 222, 202),
    "panel": (255, 239, 202),
    "line": (231, 126, 119),
    "ink": (83, 58, 65),
    "red": (238, 82, 77),
    "blue": (65, 148, 224),
    "green": (103, 183, 70),
    "white": (255, 252, 235),
    "shadow": (184, 126, 117),
    "cream": (255, 238, 199),
    "cream_dark": (226, 190, 143),
    "pink": (244, 128, 139),
    "pink_dark": (204, 83, 97),
    "aqua": (106, 198, 219),
    "gold": (250, 185, 55),
    "boss": (151, 92, 190),
}


@lru_cache(maxsize=None)
def font(size: int, bold: bool = False) -> pygame.font.Font:
    """Readable rounded UI type, bundled so every itch build looks identical."""
    path = FONT_DIR / "Nunito-Variable.ttf"
    result = pygame.font.Font(path if path.exists() else None, size)
    result.set_bold(bold)
    return result


@lru_cache(maxsize=None)
def display_font(size: int, bold: bool = True) -> pygame.font.Font:
    """Chunkier candy-like type for titles, counters, and impact text."""
    filename = "Fredoka-Bold.ttf" if bold else "Fredoka-SemiBold.ttf"
    path = FONT_DIR / filename
    if path.exists():
        return pygame.font.Font(path, size)
    return font(size, bold)


def rounded_rect(surface, color, rect, radius=16, width=0):
    pygame.draw.rect(surface, color, rect, width=width, border_radius=radius)


def mix_color(color, target, amount):
    return tuple(round(a + (b - a) * amount) for a, b in zip(color, target))


def glossy_rect(surface, fill, rect, radius=14, border=None):
    """用高光和柔和阴影模拟圆润软陶。"""
    rounded_rect(surface, fill, rect, radius)
    if border:
        rounded_rect(surface, border, rect, radius, 3)
    highlight = mix_color(fill, (255, 255, 255), 0.48)
    pygame.draw.arc(surface, highlight, rect.inflate(-8, -8), 0.7, 2.45, 2)


def star_points(center, outer, inner, points=5, rotation=-math.pi / 2):
    result = []
    for index in range(points * 2):
        angle = rotation + index * math.pi / points
        radius = outer if index % 2 == 0 else inner
        result.append(
            (
                round(center[0] + math.cos(angle) * radius),
                round(center[1] + math.sin(angle) * radius),
            )
        )
    return result


class Game:
    def __init__(self, language: str = DEFAULT_LANGUAGE):
        pygame.init()
        self.language = language
        pygame.display.set_caption(self.text("game_title"))
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.piece_sprites = self.load_piece_sprites()
        self.monster_sprites = self.load_monster_sprites()
        self.boss_sprite = self.load_sprite(
            ASSET_DIR / "monsters" / "boss.png",
            BOSS_SPRITE_SIZE,
        )
        self.monster_defeat_frames = {
            color: self.load_animation_frames(
                ASSET_DIR / "monsters" / "defeat" / f"{color}.png",
                MONSTER_DEFEAT_SPRITE_SIZE,
            )
            for color in COLORS
        }
        self.monster_defeat_frames["boss"] = self.load_animation_frames(
            ASSET_DIR / "monsters" / "defeat" / "boss.png",
            BOSS_DEFEAT_SPRITE_SIZE,
        )
        self.projectile_sprites = {
            color: self.load_sprite(
                ASSET_DIR / "effects" / "royal_star_comet" / f"projectile_{color}.png",
                PROJECTILE_SPRITE_SIZE,
            )
            for color in COLORS
        }
        self.projectile_trails = {
            color: self.load_sprite(
                ASSET_DIR / "effects" / "royal_star_comet" / f"trail_{color}.png",
                PROJECTILE_TRAIL_SIZE,
            )
            for color in COLORS
        }
        self.projectile_impact = self.load_sprite(
            ASSET_DIR / "effects" / "royal_star_comet" / "impact_starburst.png",
            PROJECTILE_IMPACT_SIZE,
        )
        self.projectile_impacts = {
            color: self.colorize_effect(self.projectile_impact, PALETTE[color])
            for color in COLORS
        }
        self.projectile_crown = self.load_sprite(
            ASSET_DIR / "effects" / "royal_star_comet" / "crown_flash.png",
            PROJECTILE_CROWN_SIZE,
        )
        self.projectile_particles = self.load_projectile_particles()
        self.state = GameState()
        self.selected = None
        self.drag_start = None
        self.drag_pos = None
        self.is_dragging = False
        self.mouse_down = None
        self.refill_at = 0.0
        self.auto_merge_at = 0.0
        self.auto_focus = None
        self.message = self.text("intro")
        self.message_until = 0.0
        self.merge_animation = None
        self.fall_animations = []
        self.projectile_animations = []
        self.active_chain_attack = None
        self.defeat_started_at = {}
        self.settle_at = 0.0
        self.restart_confirm_action = None
        self.restart_confirm_until = 0.0
        self.level_clear_started_at = 0.0
        self.level_clear_level = None
        self.running = True

    def text(self, key: str, **values) -> str:
        return translate(self.language, key, **values)

    @staticmethod
    def load_sprite(path: Path, size: tuple[int, int]):
        try:
            image = pygame.image.load(path).convert_alpha()
        except (FileNotFoundError, pygame.error):
            return None
        return pygame.transform.smoothscale(image, size)

    def load_piece_sprites(self):
        return {
            (color, level): self.load_sprite(
                ASSET_DIR / "pieces" / f"{color}_{level}.png",
                PIECE_SPRITE_SIZE,
            )
            for color in COLORS
            for level in range(1, MAX_LEVEL + 1)
        }

    def load_monster_sprites(self):
        return {
            color: self.load_sprite(
                ASSET_DIR / "monsters" / f"{color}.png",
                MONSTER_SPRITE_SIZE,
            )
            for color in COLORS
        }

    @staticmethod
    def load_animation_frames(path: Path, size: tuple[int, int]):
        try:
            sheet = pygame.image.load(path).convert_alpha()
        except (FileNotFoundError, pygame.error):
            return []
        cell_width = sheet.get_width() // 3
        cell_height = sheet.get_height() // 2
        frames = []
        main_bounds = []
        for row in range(2):
            for col in range(3):
                frame = sheet.subsurface(
                    (
                        col * cell_width,
                        row * cell_height,
                        cell_width,
                        cell_height,
                    )
                ).copy()
                mask = pygame.mask.from_surface(frame, 8)
                components = mask.connected_components(8)
                if components:
                    main_component = max(components, key=lambda item: item.count())
                    main_rect = main_component.get_bounding_rects()[0]
                    kept = pygame.mask.Mask(frame.get_size())
                    for component in components:
                        rect = component.get_bounding_rects()[0]
                        touches_edge = (
                            rect.left <= 10
                            or rect.top <= 10
                            or rect.right >= cell_width - 10
                            or rect.bottom >= cell_height - 10
                        )
                        if component is main_component or not touches_edge:
                            kept.draw(component, (0, 0))
                    alpha_mask = kept.to_surface(
                        setcolor=(255, 255, 255, 255),
                        unsetcolor=(255, 255, 255, 0),
                    )
                    frame.blit(alpha_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                else:
                    main_rect = frame.get_rect()
                frames.append(frame)
                main_bounds.append(main_rect)

        # 最后两帧使用相同的身体锚点，避免眩晕星星出现时角色突然横移。
        fifth = main_bounds[4]
        sixth = main_bounds[5]
        shift_x = round(fifth.centerx - sixth.centerx)
        shift_y = fifth.bottom - sixth.bottom
        aligned_final = pygame.Surface(frames[5].get_size(), pygame.SRCALPHA)
        aligned_final.blit(frames[5], (shift_x, shift_y))
        frames[5] = aligned_final

        return [pygame.transform.smoothscale(frame, size) for frame in frames]

    def load_projectile_particles(self):
        path = ASSET_DIR / "effects" / "royal_star_comet" / "particles_atlas.png"
        try:
            atlas = pygame.image.load(path).convert_alpha()
        except (FileNotFoundError, pygame.error):
            return []

        particles = []
        width, height = atlas.get_size()
        target_sizes = (14, 10, 11)
        for row in range(3):
            row_particles = []
            for col in range(4):
                left = round(col * width / 4)
                right = round((col + 1) * width / 4)
                top = round(row * height / 3)
                bottom = round((row + 1) * height / 3)
                tile = atlas.subsurface((left, top, right - left, bottom - top)).copy()
                bounds = tile.get_bounding_rect(min_alpha=8)
                if bounds.width and bounds.height:
                    tile = tile.subsurface(bounds).copy()
                    size = target_sizes[row]
                    scale = min(size / tile.get_width(), size / tile.get_height())
                    tile = pygame.transform.smoothscale(
                        tile,
                        (
                            max(1, round(tile.get_width() * scale)),
                            max(1, round(tile.get_height() * scale)),
                        ),
                    )
                row_particles.append(tile)
            particles.append(row_particles)
        return particles

    def cell_at(self, pos):
        x, y = pos
        if not (BOARD_X <= x < BOARD_X + BOARD_W and BOARD_Y <= y < BOARD_Y + BOARD_H):
            return None
        return ((y - BOARD_Y) // CELL, (x - BOARD_X) // CELL)

    def handle_cell_action(self, source, target):
        result = self.state.move(source, target)
        if result.kind == "invalid":
            return
        if result.kind == "no_moves":
            self.show_message(self.text("no_moves"), 1.5)
            return
        if result.kind == "game_over":
            return
        if result.kind in ("merge", "max_merge", "attack"):
            self.handle_merge_result(result, animate=False, new_chain=True)
            self.auto_focus = result.target
            self.auto_merge_at = time.monotonic() + 0.10
        else:
            self.show_message(self.text("different_piece"), 1.2)

    def handle_merge_result(self, result, animate=True, new_chain=False):
        if result.kind == "merge":
            self.show_message(self.text("merge_success", damage=result.damage))
            self.record_chain_attack(result, new_chain)
            if animate:
                self.start_merge_animation(result)
        elif result.kind == "max_merge":
            self.show_message(self.text("max_merge", damage=result.damage))
            self.record_chain_attack(result, new_chain)
            if animate:
                self.start_merge_animation(result)
        elif result.kind == "attack":
            self.show_message(self.text("level_six_ready", damage=result.damage))
            self.start_projectile(
                result.target, result.color, result.damage, royal=True
            )

    def show_attack_resolution(self, result):
        if result.wave_cleared:
            if self.state.is_boss_wave:
                self.show_message(self.text("boss_defeated"))
            else:
                self.show_message(self.text("wave_defeated"))
        elif result.monster_defeated:
            self.show_message(self.text("monster_defeated"))
        else:
            self.show_message(self.text("damage_dealt", damage=result.damage))

    def record_chain_attack(self, result, new_chain=False):
        if (
            self.active_chain_attack
            and (new_chain or self.active_chain_attack["color"] != result.color)
        ):
            self.launch_active_chain_attack()
        if self.active_chain_attack is None:
            self.active_chain_attack = {
                "color": result.color,
                "damage": 0,
                "source": result.target,
            }
        self.active_chain_attack["damage"] += result.damage
        self.active_chain_attack["source"] = result.target

    def start_projectile(self, source, color, damage, delay=0.0, royal=False):
        if source is None:
            return
        self.projectile_animations.append(
            {
                "source": source,
                "color": color,
                "damage": damage,
                "born": time.monotonic(),
                "delay": delay,
                "applied": False,
                "royal": royal,
            }
        )

    def launch_active_chain_attack(self):
        if not self.active_chain_attack:
            return 0.0
        attack = self.active_chain_attack
        self.start_projectile(
            attack["source"], attack["color"], attack["damage"]
        )
        self.active_chain_attack = None
        return PROJECTILE_TRAVEL_DURATION

    def start_merge_animation(self, result):
        if result.source is None or result.target is None:
            return
        self.merge_animation = {
            "source": result.source,
            "target": result.target,
            "piece": Piece(result.color, result.source_level),
            "born": time.monotonic(),
        }

    def show_message(self, text, seconds=1.8):
        self.message = text
        self.message_until = time.monotonic() + seconds

    def board_busy(self):
        return bool(
            self.merge_animation
            or self.fall_animations
            or self.auto_merge_at
            or self.refill_at
            or self.settle_at
            or self.level_clear_started_at
        )

    def clear_runtime_state(self):
        """清除不属于规则存档的输入与动画状态。"""
        self.selected = None
        self.drag_start = None
        self.drag_pos = None
        self.is_dragging = False
        self.mouse_down = None
        self.refill_at = 0.0
        self.auto_merge_at = 0.0
        self.auto_focus = None
        self.merge_animation = None
        self.fall_animations = []
        self.projectile_animations = []
        self.active_chain_attack = None
        self.defeat_started_at = {}
        self.settle_at = 0.0
        self.restart_confirm_action = None
        self.restart_confirm_until = 0.0
        self.level_clear_started_at = 0.0
        self.level_clear_level = None

    def restart_current_level(self):
        self.state.restart_level()
        self.clear_runtime_state()
        self.show_message(self.text("level_restarted", level=self.state.level), 2.0)

    def restart_game(self):
        self.state.reset()
        self.clear_runtime_state()
        self.show_message(self.text("new_game"))

    def request_restart(self, action):
        """游戏进行中要求按两次重启快捷键，避免误触丢失进度。"""
        now = time.monotonic()
        if self.restart_confirm_action == action and now < self.restart_confirm_until:
            if action == "full":
                self.restart_game()
            else:
                self.restart_current_level()
            return
        self.restart_confirm_action = action
        self.restart_confirm_until = now + 2.0
        key = "confirm_new_game" if action == "full" else "confirm_retry_level"
        self.show_message(self.text(key), 2.0)

    def end_screen_buttons(self):
        if self.state.game_won:
            return {"full": pygame.Rect(120, 492, 300, 50)}
        return {
            "level": pygame.Rect(120, 462, 300, 50),
            "full": pygame.Rect(120, 524, 300, 44),
        }

    def handle_end_screen_click(self, pos):
        for action, rect in self.end_screen_buttons().items():
            if rect.collidepoint(pos):
                if action == "level":
                    self.restart_current_level()
                else:
                    self.restart_game()
                return True
        return False

    @staticmethod
    def level_clear_button_rect():
        return pygame.Rect(120, 490, 300, 58)

    def start_level_clear_celebration(self):
        if self.level_clear_started_at:
            return
        self.level_clear_level = self.state.level
        self.level_clear_started_at = time.monotonic()
        self.settle_at = 0.0

    def continue_from_level_clear(self):
        if not self.level_clear_started_at:
            return
        transition = self.state.advance_wave()
        self.clear_runtime_state()
        if transition == "level":
            self.show_message(
                self.text("level_incoming", level=self.state.level), 2.2
            )

    def events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif self.level_clear_started_at:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif (
                        event.key in (pygame.K_SPACE, pygame.K_RETURN)
                        and time.monotonic() - self.level_clear_started_at
                        >= LEVEL_CLEAR_BUTTON_AT
                    ):
                        self.continue_from_level_clear()
                elif (
                    event.type == pygame.MOUSEBUTTONDOWN
                    and event.button == 1
                    and time.monotonic() - self.level_clear_started_at
                    >= LEVEL_CLEAR_BUTTON_AT
                    and self.level_clear_button_rect().collidepoint(event.pos)
                ):
                    self.continue_from_level_clear()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_r:
                    full_restart = bool(event.mod & pygame.KMOD_SHIFT)
                    if self.state.game_won:
                        self.restart_game()
                    elif self.state.game_over:
                        if full_restart:
                            self.restart_game()
                        else:
                            self.restart_current_level()
                    else:
                        self.request_restart("full" if full_restart else "level")
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.state.game_over or self.state.game_won:
                    self.handle_end_screen_click(event.pos)
                    continue
                if self.board_busy():
                    self.show_message(self.text("settling"), 0.8)
                    continue
                cell = self.cell_at(event.pos)
                self.mouse_down = event.pos
                self.drag_start = cell
                self.drag_pos = event.pos
                self.is_dragging = False
                self.selected = cell
            elif event.type == pygame.MOUSEMOTION and self.mouse_down:
                self.drag_pos = event.pos
                self.is_dragging = math.dist(self.mouse_down, event.pos) > 10
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                target = self.cell_at(event.pos)
                if self.drag_start is not None and self.is_dragging:
                    if target is not None:
                        self.handle_cell_action(self.drag_start, target)
                    else:
                        self.show_message(self.text("returned"), 1.0)
                elif self.drag_start is not None:
                    result = self.state.activate(self.drag_start)
                    if result.kind == "attack":
                        self.handle_merge_result(result)
                        self.refill_at = (
                            time.monotonic()
                            + PROJECTILE_TRAVEL_DURATION
                            + 0.04
                        )
                    elif result.kind == "clear":
                        self.show_message(self.text("monster_already_defeated"), 1.5)
                        self.refill_at = time.monotonic() + 0.08
                self.selected = None
                self.drag_start = None
                self.drag_pos = None
                self.is_dragging = False
                self.mouse_down = None

    def update(self):
        now = time.monotonic()
        if self.merge_animation and now - self.merge_animation["born"] >= MERGE_ANIMATION_DURATION:
            self.merge_animation = None
        self.fall_animations = [
            item
            for item in self.fall_animations
            if now - item["born"] < item["delay"] + FALL_ANIMATION_DURATION
        ]
        for item in self.projectile_animations:
            hit_at = item["delay"] + PROJECTILE_TRAVEL_DURATION
            if not item["applied"] and now - item["born"] >= hit_at:
                item["applied"] = True
                resolution = self.state.resolve_attack(
                    item["color"], item["damage"], item["source"]
                )
                if resolution.monster_defeated:
                    defeat_key = "boss" if self.state.is_boss_wave else item["color"]
                    self.defeat_started_at[defeat_key] = now
                self.show_attack_resolution(resolution)
        self.projectile_animations = [
            item
            for item in self.projectile_animations
            if now - item["born"]
            < item["delay"] + PROJECTILE_TRAVEL_DURATION + PROJECTILE_IMPACT_DURATION
        ]
        if self.settle_at and now >= self.settle_at:
            self.settle_at = 0.0
            self.settle_board()
        if self.auto_merge_at and now >= self.auto_merge_at:
            previous_focus = self.auto_focus
            result = self.state.auto_merge_once(self.auto_focus)
            self.auto_merge_at = 0.0
            if result.kind != "none":
                continues_chain = (
                    previous_focus is not None
                    and previous_focus in (result.source, result.target)
                )
                self.handle_merge_result(result, new_chain=not continues_chain)
                self.auto_focus = result.target
                self.auto_merge_at = now + MERGE_ANIMATION_DURATION + 0.04
            else:
                projectile_wait = self.launch_active_chain_attack()
                if any(piece is None for row in self.state.board for piece in row):
                    self.refill_at = now + max(0.07, projectile_wait + 0.04)
                elif projectile_wait:
                    self.settle_at = now + projectile_wait + 0.04
                else:
                    self.settle_board()
        if self.refill_at and now >= self.refill_at:
            moves = self.state.refill()
            self.refill_at = 0.0
            self.start_fall_animations(moves, now)
            new_moves = [move for move in moves if move.is_new]
            self.auto_focus = new_moves[-1].target if new_moves else None
            max_delay = max((item["delay"] for item in self.fall_animations), default=0.0)
            self.auto_merge_at = now + max_delay + FALL_ANIMATION_DURATION + 0.035

    def settle_board(self):
        now = time.monotonic()
        transition_ready_at = self.defeat_transition_ready_at()
        if transition_ready_at > now:
            self.settle_at = transition_ready_at
            return
        finishing_level = (
            self.state.wave_cleared
            and self.state.wave_index + 1 >= self.state.total_waves
        )
        if finishing_level and self.state.level < len(LEVELS):
            self.start_level_clear_celebration()
            return
        transition = self.state.advance_wave()
        if transition is not None:
            self.defeat_started_at = {}
        if transition == "wave":
            if self.state.is_boss_wave:
                self.show_message(self.text("boss_incoming"), 2.2)
            else:
                self.show_message(self.text("wave_incoming", wave=self.state.wave_number))
        elif transition == "level":
            self.show_message(
                self.text("level_incoming", level=self.state.level), 2.2
            )
        elif transition == "won":
            self.show_message(self.text("all_levels_cleared"), 3.0)
        else:
            self.state.check_failure()

    def start_fall_animations(self, moves, now):
        self.fall_animations = []
        new_count_by_col = {}
        for move in moves:
            if move.is_new:
                new_count_by_col[move.target[1]] = new_count_by_col.get(move.target[1], 0) + 1
        for move in moves:
            target_row, target_col = move.target
            delay = target_col * 0.005
            if move.is_new:
                last_new_row = new_count_by_col[target_col] - 1
                delay += (last_new_row - target_row) * 0.028
            self.fall_animations.append(
                {
                    "piece": move.piece,
                    "source": move.source,
                    "target": move.target,
                    "born": now,
                    "delay": delay,
                }
            )
    def draw_background(self):
        # 蓝天渐变与粉色棋盘地面。
        for y in range(0, 190, 10):
            amount = y / 260
            pygame.draw.rect(
                self.screen,
                mix_color(PALETTE["sky"], PALETTE["white"], amount),
                (0, y, WIDTH, 10),
            )
        pygame.draw.rect(self.screen, PALETTE["sand"], (0, 190, WIDTH, HEIGHT - 190))
        tile = 45
        for row, y in enumerate(range(190, 390, tile)):
            for col, x in enumerate(range(0, WIDTH, tile)):
                color = (255, 229, 207) if (row + col) % 2 == 0 else (250, 207, 198)
                pygame.draw.rect(self.screen, color, (x, y, tile, tile))

        # 奶油云和两侧软陶积木城堡。
        for cloud_x, cloud_y, scale in ((44, 76, 1.0), (492, 68, 1.12)):
            cloud = (255, 243, 220)
            pygame.draw.ellipse(
                self.screen, (219, 174, 153),
                (cloud_x - 44 * scale, cloud_y + 10, 88 * scale, 18),
            )
            for dx, dy, radius in ((-30, 7, 22), (-7, -3, 30), (22, 5, 24)):
                pygame.draw.circle(
                    self.screen,
                    cloud,
                    (round(cloud_x + dx * scale), round(cloud_y + dy * scale)),
                    round(radius * scale),
                )
        block_colors = ((242, 133, 137), (112, 183, 217), (250, 191, 83), (166, 122, 201))
        for side in (-1, 1):
            base_x = 3 if side < 0 else WIDTH - 61
            for index, (w, h) in enumerate(((58, 34), (46, 38), (34, 32))):
                rect = pygame.Rect(base_x + index * 6, 310 - index * 34, w, h)
                color = block_colors[(index + (1 if side > 0 else 0)) % len(block_colors)]
                pygame.draw.rect(self.screen, mix_color(color, PALETTE["shadow"], 0.28), rect.move(0, 4), border_radius=8)
                glossy_rect(self.screen, color, rect, 8)
            roof_x = base_x + 17
            pygame.draw.polygon(
                self.screen,
                block_colors[2],
                [(roof_x, 239), (roof_x + 18, 218), (roof_x + 36, 239)],
            )

        # 糖霜招牌使用多层软边和糖针装饰。
        title_shadow = pygame.Rect(78, 18, 384, 70)
        rounded_rect(self.screen, PALETTE["pink_dark"], title_shadow.move(0, 5), 31)
        glossy_rect(self.screen, PALETTE["pink"], title_shadow, 31)
        title_patch = title_shadow.inflate(-10, -10)
        glossy_rect(self.screen, PALETTE["white"], title_patch, 27, (255, 211, 180))
        sprinkle_colors = (PALETTE["red"], PALETTE["blue"], PALETTE["green"], PALETTE["gold"])
        for index, (sx, sy) in enumerate(((106, 31), (142, 70), (395, 31), (430, 67), (269, 27))):
            pygame.draw.line(
                self.screen,
                sprinkle_colors[index % len(sprinkle_colors)],
                (sx - 3, sy - 1),
                (sx + 3, sy + 1),
                3,
            )
        title = display_font(29).render(
            self.text("game_title"), True, PALETTE["pink_dark"]
        )
        self.screen.blit(title, title.get_rect(center=title_patch.center))

    def defeat_frame(self, key):
        frames = self.monster_defeat_frames.get(key, [])
        if len(frames) != 6:
            return None
        started_at = self.defeat_started_at.get(key)
        if started_at is None:
            return frames[-1]
        elapsed = max(0.0, time.monotonic() - started_at)
        frame_times = (
            BOSS_DEFEAT_FRAME_TIMES
            if key == "boss"
            else MONSTER_DEFEAT_FRAME_TIMES
        )
        frame_index = sum(elapsed >= frame_time for frame_time in frame_times)
        return frames[min(frame_index, len(frames) - 1)]

    def defeat_transition_ready_at(self):
        if not self.state.wave_cleared or not self.defeat_started_at:
            return 0.0
        key, started_at = max(
            self.defeat_started_at.items(), key=lambda item: item[1]
        )
        frame_times = (
            BOSS_DEFEAT_FRAME_TIMES
            if key == "boss"
            else MONSTER_DEFEAT_FRAME_TIMES
        )
        return started_at + frame_times[-1] + DEFEAT_FINAL_HOLD

    def _draw_monster_procedural(self, color, center, monster):
        x, y = center
        body = PALETTE[color]
        dark = mix_color(body, PALETTE["ink"], 0.32)
        light = mix_color(body, PALETTE["white"], 0.45)
        pygame.draw.ellipse(self.screen, (213, 157, 143), (x - 47, y + 34, 94, 15))

        # 圆润软陶怪物：厚描边、角、突起和局部高光。
        pygame.draw.polygon(
            self.screen, dark, [(x - 29, y - 29), (x - 20, y - 51), (x - 9, y - 29)]
        )
        pygame.draw.polygon(
            self.screen, PALETTE["cream"],
            [(x - 26, y - 30), (x - 20, y - 47), (x - 13, y - 29)],
        )
        pygame.draw.polygon(
            self.screen, dark, [(x + 29, y - 29), (x + 20, y - 51), (x + 9, y - 29)]
        )
        pygame.draw.polygon(
            self.screen, PALETTE["cream"],
            [(x + 26, y - 30), (x + 20, y - 47), (x + 13, y - 29)],
        )
        pygame.draw.ellipse(self.screen, dark, (x - 51, y - 5, 28, 43))
        pygame.draw.ellipse(self.screen, body, (x - 47, y - 3, 22, 37))
        pygame.draw.ellipse(self.screen, dark, (x + 23, y - 5, 28, 43))
        pygame.draw.ellipse(self.screen, body, (x + 25, y - 3, 22, 37))
        pygame.draw.ellipse(self.screen, dark, (x - 40, y - 39, 80, 83))
        pygame.draw.ellipse(self.screen, body, (x - 36, y - 36, 72, 76))
        pygame.draw.ellipse(self.screen, light, (x - 25, y - 27, 37, 17))

        for spot_x, spot_y, radius in ((-26, 10, 4), (24, 17, 5), (-19, 25, 3), (28, -18, 3)):
            pygame.draw.circle(self.screen, dark, (x + spot_x, y + spot_y), radius)
            pygame.draw.circle(
                self.screen, mix_color(body, PALETTE["white"], 0.18),
                (x + spot_x - 1, y + spot_y - 1), max(1, radius - 2)
            )

        for dx in (-13, 13):
            pygame.draw.ellipse(self.screen, PALETTE["cream"], (x + dx - 9, y - 17, 18, 21))
            pygame.draw.circle(self.screen, PALETTE["ink"], (x + dx, y - 7), 6)
            pygame.draw.circle(self.screen, PALETTE["white"], (x + dx - 2, y - 10), 2)
        pygame.draw.line(self.screen, PALETTE["ink"], (x - 24, y - 22), (x - 7, y - 17), 4)
        pygame.draw.line(self.screen, PALETTE["ink"], (x + 24, y - 22), (x + 7, y - 17), 4)
        mouth = pygame.Rect(x - 13, y + 5, 26, 17)
        pygame.draw.arc(self.screen, PALETTE["ink"], mouth, math.pi, math.tau, 3)
        pygame.draw.polygon(
            self.screen, PALETTE["white"],
            [(x - 7, y + 9), (x - 2, y + 9), (x - 4, y + 15)],
        )
        pygame.draw.polygon(
            self.screen, PALETTE["white"],
            [(x + 7, y + 9), (x + 2, y + 9), (x + 4, y + 15)],
        )

        badge_rect = pygame.Rect(x - 27, y + 47, 54, 20)
        glossy_rect(self.screen, PALETTE["cream"], badge_rect, 9, PALETTE["pink_dark"])
        badge = font(14, True).render(f"Lv.{monster.stage}", True, PALETTE["ink"])
        self.screen.blit(badge, badge.get_rect(center=badge_rect.center))
        bar = pygame.Rect(x - 58, y + 76, 116, 18)
        rounded_rect(self.screen, PALETTE["ink"], bar, 8)
        inner_bar = bar.inflate(-6, -6)
        rounded_rect(self.screen, PALETTE["cream"], inner_bar, 6)
        fill = inner_bar.copy()
        fill.width = max(0, int(inner_bar.width * monster.hp / monster.max_hp))
        rounded_rect(self.screen, body, fill, 6)
        if fill.width > 8:
            pygame.draw.line(
                self.screen, light, (fill.left + 4, fill.top + 2),
                (fill.right - 4, fill.top + 2), 2
            )
        hp = font(12, True).render(f"{monster.hp}/{monster.max_hp}", True, PALETTE["ink"])
        self.screen.blit(hp, hp.get_rect(center=bar.center))

    def draw_monster(self, color, center, monster):
        sprite = self.monster_sprites.get(color)
        defeat_sprite = self.defeat_frame(color) if monster.hp <= 0 else None
        if sprite is None and defeat_sprite is None:
            self._draw_monster_procedural(color, center, monster)
            return

        x, y = center
        body = PALETTE[color]
        light = mix_color(body, PALETTE["white"], 0.45)
        if defeat_sprite is not None:
            defeat_rect = defeat_sprite.get_rect(center=(x, y - 11))
            self.screen.blit(defeat_sprite, defeat_rect)
        else:
            sprite_rect = sprite.get_rect(center=(x, y - 8))
            self.screen.blit(sprite, sprite_rect)

        badge_rect = pygame.Rect(x - 27, y + 49, 54, 20)
        glossy_rect(
            self.screen, PALETTE["cream"], badge_rect, 9, PALETTE["pink_dark"]
        )
        badge = font(14, True).render(f"Lv.{monster.stage}", True, PALETTE["ink"])
        self.screen.blit(badge, badge.get_rect(center=badge_rect.center))

        bar = pygame.Rect(x - 58, y + 76, 116, 18)
        rounded_rect(self.screen, PALETTE["ink"], bar, 8)
        inner_bar = bar.inflate(-6, -6)
        rounded_rect(self.screen, PALETTE["cream"], inner_bar, 6)
        fill = inner_bar.copy()
        fill.width = max(0, int(inner_bar.width * monster.hp / monster.max_hp))
        rounded_rect(self.screen, body, fill, 6)
        if fill.width > 8:
            pygame.draw.line(
                self.screen,
                light,
                (fill.left + 4, fill.top + 2),
                (fill.right - 4, fill.top + 2),
                2,
            )
        hp = font(12, True).render(
            f"{monster.hp}/{monster.max_hp}", True, PALETTE["ink"]
        )
        self.screen.blit(hp, hp.get_rect(center=bar.center))

    def draw_boss(self, center, boss):
        """绘制不受颜色限制的糖果巨兽和加宽血条。"""
        x, y = center
        body = PALETTE["boss"]
        dark = mix_color(body, PALETTE["ink"], 0.35)
        light = mix_color(body, PALETTE["white"], 0.48)
        defeat_sprite = self.defeat_frame("boss") if boss.hp <= 0 else None

        if defeat_sprite is not None:
            defeat_rect = defeat_sprite.get_rect(center=(x, y - 24))
            self.screen.blit(defeat_sprite, defeat_rect)
        elif self.boss_sprite is not None:
            sprite_rect = self.boss_sprite.get_rect(center=(x, y - 16))
            self.screen.blit(self.boss_sprite, sprite_rect)
        else:
            pygame.draw.ellipse(
                self.screen, (207, 150, 139), (x - 82, y + 44, 164, 18)
            )
            for dx in (-58, 58):
                pygame.draw.circle(self.screen, dark, (x + dx, y + 7), 30)
                pygame.draw.circle(self.screen, body, (x + dx, y + 4), 24)
            pygame.draw.polygon(
                self.screen,
                PALETTE["cream"],
                [(x - 57, y - 35), (x - 40, y - 70), (x - 22, y - 39)],
            )
            pygame.draw.polygon(
                self.screen,
                PALETTE["cream"],
                [(x + 57, y - 35), (x + 40, y - 70), (x + 22, y - 39)],
            )
            pygame.draw.ellipse(self.screen, dark, (x - 72, y - 52, 144, 118))
            pygame.draw.ellipse(self.screen, body, (x - 66, y - 48, 132, 108))
            pygame.draw.ellipse(self.screen, light, (x - 45, y - 36, 67, 28))

            for dx in (-24, 24):
                pygame.draw.ellipse(
                    self.screen, PALETTE["cream"], (x + dx - 13, y - 20, 26, 30)
                )
                pygame.draw.circle(self.screen, PALETTE["ink"], (x + dx, y - 4), 8)
                pygame.draw.circle(
                    self.screen, PALETTE["white"], (x + dx - 3, y - 8), 3
                )
            pygame.draw.arc(
                self.screen,
                PALETTE["ink"],
                (x - 25, y + 10, 50, 32),
                math.pi,
                math.tau,
                5,
            )

            crown = [
                (x - 38, y - 52),
                (x - 31, y - 82),
                (x - 12, y - 66),
                (x, y - 91),
                (x + 13, y - 66),
                (x + 33, y - 82),
                (x + 39, y - 52),
            ]
            pygame.draw.polygon(self.screen, PALETTE["gold"], crown)
            pygame.draw.polygon(self.screen, PALETTE["ink"], crown, 3)

        label = display_font(18).render("BOSS", True, PALETTE["ink"])
        self.screen.blit(label, label.get_rect(center=(x, y + 74)))
        bar = pygame.Rect(x - 155, y + 91, 310, 22)
        rounded_rect(self.screen, PALETTE["ink"], bar, 10)
        inner = bar.inflate(-6, -6)
        rounded_rect(self.screen, PALETTE["cream"], inner, 7)
        fill = inner.copy()
        fill.width = max(0, int(inner.width * boss.hp / boss.max_hp))
        rounded_rect(self.screen, body, fill, 7)
        hp = font(14, True).render(f"{boss.hp}/{boss.max_hp}", True, PALETTE["ink"])
        self.screen.blit(hp, hp.get_rect(center=bar.center))

    def _draw_piece_procedural(self, piece: Piece, rect, selected=False):
        if selected:
            rounded_rect(self.screen, PALETTE["gold"], rect.inflate(-3, -3), 15, 4)
        center = rect.center
        color = PALETTE[piece.color]
        dark = mix_color(color, PALETTE["ink"], 0.28)
        light = mix_color(color, PALETTE["white"], 0.48)
        if piece.level == 1:
            # 果冻软糖。
            pygame.draw.ellipse(self.screen, (211, 166, 137), (center[0] - 20, center[1] + 14, 40, 10))
            pygame.draw.polygon(
                self.screen,
                dark,
                [
                    (center[0] - 19, center[1] + 15),
                    (center[0] - 15, center[1] - 11),
                    (center[0] - 10, center[1] - 18),
                    (center[0] + 10, center[1] - 18),
                    (center[0] + 15, center[1] - 11),
                    (center[0] + 19, center[1] + 15),
                ],
            )
            pygame.draw.polygon(
                self.screen,
                color,
                [
                    (center[0] - 15, center[1] + 12),
                    (center[0] - 12, center[1] - 9),
                    (center[0] - 7, center[1] - 14),
                    (center[0] + 8, center[1] - 14),
                    (center[0] + 12, center[1] - 8),
                    (center[0] + 15, center[1] + 12),
                ],
            )
            pygame.draw.arc(
                self.screen, light, (center[0] - 9, center[1] - 12, 15, 22), 1.4, 3.7, 3
            )
        elif piece.level == 2:
            # 一簇圆润糖珠。
            for dx, dy in ((-12, 8), (0, 10), (12, 8), (-8, -4), (8, -4), (0, -12)):
                pygame.draw.circle(self.screen, dark, (center[0] + dx, center[1] + dy), 11)
                pygame.draw.circle(self.screen, color, (center[0] + dx, center[1] + dy - 1), 9)
                pygame.draw.circle(self.screen, light, (center[0] + dx - 3, center[1] + dy - 4), 2)
        elif piece.level == 3:
            # 奶油条纹提篮。
            pygame.draw.arc(
                self.screen, dark, rect.inflate(-22, -13), 0, math.pi, 8
            )
            pygame.draw.arc(
                self.screen, PALETTE["cream"], rect.inflate(-22, -13), 0, math.pi, 4
            )
            pygame.draw.rect(
                self.screen, dark,
                (center[0] - 25, center[1] - 2, 50, 25),
                border_radius=7,
            )
            pygame.draw.rect(
                self.screen, color,
                (center[0] - 22, center[1] + 1, 44, 19),
                border_radius=7,
            )
            for dx in (-12, 0, 12):
                pygame.draw.circle(self.screen, dark, (center[0] + dx, center[1] - 7), 12)
                pygame.draw.circle(self.screen, color, (center[0] + dx, center[1] - 7), 9)
                pygame.draw.circle(self.screen, light, (center[0] + dx - 3, center[1] - 10), 2)
            for stripe_x in range(center[0] - 17, center[0] + 19, 12):
                pygame.draw.line(
                    self.screen, PALETTE["cream"],
                    (stripe_x, center[1] + 3), (stripe_x + 7, center[1] + 18), 4
                )
        elif piece.level == 4:
            pygame.draw.line(
                self.screen,
                (166, 104, 69),
                (center[0] - 13, center[1] + 25),
                (center[0] + 8, center[1] - 13),
                7,
            )
            pygame.draw.circle(self.screen, dark, (center[0] + 9, center[1] - 13), 23)
            pygame.draw.circle(
                self.screen, PALETTE["white"], (center[0] + 9, center[1] - 13), 19
            )
            for radius in (16, 11, 6):
                swirl_color = color if radius % 2 == 0 else PALETTE["white"]
                pygame.draw.arc(
                    self.screen,
                    swirl_color,
                    (
                        center[0] + 9 - radius,
                        center[1] - 13 - radius,
                        radius * 2,
                        radius * 2,
                    ),
                    0.15,
                    5.7,
                    4,
                )
            pygame.draw.polygon(
                self.screen,
                color,
                [
                    (center[0] - 17, center[1] + 13),
                    (center[0] - 28, center[1] + 7),
                    (center[0] - 25, center[1] + 23),
                ],
            )
            pygame.draw.circle(self.screen, light, (center[0] + 2, center[1] - 21), 4)
        else:
            # 最高级皇冠星糖。
            outer = star_points(center, 29, 14)
            pygame.draw.polygon(self.screen, PALETTE["gold"], outer)
            pygame.draw.polygon(self.screen, PALETTE["ink"], outer, 3)
            pygame.draw.polygon(self.screen, color, star_points(center, 22, 10))
            pygame.draw.polygon(
                self.screen,
                light,
                star_points((center[0] - 3, center[1] - 3), 10, 4),
            )
            crown = [
                (center[0] - 13, center[1] - 25),
                (center[0] - 10, center[1] - 35),
                (center[0] - 3, center[1] - 29),
                (center[0] + 3, center[1] - 37),
                (center[0] + 10, center[1] - 28),
                (center[0] + 14, center[1] - 35),
                (center[0] + 16, center[1] - 24),
            ]
            pygame.draw.polygon(self.screen, PALETTE["gold"], crown)
            pygame.draw.line(
                self.screen, mix_color(PALETTE["gold"], PALETTE["ink"], 0.25),
                crown[0], crown[-1], 2
            )
        level = font(13, True).render(str(piece.level), True, PALETTE["white"])
        badge = pygame.Rect(rect.right - 23, rect.top + 5, 18, 18)
        pygame.draw.circle(self.screen, PALETTE["ink"], badge.center, 10)
        pygame.draw.circle(self.screen, PALETTE["gold"], badge.center, 10, 2)
        self.screen.blit(level, level.get_rect(center=badge.center))

    def draw_piece(self, piece: Piece, rect, selected=False):
        sprite = self.piece_sprites.get((piece.color, piece.level))
        if sprite is None:
            self._draw_piece_procedural(piece, rect, selected)
            return

        if selected:
            rounded_rect(self.screen, PALETTE["gold"], rect.inflate(-3, -3), 15, 4)
        self.screen.blit(sprite, sprite.get_rect(center=rect.center))

        level = font(13, True).render(str(piece.level), True, PALETTE["white"])
        badge = pygame.Rect(rect.right - 23, rect.top + 5, 18, 18)
        pygame.draw.circle(self.screen, PALETTE["ink"], badge.center, 10)
        pygame.draw.circle(self.screen, PALETTE["gold"], badge.center, 10, 2)
        self.screen.blit(level, level.get_rect(center=badge.center))

    def draw_board(self):
        panel = pygame.Rect(14, 390, WIDTH - 28, BOARD_H + 30)
        rounded_rect(self.screen, PALETTE["shadow"], panel.move(0, 7), 24)
        rounded_rect(self.screen, PALETTE["aqua"], panel.move(0, 4), 24)
        rounded_rect(self.screen, PALETTE["cream_dark"], panel, 24)
        glossy_rect(self.screen, PALETTE["cream"], panel.inflate(-4, -4), 21)
        sprinkle_colors = (
            PALETTE["red"], PALETTE["blue"], PALETTE["green"], PALETTE["gold"]
        )
        for index, (sx, sy, angle) in enumerate(
            ((31, 398, 0), (76, 397, 1), (128, 399, 0), (405, 397, 1),
             (455, 399, 0), (503, 398, 1), (28, 810, 1), (511, 812, 0))
        ):
            color = sprinkle_colors[index % len(sprinkle_colors)]
            if angle:
                pygame.draw.line(self.screen, color, (sx, sy - 3), (sx + 2, sy + 3), 3)
            else:
                pygame.draw.line(self.screen, color, (sx - 3, sy), (sx + 3, sy), 3)
        for row in range(self.state.rows):
            for col in range(self.state.cols):
                rect = pygame.Rect(BOARD_X + col * CELL, BOARD_Y + row * CELL, CELL, CELL)
                cell_rect = rect.inflate(-5, -5)
                cell_fill = (255, 244, 218) if (row + col) % 2 == 0 else (252, 235, 205)
                pygame.draw.rect(
                    self.screen, (217, 177, 137), cell_rect.move(0, 3), border_radius=11
                )
                glossy_rect(self.screen, cell_fill, cell_rect, 11, (232, 199, 158))
                piece = self.state.board[row][col]
                hidden_by_drag = self.is_dragging and self.drag_start == (row, col)
                hidden_by_merge = (
                    self.merge_animation
                    and self.merge_animation["target"] == (row, col)
                )
                hidden_by_fall = any(
                    item["target"] == (row, col) for item in self.fall_animations
                )
                if piece and not hidden_by_drag and not hidden_by_merge and not hidden_by_fall:
                    self.draw_piece(piece, rect, self.selected == (row, col))

    def cell_center(self, cell):
        row, col = cell
        return (BOARD_X + col * CELL + CELL // 2, BOARD_Y + row * CELL + CELL // 2)

    def draw_merge_animation(self):
        animation = self.merge_animation
        if not animation:
            return
        progress = min(1.0, (time.monotonic() - animation["born"]) / MERGE_ANIMATION_DURATION)
        eased = progress * progress * (3.0 - 2.0 * progress)
        source_x, source_y = self.cell_center(animation["source"])
        target_x, target_y = self.cell_center(animation["target"])

        if progress < 0.76:
            target_rect = pygame.Rect(0, 0, CELL, CELL)
            target_rect.center = (target_x, target_y)
            self.draw_piece(animation["piece"], target_rect)

            moving_x = source_x + (target_x - source_x) * eased
            moving_y = source_y + (target_y - source_y) * eased - math.sin(math.pi * eased) * 18
            moving_rect = pygame.Rect(0, 0, CELL, CELL)
            moving_rect.center = (round(moving_x), round(moving_y))
            self.draw_piece(animation["piece"], moving_rect, True)
        else:
            row, col = animation["target"]
            result_piece = self.state.board[row][col]
            if result_piece:
                result_rect = pygame.Rect(0, 0, CELL, CELL)
                result_rect.center = (target_x, target_y)
                self.draw_piece(result_piece, result_rect, True)
            pulse = int(25 + 18 * (1.0 - progress))
            pygame.draw.circle(self.screen, PALETTE["gold"], (target_x, target_y), pulse, 4)

    def draw_fall_animations(self):
        now = time.monotonic()
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(pygame.Rect(BOARD_X, BOARD_Y, BOARD_W, BOARD_H))
        for animation in self.fall_animations:
            elapsed = now - animation["born"] - animation["delay"]
            if elapsed < 0:
                progress = 0.0
            else:
                progress = min(1.0, elapsed / FALL_ANIMATION_DURATION)

            if progress < 0.82:
                travel = (progress / 0.82) ** 2
            else:
                bounce_progress = (progress - 0.82) / 0.18
                travel = 1.0 - 0.055 * math.sin(math.pi * bounce_progress)

            source_x, source_y = self.cell_center(animation["source"])
            target_x, target_y = self.cell_center(animation["target"])
            x = source_x + (target_x - source_x) * travel
            y = source_y + (target_y - source_y) * travel
            rect = pygame.Rect(0, 0, CELL, CELL)
            rect.center = (round(x), round(y))
            self.draw_piece(animation["piece"], rect)
        self.screen.set_clip(previous_clip)

    @staticmethod
    def projectile_point(source, target, progress):
        eased = 1.0 - (1.0 - progress) ** 3
        x = source[0] + (target[0] - source[0]) * eased
        y = (
            source[1]
            + (target[1] - source[1]) * eased
            - math.sin(math.pi * eased) * 42
        )
        return x, y

    def draw_effect_sprite(self, sprite, center, scale=1.0, angle=0.0, alpha=255):
        if sprite is None:
            return
        transformed = pygame.transform.rotozoom(sprite, angle, scale)
        if alpha < 255:
            transformed.set_alpha(max(0, min(255, round(alpha))))
        self.screen.blit(transformed, transformed.get_rect(center=center))

    def draw_colored_glow(self, center, color, radius, alpha):
        glow = pygame.Surface((radius * 2 + 8, radius * 2 + 8), pygame.SRCALPHA)
        glow_center = (radius + 4, radius + 4)
        for scale, opacity in ((1.0, 0.12), (0.72, 0.18), (0.45, 0.26)):
            pygame.draw.circle(
                glow,
                (*color, round(alpha * opacity)),
                glow_center,
                max(1, round(radius * scale)),
            )
        self.screen.blit(glow, glow.get_rect(center=center))

    @staticmethod
    def colorize_effect(sprite, color):
        if sprite is None:
            return None
        colored = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
        width, height = sprite.get_size()
        for y in range(height):
            for x in range(width):
                source = sprite.get_at((x, y))
                if not source.a:
                    continue
                brightness = max(source.r, source.g, source.b) / 255
                highlight = 0.04 + brightness * 0.24
                tinted = mix_color(color, PALETTE["white"], highlight)
                shade = 0.72 + brightness * 0.28
                colored.set_at(
                    (x, y),
                    (
                        round(tinted[0] * shade),
                        round(tinted[1] * shade),
                        round(tinted[2] * shade),
                        source.a,
                    ),
                )
        return colored

    def draw_projectile_particles(self, animation, source, target, progress):
        if len(self.projectile_particles) != 3:
            return
        color_index = COLORS.index(animation["color"])
        particle_choices = (
            self.projectile_particles[0][color_index],
            self.projectile_particles[1][color_index],
            self.projectile_particles[2][color_index],
        )
        for index, particle in enumerate(particle_choices):
            lag = 0.055 + index * 0.045
            sample_progress = max(0.0, progress - lag)
            px, py = self.projectile_point(source, target, sample_progress)
            wobble = math.sin(progress * 24 + index * 2.3) * (4 + index * 2)
            px += wobble
            py += math.cos(progress * 21 + index) * 3
            alpha = min(220, progress * 700) * (1.0 - index * 0.13)
            self.draw_effect_sprite(
                particle,
                (round(px), round(py)),
                scale=0.78 + index * 0.08,
                angle=progress * 260 + index * 37,
                alpha=alpha,
            )

    def draw_projectiles(self):
        now = time.monotonic()
        targets = {"red": (105, 280), "blue": (270, 280), "green": (435, 280)}
        for animation in self.projectile_animations:
            elapsed = now - animation["born"] - animation["delay"]
            if elapsed < 0:
                continue
            color_name = animation["color"]
            color = PALETTE[color_name]
            target = (270, 270) if self.state.is_boss_wave else targets[color_name]
            source = self.cell_center(animation["source"])
            if elapsed < PROJECTILE_TRAVEL_DURATION:
                progress = elapsed / PROJECTILE_TRAVEL_DURATION
                x, y = self.projectile_point(source, target, progress)
                previous_progress = max(0.0, progress - 0.025)
                previous_x, previous_y = self.projectile_point(
                    source, target, previous_progress
                )
                direction_x = x - previous_x
                direction_y = y - previous_y
                direction_length = max(0.001, math.hypot(direction_x, direction_y))
                unit_x = direction_x / direction_length
                unit_y = direction_y / direction_length
                angle = math.degrees(math.atan2(-direction_y, direction_x))

                trail = self.projectile_trails.get(color_name)
                if trail is not None and progress > 0.025:
                    trail = pygame.transform.flip(trail, True, False)
                    trail_center = (
                        round(x - unit_x * PROJECTILE_TRAIL_SIZE[0] * 0.42),
                        round(y - unit_y * PROJECTILE_TRAIL_SIZE[0] * 0.42),
                    )
                    self.draw_effect_sprite(
                        trail,
                        trail_center,
                        scale=0.72 + min(0.28, progress),
                        angle=angle,
                        alpha=min(255, progress * 720),
                    )
                else:
                    trail_x = x - unit_x * 36
                    trail_y = y - unit_y * 36
                    pygame.draw.line(
                        self.screen, PALETTE["cream"], (trail_x, trail_y), (x, y), 8
                    )
                    pygame.draw.line(
                        self.screen, color, (trail_x, trail_y), (x, y), 4
                    )

                self.draw_projectile_particles(animation, source, target, progress)
                candy_center = (round(x), round(y))
                self.draw_colored_glow(candy_center, color, 28, 155)
                projectile = self.projectile_sprites.get(color_name)
                if projectile is not None:
                    launch_scale = 0.62 + min(0.38, progress * 2.4)
                    self.draw_effect_sprite(
                        projectile,
                        candy_center,
                        scale=launch_scale,
                        angle=-progress * 690,
                    )
                else:
                    pygame.draw.polygon(
                        self.screen,
                        color,
                        star_points(candy_center, 16, 8, rotation=-math.pi / 2 + progress * 8),
                    )
                    pygame.draw.polygon(
                        self.screen, PALETTE["cream"], star_points(candy_center, 9, 4)
                    )

                if animation.get("royal") and progress < 0.86:
                    crown_progress = progress / 0.86
                    fade_in = min(1.0, crown_progress / 0.16)
                    fade_out = min(1.0, (1.0 - crown_progress) / 0.30)
                    crown_alpha = 255 * min(fade_in, fade_out)
                    crown_scale = 0.72 + min(0.24, crown_progress * 1.4)
                    crown_center = (source[0], source[1] - 24)
                    self.draw_colored_glow(
                        crown_center,
                        color,
                        48,
                        crown_alpha * 0.9,
                    )
                    self.draw_effect_sprite(
                        self.projectile_crown,
                        crown_center,
                        scale=crown_scale,
                        alpha=crown_alpha,
                    )
            else:
                impact = min(
                    1.0,
                    (elapsed - PROJECTILE_TRAVEL_DURATION)
                    / PROJECTILE_IMPACT_DURATION,
                )
                impact_scale = 0.46 + 0.78 * (1.0 - (1.0 - impact) ** 3)
                impact_alpha = 255 * (1.0 - impact) ** 0.62
                self.draw_colored_glow(
                    target,
                    color,
                    round(64 + impact * 28),
                    impact_alpha,
                )
                colored_impact = self.projectile_impacts.get(color_name)
                if colored_impact is not None:
                    self.draw_effect_sprite(
                        colored_impact,
                        target,
                        scale=impact_scale,
                        angle=impact * 42,
                        alpha=impact_alpha,
                    )
                else:
                    radius = int(18 + impact * 34)
                    ring_color = tuple(min(255, channel + 70) for channel in color)
                    pygame.draw.polygon(
                        self.screen,
                        ring_color,
                        star_points(target, radius, radius * 0.48),
                        5,
                    )
                damage = display_font(21).render(
                    self.text("damage_popup", damage=animation["damage"]), True, color
                )
                damage_rect = damage.get_rect(
                    center=(target[0], target[1] - 68 - impact * 7)
                )
                glossy_rect(
                    self.screen,
                    PALETTE["cream"],
                    damage_rect.inflate(18, 10),
                    10,
                    PALETTE["pink_dark"],
                )
                self.screen.blit(damage, damage_rect)

    def draw_dragged_piece(self):
        if not self.is_dragging or self.drag_start is None or self.drag_pos is None:
            return
        row, col = self.drag_start
        piece = self.state.board[row][col]
        if piece:
            rect = pygame.Rect(0, 0, CELL, CELL)
            rect.center = self.drag_pos
            self.draw_piece(piece, rect, True)

    def draw_hud(self):
        if self.state.is_boss_wave:
            self.draw_boss((270, 260), self.state.boss)
        else:
            positions = [(105, 280), (270, 280), (435, 280)]
            for color, pos in zip(COLORS, positions):
                self.draw_monster(color, pos, self.state.monsters[color])

        level_panel = pygame.Rect(54, 102, 302, 42)
        moves_panel = pygame.Rect(366, 102, 120, 42)
        pygame.draw.rect(
            self.screen, PALETTE["pink_dark"], level_panel.move(0, 4), border_radius=18
        )
        glossy_rect(self.screen, PALETTE["pink"], level_panel, 18)
        glossy_rect(
            self.screen, PALETTE["cream"], level_panel.inflate(-7, -7), 14,
            PALETTE["pink_dark"]
        )
        level_wave = font(17, True).render(
            self.text(
                "level_wave",
                level=self.state.level,
                wave=self.state.wave_number,
                total=self.state.total_waves,
            ),
            True,
            PALETTE["ink"],
        )
        self.screen.blit(level_wave, level_wave.get_rect(center=level_panel.center))

        moves_fill = PALETTE["red"] if self.state.moves_remaining <= 5 else PALETTE["gold"]
        pygame.draw.rect(
            self.screen,
            mix_color(moves_fill, PALETTE["shadow"], 0.28),
            moves_panel.move(0, 4),
            border_radius=18,
        )
        glossy_rect(self.screen, moves_fill, moves_panel, 18)
        glossy_rect(
            self.screen,
            PALETTE["cream"],
            moves_panel.inflate(-7, -7),
            14,
            PALETTE["pink_dark"],
        )
        moves_color = PALETTE["red"] if self.state.moves_remaining <= 5 else PALETTE["ink"]
        moves = display_font(17).render(
            self.text("moves", count=self.state.moves_remaining), True, moves_color
        )
        self.screen.blit(moves, moves.get_rect(center=moves_panel.center))

        message = (
            self.message
            if time.monotonic() < self.message_until
            else self.text("default_hint")
        )
        message_panel = pygame.Rect(35, 836, WIDTH - 70, 36)
        pygame.draw.rect(
            self.screen, PALETTE["shadow"], message_panel.move(0, 3), border_radius=15
        )
        glossy_rect(
            self.screen, PALETTE["cream"], message_panel, 15, PALETTE["pink"]
        )
        text = font(16, True).render(message, True, PALETTE["ink"])
        self.screen.blit(text, text.get_rect(center=message_panel.center))
        if not (
            self.state.game_over
            or self.state.game_won
            or self.level_clear_started_at
        ):
            self.draw_control_hints()

    def draw_control_hints(self):
        groups = (
            (("R",), self.text("restart_short")),
            (("SHIFT", "+", "R"), self.text("new_game_short")),
            (("ESC",), self.text("quit_short")),
        )
        key_face = font(11, True)
        label_face = font(12, True)
        key_padding = 7
        key_gap = 3
        label_gap = 5
        group_gap = 13

        prepared = []
        total_width = 0
        for keys, label_text in groups:
            items = []
            keys_width = 0
            for key in keys:
                surface = key_face.render(key, True, PALETTE["ink"])
                if key == "+":
                    width = surface.get_width()
                    is_keycap = False
                else:
                    width = surface.get_width() + key_padding * 2
                    is_keycap = True
                items.append((surface, width, is_keycap))
                keys_width += width
            keys_width += key_gap * (len(items) - 1)
            label = label_face.render(label_text, True, PALETTE["ink"])
            group_width = keys_width + label_gap + label.get_width()
            prepared.append((items, label, group_width))
            total_width += group_width
        total_width += group_gap * (len(prepared) - 1)

        x = (WIDTH - total_width) // 2
        center_y = 884
        for items, label, group_width in prepared:
            item_x = x
            for surface, width, is_keycap in items:
                if is_keycap:
                    key_rect = pygame.Rect(item_x, center_y - 10, width, 20)
                    pygame.draw.rect(
                        self.screen,
                        PALETTE["shadow"],
                        key_rect.move(0, 2),
                        border_radius=6,
                    )
                    rounded_rect(self.screen, PALETTE["white"], key_rect, 6)
                    rounded_rect(self.screen, PALETTE["pink_dark"], key_rect, 6, 2)
                    self.screen.blit(surface, surface.get_rect(center=key_rect.center))
                else:
                    self.screen.blit(
                        surface,
                        surface.get_rect(center=(item_x + width // 2, center_y)),
                    )
                item_x += width + key_gap
            item_x += label_gap - key_gap
            self.screen.blit(
                label,
                label.get_rect(midleft=(item_x, center_y)),
            )
            x += group_width + group_gap

    def draw_level_clear_celebration(self):
        if not self.level_clear_started_at or self.level_clear_level is None:
            return
        elapsed = max(0.0, time.monotonic() - self.level_clear_started_at)

        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade_alpha = round(125 * min(1.0, elapsed / 0.32))
        shade.fill((63, 42, 67, shade_alpha))
        self.screen.blit(shade, (0, 0))

        target = (WIDTH // 2, 303)
        origins = ((118, 670), (270, 720), (422, 670))
        bends = (-66, 0, 66)
        gather = min(1.0, elapsed / LEVEL_CLEAR_GATHER_DURATION)
        eased = 1.0 - (1.0 - gather) ** 3
        for index, color_name in enumerate(COLORS):
            color = PALETTE[color_name]

            def celebration_point(progress):
                x = origins[index][0] + (target[0] - origins[index][0]) * progress
                y = origins[index][1] + (target[1] - origins[index][1]) * progress
                x += math.sin(math.pi * progress) * bends[index]
                y -= math.sin(math.pi * progress) * (45 + index * 7)
                return round(x), round(y)

            trail_layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            trail_points = []
            for step in range(7, -1, -1):
                sample = max(0.0, eased - step * 0.045)
                trail_points.append(celebration_point(sample))
            if len(trail_points) > 1:
                pygame.draw.lines(
                    trail_layer,
                    (*PALETTE["cream"], 135),
                    False,
                    trail_points,
                    8,
                )
                pygame.draw.lines(
                    trail_layer,
                    (*color, 205),
                    False,
                    trail_points,
                    4,
                )
            self.screen.blit(trail_layer, (0, 0))

            candy_center = celebration_point(eased)
            self.draw_colored_glow(candy_center, color, 32, 180)
            projectile = self.projectile_sprites.get(color_name)
            if projectile is not None:
                self.draw_effect_sprite(
                    projectile,
                    candy_center,
                    scale=0.82 + gather * 0.2,
                    angle=-gather * 520 + index * 18,
                )
            else:
                pygame.draw.polygon(
                    self.screen,
                    color,
                    star_points(candy_center, 18, 9, rotation=gather * 6),
                )

        if elapsed >= LEVEL_CLEAR_BURST_AT:
            burst = min(1.0, (elapsed - LEVEL_CLEAR_BURST_AT) / 0.72)
            burst_eased = 1.0 - (1.0 - burst) ** 3
            self.draw_colored_glow(
                target,
                PALETTE["gold"],
                round(55 + burst_eased * 95),
                230 * (1.0 - burst * 0.42),
            )
            confetti_colors = (
                PALETTE["red"],
                PALETTE["blue"],
                PALETTE["green"],
                PALETTE["gold"],
                PALETTE["pink"],
            )
            fall = max(0.0, elapsed - 1.25) * 34
            for index in range(32):
                angle = index * 2.399 + 0.35
                distance = (62 + (index % 8) * 17) * burst_eased
                x = target[0] + math.cos(angle) * distance
                y = target[1] + math.sin(angle) * distance * 0.72 + fall
                length = 5 + index % 4
                color = confetti_colors[index % len(confetti_colors)]
                pygame.draw.line(
                    self.screen,
                    color,
                    (round(x - math.cos(angle) * length), round(y - math.sin(angle) * length)),
                    (round(x + math.cos(angle) * length), round(y + math.sin(angle) * length)),
                    3,
                )

        if elapsed < LEVEL_CLEAR_CARD_AT:
            crown_progress = min(1.0, max(0.0, elapsed - 0.46) / 0.5)
            if crown_progress > 0:
                self.draw_colored_glow(target, PALETTE["gold"], 62, 210)
                self.draw_effect_sprite(
                    self.projectile_crown,
                    (target[0], target[1] - 42),
                    scale=0.72 + crown_progress * 0.3,
                    alpha=255 * crown_progress,
                )
            return

        card_progress = min(1.0, (elapsed - LEVEL_CLEAR_CARD_AT) / 0.46)
        offset = card_progress - 1.0
        card_scale = max(
            0.0,
            1.0 + 2.70158 * offset ** 3 + 1.70158 * offset ** 2,
        )
        card = pygame.Surface((400, 290), pygame.SRCALPHA)
        shadow_rect = pygame.Rect(5, 10, 390, 272)
        panel_rect = pygame.Rect(5, 3, 390, 272)
        rounded_rect(card, (*PALETTE["shadow"], 210), shadow_rect, 32)
        glossy_rect(card, PALETTE["pink"], panel_rect, 32)
        glossy_rect(
            card,
            PALETTE["cream"],
            panel_rect.inflate(-12, -12),
            26,
            PALETTE["pink_dark"],
        )

        sprinkle_colors = (
            PALETTE["red"],
            PALETTE["blue"],
            PALETTE["green"],
            PALETTE["gold"],
        )
        for index, x in enumerate((43, 78, 116, 286, 324, 356)):
            y = 26 + (index % 2) * 8
            pygame.draw.line(
                card,
                sprinkle_colors[index % len(sprinkle_colors)],
                (x - 3, y - 2),
                (x + 3, y + 2),
                3,
            )

        if self.projectile_crown is not None:
            crown = pygame.transform.smoothscale(self.projectile_crown, (78, 65))
            card.blit(crown, crown.get_rect(center=(200, 58)))

        level_title = display_font(34).render(
            self.text("level_clear_title", level=self.level_clear_level),
            True,
            PALETTE["pink_dark"],
        )
        cleared = display_font(43).render(
            self.text("level_clear_status"), True, PALETTE["gold"]
        )
        card.blit(level_title, level_title.get_rect(center=(200, 112)))
        card.blit(cleared, cleared.get_rect(center=(200, 153)))

        button = pygame.Rect(50, 195, 300, 58)
        rounded_rect(card, (*PALETTE["shadow"], 210), button.move(0, 5), 22)
        glossy_rect(card, PALETTE["pink"], button, 22, PALETTE["pink_dark"])
        if elapsed >= LEVEL_CLEAR_BUTTON_AT:
            pulse = 1 + round((math.sin(elapsed * 4.5) + 1) * 0.5)
            rounded_rect(card, PALETTE["white"], button.inflate(pulse, pulse), 23, 2)
        continue_text = display_font(27).render(
            self.text("continue_button"), True, PALETTE["white"]
        )
        card.blit(continue_text, continue_text.get_rect(center=button.center))

        scaled_size = (
            max(1, round(card.get_width() * card_scale)),
            max(1, round(card.get_height() * card_scale)),
        )
        scaled_card = pygame.transform.smoothscale(card, scaled_size)
        self.screen.blit(scaled_card, scaled_card.get_rect(center=(270, 438)))

    def draw_game_over(self):
        if not (self.state.game_over or self.state.game_won):
            return
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((91, 58, 76, 165))
        self.screen.blit(shade, (0, 0))
        panel = pygame.Rect(75, 286, 390, 300)
        pygame.draw.rect(
            self.screen, PALETTE["pink_dark"], panel.move(0, 8), border_radius=28
        )
        glossy_rect(self.screen, PALETTE["pink"], panel, 28)
        glossy_rect(
            self.screen, PALETTE["cream"], panel.inflate(-10, -10), 23,
            PALETTE["pink_dark"]
        )
        if self.state.game_won:
            title_text = self.text("victory_title")
            detail_text = self.text("victory_detail")
            title_color = PALETTE["green"]
        else:
            title_text = self.text("defeat_title")
            detail_text = self.text("defeat_detail")
            title_color = PALETTE["red"]
        title = display_font(34).render(title_text, True, title_color)
        detail = font(18, True).render(detail_text, True, PALETTE["ink"])
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 340)))
        self.screen.blit(detail, detail.get_rect(center=(WIDTH // 2, 395)))

        if not self.state.game_won:
            progress = font(15).render(
                self.text(
                    "failure_progress",
                    level=self.state.level,
                    wave=self.state.wave_number,
                    total=self.state.total_waves,
                ),
                True,
                PALETTE["ink"],
            )
            self.screen.blit(progress, progress.get_rect(center=(WIDTH // 2, 425)))

        for action, rect in self.end_screen_buttons().items():
            primary = action == "level" or self.state.game_won
            fill = PALETTE["gold"] if primary else PALETTE["cream"]
            border = PALETTE["pink_dark"]
            pygame.draw.rect(
                self.screen,
                mix_color(fill, PALETTE["shadow"], 0.25),
                rect.move(0, 4),
                border_radius=18,
            )
            glossy_rect(self.screen, fill, rect, 18, border)
            label_key = "retry_level_button" if action == "level" else "new_game_button"
            label = display_font(18).render(
                self.text(label_key), True, PALETTE["ink"]
            )
            self.screen.blit(label, label.get_rect(center=rect.center))

    def draw(self):
        self.draw_background()
        self.draw_hud()
        self.draw_board()
        self.draw_fall_animations()
        self.draw_merge_animation()
        self.draw_projectiles()
        self.draw_dragged_piece()
        self.draw_level_clear_celebration()
        self.draw_game_over()
        pygame.display.flip()

    def run(self):
        while self.running:
            self.events()
            self.update()
            self.draw()
            self.clock.tick(FPS)
        pygame.quit()


if __name__ == "__main__":
    try:
        Game().run()
    except pygame.error as exc:
        print(translate(DEFAULT_LANGUAGE, "pygame_error", error=exc))
        sys.exit(1)
