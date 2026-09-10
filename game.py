from __future__ import annotations

import math
from pathlib import Path
import sys
import time

import pygame

from game_logic import COLORS, MAX_LEVEL, GameState, Piece


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
PIECE_SPRITE_SIZE = (68, 68)
MONSTER_SPRITE_SIZE = (126, 126)

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


def font(size: int, bold: bool = False) -> pygame.font.Font:
    candidates = [
        "/System/Library/Fonts/STHeiti Medium.ttc" if bold else "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return pygame.font.Font(candidate, size)
    return pygame.font.SysFont("Arial", size, bold=bold)


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
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("糖果玩具大作战")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.piece_sprites = self.load_piece_sprites()
        self.monster_sprites = self.load_monster_sprites()
        self.state = GameState()
        self.selected = None
        self.drag_start = None
        self.drag_pos = None
        self.is_dragging = False
        self.mouse_down = None
        self.refill_at = 0.0
        self.auto_merge_at = 0.0
        self.auto_focus = None
        self.message = "把相同物品摆到相邻位置"
        self.message_until = 0.0
        self.merge_animation = None
        self.fall_animations = []
        self.projectile_animations = []
        self.active_chain_attack = None
        self.settle_at = 0.0
        self.running = True

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
            self.show_message("拖拽次数已用完", 1.5)
            return
        if result.kind == "game_over":
            return
        if result.kind in ("merge", "max_merge", "attack"):
            self.handle_merge_result(result, animate=False, new_chain=True)
            self.auto_focus = result.target
            self.auto_merge_at = time.monotonic() + 0.10
        else:
            self.show_message("物品不同，返回原位", 1.2)

    def handle_merge_result(self, result, animate=True, new_chain=False):
        if result.kind == "merge":
            self.show_message(f"合成成功！累计 {result.damage} 点攻击")
            self.record_chain_attack(result, new_chain)
            if animate:
                self.start_merge_animation(result)
        elif result.kind == "max_merge":
            self.show_message(f"达到最高等级！累计 {result.damage} 点攻击")
            self.record_chain_attack(result, new_chain)
            if animate:
                self.start_merge_animation(result)
        elif result.kind == "attack":
            self.show_message(f"五级物品准备发射：{result.damage} 点攻击")
            self.start_projectile(result.target, result.color, result.damage)

    def show_attack_resolution(self, result):
        if result.wave_cleared:
            if self.state.is_boss_wave:
                self.show_message("重击命中！Boss 已被击败")
            else:
                self.show_message("炮弹命中！本波怪物全部击败")
        elif result.monster_defeated:
            self.show_message("炮弹命中并击败怪物，等待其他颜色")
        else:
            self.show_message(f"炮弹发射！怪物生命减少 {result.damage}")

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

    def start_projectile(self, source, color, damage, delay=0.0):
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
        )

    def events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_r:
                    self.state.reset()
                    self.selected = None
                    self.refill_at = 0.0
                    self.auto_merge_at = 0.0
                    self.auto_focus = None
                    self.merge_animation = None
                    self.fall_animations = []
                    self.projectile_animations = []
                    self.active_chain_attack = None
                    self.settle_at = 0.0
                    self.show_message("新游戏开始！")
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.board_busy():
                    self.show_message("正在结算，请稍候", 0.8)
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
                        self.show_message("已返回原位", 1.0)
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
                        self.show_message("对应怪物已击败，五级物品已释放", 1.5)
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
            if not item["applied"] and now - item["born"] >= item["delay"]:
                item["applied"] = True
                resolution = self.state.resolve_attack(
                    item["color"], item["damage"], item["source"]
                )
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
        transition = self.state.advance_wave()
        if transition == "wave":
            if self.state.is_boss_wave:
                self.show_message("Boss 登场！所有颜色都能造成伤害", 2.2)
            else:
                self.show_message(f"第 {self.state.wave_number} 波怪物出现！")
        elif transition == "level":
            self.show_message(
                f"进入第 {self.state.level} 关，拖拽次数已补满！", 2.2
            )
        elif transition == "won":
            self.show_message("前四关全部通关！", 3.0)
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
        title = font(31, True).render("糖果玩具大作战", True, PALETTE["pink_dark"])
        self.screen.blit(title, title.get_rect(center=title_patch.center))

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

        if monster.stage > 1:
            pygame.draw.polygon(self.screen, PALETTE["gold"], star_points((x, y - 45), 11, 5))

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
        if monster.hp <= 0:
            defeated = font(17, True).render("已击败", True, PALETTE["ink"])
            defeated_rect = defeated.get_rect(center=(x, y))
            glossy_rect(
                self.screen, PALETTE["cream"], defeated_rect.inflate(18, 10),
                10, PALETTE["pink_dark"]
            )
            self.screen.blit(defeated, defeated_rect)

    def draw_monster(self, color, center, monster):
        sprite = self.monster_sprites.get(color)
        if sprite is None:
            self._draw_monster_procedural(color, center, monster)
            return

        x, y = center
        body = PALETTE[color]
        light = mix_color(body, PALETTE["white"], 0.45)
        sprite_rect = sprite.get_rect(center=(x, y - 8))
        self.screen.blit(sprite, sprite_rect)

        if monster.stage > 1:
            crown = star_points((x, sprite_rect.top + 8), 11, 5)
            pygame.draw.polygon(self.screen, PALETTE["gold"], crown)
            pygame.draw.polygon(self.screen, PALETTE["ink"], crown, 2)

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

        if monster.hp <= 0:
            defeated = font(17, True).render("已击败", True, PALETTE["ink"])
            defeated_rect = defeated.get_rect(center=(x, y))
            glossy_rect(
                self.screen,
                PALETTE["cream"],
                defeated_rect.inflate(18, 10),
                10,
                PALETTE["pink_dark"],
            )
            self.screen.blit(defeated, defeated_rect)

    def draw_boss(self, center, boss):
        """绘制不受颜色限制的糖果巨兽和加宽血条。"""
        x, y = center
        body = PALETTE["boss"]
        dark = mix_color(body, PALETTE["ink"], 0.35)
        light = mix_color(body, PALETTE["white"], 0.48)

        pygame.draw.ellipse(self.screen, (207, 150, 139), (x - 82, y + 44, 164, 18))
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
            pygame.draw.circle(self.screen, PALETTE["white"], (x + dx - 3, y - 8), 3)
        pygame.draw.arc(
            self.screen, PALETTE["ink"], (x - 25, y + 10, 50, 32), math.pi, math.tau, 5
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

        label = font(18, True).render(f"BOSS {boss.stage}", True, PALETTE["ink"])
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

    def draw_projectiles(self):
        now = time.monotonic()
        targets = {"red": (105, 280), "blue": (270, 280), "green": (435, 280)}
        for animation in self.projectile_animations:
            elapsed = now - animation["born"] - animation["delay"]
            if elapsed < 0:
                continue
            color = PALETTE[animation["color"]]
            if self.state.is_boss_wave:
                target_x, target_y = (270, 270)
            else:
                target_x, target_y = targets[animation["color"]]
            if elapsed < PROJECTILE_TRAVEL_DURATION:
                progress = elapsed / PROJECTILE_TRAVEL_DURATION
                eased = 1.0 - (1.0 - progress) ** 3
                source_x, source_y = self.cell_center(animation["source"])
                x = source_x + (target_x - source_x) * eased
                y = source_y + (target_y - source_y) * eased - math.sin(math.pi * eased) * 42
                previous = max(0.0, eased - 0.08)
                trail_x = source_x + (target_x - source_x) * previous
                trail_y = source_y + (target_y - source_y) * previous - math.sin(math.pi * previous) * 42
                pygame.draw.line(
                    self.screen, PALETTE["gold"], (trail_x, trail_y), (x, y), 7
                )
                candy_center = (round(x), round(y))
                pygame.draw.polygon(
                    self.screen,
                    color,
                    [
                        (candy_center[0] - 15, candy_center[1]),
                        (candy_center[0] - 9, candy_center[1] - 7),
                        (candy_center[0] - 9, candy_center[1] + 7),
                    ],
                )
                pygame.draw.polygon(
                    self.screen,
                    color,
                    [
                        (candy_center[0] + 15, candy_center[1]),
                        (candy_center[0] + 9, candy_center[1] - 7),
                        (candy_center[0] + 9, candy_center[1] + 7),
                    ],
                )
                pygame.draw.circle(self.screen, PALETTE["white"], candy_center, 10)
                pygame.draw.circle(self.screen, color, candy_center, 7)
            else:
                impact = min(1.0, (elapsed - PROJECTILE_TRAVEL_DURATION) / PROJECTILE_IMPACT_DURATION)
                radius = int(18 + impact * 34)
                ring_color = tuple(min(255, channel + 70) for channel in color)
                pygame.draw.circle(self.screen, ring_color, (target_x, target_y), radius, 5)
                damage = font(22, True).render(
                    f"攻击 +{animation['damage']}", True, color
                )
                damage_rect = damage.get_rect(
                    center=(target_x, target_y - 68 - impact * 7)
                )
                glossy_rect(
                    self.screen,
                    PALETTE["cream"],
                    damage_rect.inflate(18, 10),
                    10,
                    PALETTE["pink_dark"],
                )
                self.screen.blit(
                    damage,
                    damage_rect,
                )

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

        score_panel = pygame.Rect(80, 102, 380, 42)
        pygame.draw.rect(
            self.screen, PALETTE["pink_dark"], score_panel.move(0, 4), border_radius=18
        )
        glossy_rect(
            self.screen, PALETTE["pink"], score_panel, 18
        )
        glossy_rect(
            self.screen, PALETTE["cream"], score_panel.inflate(-7, -7), 14,
            PALETTE["pink_dark"]
        )
        moves_color = PALETTE["red"] if self.state.moves_remaining <= 5 else PALETTE["ink"]
        wave_name = "Boss" if self.state.is_boss_wave else "普通"
        moves = font(18, True).render(
            f"第{self.state.level}关  {self.state.wave_number}/{self.state.total_waves}波·{wave_name}  "
            f"本关剩余 {self.state.moves_remaining}",
            True,
            moves_color,
        )
        self.screen.blit(moves, moves.get_rect(center=score_panel.center))

        message = self.message if time.monotonic() < self.message_until else "拖拽合成；单击最高级物品发动攻击"
        message_panel = pygame.Rect(35, 836, WIDTH - 70, 36)
        pygame.draw.rect(
            self.screen, PALETTE["shadow"], message_panel.move(0, 3), border_radius=15
        )
        glossy_rect(
            self.screen, PALETTE["cream"], message_panel, 15, PALETTE["pink"]
        )
        text = font(18, True).render(message, True, PALETTE["ink"])
        self.screen.blit(text, text.get_rect(center=message_panel.center))
        hint = font(15).render("R：重新开始    Esc：退出", True, (103, 103, 90))
        self.screen.blit(hint, hint.get_rect(center=(WIDTH // 2, 882)))

    def draw_game_over(self):
        if not (self.state.game_over or self.state.game_won):
            return
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((91, 58, 76, 165))
        self.screen.blit(shade, (0, 0))
        panel = pygame.Rect(75, 325, 390, 210)
        pygame.draw.rect(
            self.screen, PALETTE["pink_dark"], panel.move(0, 8), border_radius=28
        )
        glossy_rect(self.screen, PALETTE["pink"], panel, 28)
        glossy_rect(
            self.screen, PALETTE["cream"], panel.inflate(-10, -10), 23,
            PALETTE["pink_dark"]
        )
        if self.state.game_won:
            title_text = "四关通关！"
            detail_text = "所有糖果怪物与 Boss 已被击败"
            title_color = PALETTE["green"]
        else:
            title_text = "挑战失败"
            detail_text = "本关拖拽次数已用完"
            title_color = PALETTE["red"]
        title = font(38, True).render(title_text, True, title_color)
        detail = font(20).render(detail_text, True, PALETTE["ink"])
        hint = font(18).render("按 R 重新开始", True, PALETTE["ink"])
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 380)))
        self.screen.blit(detail, detail.get_rect(center=(WIDTH // 2, 445)))
        self.screen.blit(hint, hint.get_rect(center=(WIDTH // 2, 492)))

    def draw(self):
        self.draw_background()
        self.draw_hud()
        self.draw_board()
        self.draw_fall_animations()
        self.draw_merge_animation()
        self.draw_projectiles()
        self.draw_dragged_piece()
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
        print(f"Pygame 无法启动：{exc}")
        sys.exit(1)
